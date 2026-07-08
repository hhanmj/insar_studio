"""JS<->Python bridge for the desktop web UI.

Every public method on :class:`Api` is callable from the frontend as
``window.pywebview.api.<method>(...)`` and returns a JSON-serialisable value
(pywebview marshals the return value into a JS Promise). This layer is
deliberately thin: it reuses the existing, fully-tested core
(:mod:`insar_prep.processing`, :mod:`insar_prep.providers`,
:mod:`insar_prep.quality`, :mod:`insar_prep.reporting`) and the Qt-free
:class:`insar_prep.gui.state.GuiState`, adding only (de)serialisation and stable
error codes.

Heavy / optional dependencies (shapely, rasterio, keyring, geopandas, ...) are
imported lazily *inside* the relevant methods so a missing extra only disables
that one feature instead of breaking the whole desktop app on startup.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import base64
import binascii
import io
from pathlib import Path
from typing import Any

from insar_prep import __version__
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.desktop.activity_log import ActivityLog
from insar_prep.desktop.download_job import AsfDownloadManager, DemDownloadJob, OrbitDownloadJob
from insar_prep.gui.state import GuiState, workspace_display_name

_EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS = 5 * 60
_EARTHDATA_AUTH_SUCCESS_CACHE_SECONDS = 90 * 60


def _error(exc: InsarPrepError) -> dict:
    """Render a coded core error as a JSON-friendly envelope for the UI."""
    code = getattr(exc, "code", None)
    return {"ok": False, "error": str(exc), "code": getattr(code, "name", None)}


def _error_msg(message: str, code: str | None = None) -> dict:
    """Build a plain error envelope (no core exception involved)."""
    return {"ok": False, "error": message, "code": code}


def _normalise_proxy_url(value: object) -> str:
    proxy_url = str(value or "").strip()
    if proxy_url and "://" not in proxy_url:
        proxy_url = f"http://{proxy_url}"
    return proxy_url


def _format_status_log_entry(entry: dict[str, Any]) -> str:
    detail = str(entry.get("detail") or "").strip()
    if not detail:
        return ""
    try:
        ts = float(entry.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts <= 0:
        return detail
    if ts > 10_000_000_000:
        ts = ts / 1000
    return f"[{time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(ts))}] {detail}"


def _local_dem_output_exists(path: Path) -> bool:
    related = [path, path.with_name(path.name + ".part")]
    if path.suffix:
        related.append(path.with_suffix(path.suffix + ".part"))
    related.extend([path.with_suffix(".hdr"), path.with_suffix(".sml")])
    return any(item.exists() for item in related)


def _unique_local_dem_path(path: Path) -> Path:
    if not _local_dem_output_exists(path):
        return path
    parent = path.parent
    suffix = path.suffix
    stem = path.stem if suffix else path.name
    for index in range(2, 10_000):
        candidate = parent / f"{stem}_{index}{suffix}"
        if not _local_dem_output_exists(candidate):
            return candidate
    raise ValueError(f"无法生成不冲突的 DEM 输出文件名：{path}")


def _is_update_installer(path: Path) -> bool:
    """Return True when a downloaded release asset can be used as an installer."""
    name = path.name.lower()
    return name.endswith(".msi") or (
        name.endswith(".exe") and ("setup" in name or "installer" in name)
    )


def _launch_update_installer(path: Path) -> None:
    """Start the downloaded installer with quiet per-user update arguments."""
    import subprocess  # noqa: PLC0415

    name = path.name.lower()
    if name.endswith(".msi"):
        args = ["msiexec.exe", "/i", str(path), "/qn", "/norestart"]
    else:
        args = [
            str(path),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
    subprocess.Popen(args, close_fds=True)  # noqa: S603 - path is a downloaded release asset.


def _detect_system_proxy() -> str:
    """Return the OS/browser proxy, if one is configured."""
    try:
        import urllib.request  # noqa: PLC0415 - small stdlib import, only needed here

        proxies = urllib.request.getproxies()
    except Exception:  # noqa: BLE001 - proxy probing must not block settings
        return ""
    for key in ("https", "http", "all"):
        proxy_url = _normalise_proxy_url(proxies.get(key))
        if proxy_url:
            return proxy_url
    return ""


def _asf_network_candidates(settings: dict) -> list[dict[str, Any]]:
    """Build ordered ASF download network modes for preflight fallback."""
    proxy_enabled = bool(settings.get("proxy_enabled"))
    saved_proxy = _normalise_proxy_url(settings.get("proxy_url"))
    system_proxy = _detect_system_proxy()
    ssl_verify = bool(settings.get("asf_ssl_verify", True))
    current_proxy = saved_proxy if proxy_enabled else ""
    if proxy_enabled and not current_proxy:
        current_proxy = system_proxy

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, bool, bool]] = set()

    def add(label: str, proxy_url: str, verify: bool, trust_env: bool) -> None:
        normalised = _normalise_proxy_url(proxy_url)
        key = (normalised, bool(verify), bool(trust_env))
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "label": label,
                "proxy_url": normalised,
                "ssl_verify": bool(verify),
                "trust_env": bool(trust_env),
            }
        )

    def add_with_tls_fallback(label: str, proxy_url: str, trust_env: bool) -> None:
        add(label, proxy_url, ssl_verify, trust_env)
        if ssl_verify:
            add(f"{label}（忽略 ASF 证书异常）", proxy_url, False, trust_env)

    add_with_tls_fallback("当前网络设置", current_proxy, proxy_enabled)
    add_with_tls_fallback("直连", "", False)
    if system_proxy:
        add_with_tls_fallback("系统代理", system_proxy, True)
    if saved_proxy:
        add_with_tls_fallback("保存的代理", saved_proxy, True)
    return candidates


def _missing_dep(feature: str, exc: Exception) -> dict:
    """Friendly envelope when an optional dependency is not installed."""
    text = str(exc)
    if "DEM" in feature and _is_dem_component_environment_error(text):
        return {
            "ok": False,
            "error": (
                f"{feature}需要 DEM 高级转换组件。请到“设置 → 更新与组件”安装该组件后重试。"
                f" 原因：{text}"
            ),
            "code": "DEP000",
        }
    return {
        "ok": False,
        "error": f"{feature}需要可选依赖，但当前环境未安装：{text}",
        "code": "DEP000",
    }


def _is_dem_component_environment_error(value: object) -> bool:
    text = str(value or "")
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "rasterio",
            "gdal",
            "proj.db",
            "proj_create_from_database",
            "the epsg code is unknown",
            "cannot find proj.db",
            "convert extra",
        )
    )


def _dem_component_error(feature: str, exc: Exception | str) -> dict:
    text = str(exc)
    return {
        "ok": False,
        "error": (
            f"{feature}需要完整的 DEM/GDAL 高级转换组件。"
            "如果组件状态显示“缺 EGM2008 网格”，说明当前组件包只有 GDAL/PROJ 运行库，"
            "还缺少 COP30/COP90 精确转椭球高所需的大地水准面网格。"
            "请到“设置 → 更新与组件”安装或重新安装包含 EGM2008 网格的组件后重试。"
            f" 原因：{text}"
        ),
        "code": "DEP000",
    }


def _ui_log(message: str, *, ts: float | None = None) -> str:
    when = time.localtime(ts if ts is not None else time.time())
    return f"[{time.strftime('%Y/%m/%d %H:%M:%S', when)}] {mask_text(message)}"


def _dem_result_logs(results: list[Any], *, prefix: str) -> list[str]:
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        outcome = getattr(getattr(result, "outcome", ""), "value", getattr(result, "outcome", ""))
        region = str(getattr(result, "region_safe_name", "") or "").strip()
        message = str(getattr(result, "message", "") or "").strip()
        path = str(getattr(result, "path", "") or "").strip()
        code = str(getattr(result, "error_code", "") or "").strip()
        parts = [prefix, f"{index}", outcome]
        if region:
            parts.append(region)
        if code:
            parts.append(code)
        detail = " / ".join(str(item) for item in parts if item)
        tail = "；".join(item for item in (message, path) if item)
        lines.append(_ui_log(f"{detail}：{tail}" if tail else detail))
    return lines


def _dump(model: Any) -> Any:
    """Serialise a pydantic model to JSON-safe primitives."""
    return model.model_dump(mode="json")


def _dump_optional(model: Any | None) -> Any | None:
    """Serialise a pydantic model only when it exists."""
    return _dump(model) if model is not None else None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _download_archive_layout(kind: str, item: dict[str, Any]) -> str:
    layout = str(item.get("download_layout") or "").strip().lower()
    if kind == "asf":
        if layout in {"flat", "product_subdirs"}:
            return layout
        return "product_subdirs" if _coerce_bool(item.get("use_product_subdirs"), False) else "flat"
    if kind == "orbit":
        if layout in {"flat", "orbit_subdir"}:
            return layout
        return "orbit_subdir" if _coerce_bool(item.get("use_orbit_subdir"), False) else "flat"
    return layout


def _clean_download_archive(value: Any) -> list[dict[str, Any]]:
    """Return safe, compact download history records for persistence/UI."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value[:80]:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        status = str(item.get("status") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if status == "deleted":
            continue
        if not task_id or not name or not status:
            continue
        try:
            ts = int(float(item.get("ts") or 0))
        except (TypeError, ValueError):
            ts = 0
        raw_logs = item.get("logs")
        logs = [str(line)[:2000] for line in raw_logs[:120]] if isinstance(raw_logs, list) else []
        kind = str(item.get("kind") or "").strip()
        output_dir = str(item.get("output_dir") or "").strip()
        try:
            total = int(float(item.get("total") or 0))
        except (TypeError, ValueError):
            total = 0
        try:
            concurrency = int(float(item.get("concurrency") or 0))
        except (TypeError, ValueError):
            concurrency = 0
        use_product_subdirs = _coerce_bool(item.get("use_product_subdirs"), False)
        use_orbit_subdir = _coerce_bool(item.get("use_orbit_subdir"), False)
        layout = _download_archive_layout(kind, item)
        out.append(
            {
                "id": task_id[:240],
                "name": name[:120],
                "status": status[:40],
                "detail": detail[:2000],
                "ts": ts,
                "kind": kind[:40],
                "output_dir": output_dir[:500],
                "total": total,
                "concurrency": concurrency,
                "use_product_subdirs": use_product_subdirs,
                "use_orbit_subdir": use_orbit_subdir,
                "download_layout": layout[:40],
                "logs": logs,
            }
        )
    return out


def _normalise_download_archive_path(value: object) -> str:
    return str(value or "").strip().replace("/", "\\").rstrip("\\").lower()


def _download_archive_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").strip()
    task_id = str(item.get("id") or "").strip()
    name = str(item.get("name") or "").strip()
    if not kind:
        if task_id.startswith("asf:") or "ASF" in name.upper():
            kind = "asf"
        elif task_id.startswith("orbit:") or "ORBIT" in name.upper() or "POEORB" in name.upper():
            kind = "orbit"
        elif task_id.startswith("dem:") or "DEM" in name.upper():
            kind = "dem"
    return kind


def _download_archive_path_from_task_id(kind: str, task_id: str) -> str:
    if not kind or not task_id.startswith(f"{kind}:"):
        return ""
    body = task_id[len(kind) + 1 :].strip()
    if not body:
        return ""
    if kind == "dem" and body.count(":") >= 2:
        body = body.rsplit(":", 2)[0]
    elif kind in {"asf", "orbit"}:
        parts = body.rsplit(":", 2)
        if (
            len(parts) == 3
            and parts[1] in {"flat", "product_subdirs", "orbit_subdir"}
            and parts[2].isdigit()
        ):
            body = parts[0]
        elif ":" in body:
            body = body.rsplit(":", 1)[0]
    elif ":" in body:
        body = body.rsplit(":", 1)[0]
    path = _normalise_download_archive_path(body)
    if path and Path(path).suffix.lower() in {".json", ".csv", ".txt", ".log"}:
        path = _normalise_download_archive_path(Path(path).parent)
    return path


def _download_archive_identity(item: dict[str, Any]) -> str:
    """Return the stable identity for a persisted task record."""
    kind = _download_archive_kind(item)
    task_id = str(item.get("id") or "").strip()
    if kind == "dem" and task_id:
        return task_id
    output_dir = _normalise_download_archive_path(item.get("output_dir"))
    if not output_dir:
        output_dir = _download_archive_path_from_task_id(kind, task_id)
    if kind and output_dir:
        layout = _download_archive_layout(kind, item)
        return f"{kind}:{output_dir}:{layout}" if layout else f"{kind}:{output_dir}"
    return task_id


def _download_archive_identity_candidates(
    item: dict[str, Any],
    *,
    include_legacy: bool = False,
) -> set[str]:
    kind = _download_archive_kind(item)
    task_id = str(item.get("id") or "").strip()
    output_dir = _normalise_download_archive_path(item.get("output_dir"))
    keys = {_download_archive_identity(item)}
    if task_id:
        keys.add(task_id)
    if kind and output_dir:
        layout = _download_archive_layout(kind, item)
        if layout:
            keys.add(f"{kind}:{output_dir}:{layout}")
        if include_legacy:
            keys.add(f"{kind}:{output_dir}")
    id_path = _download_archive_path_from_task_id(kind, task_id)
    if kind and id_path:
        layout = _download_archive_layout(kind, item)
        if layout:
            keys.add(f"{kind}:{id_path}:{layout}")
        if include_legacy:
            keys.add(f"{kind}:{id_path}")
    return {key[:600] for key in keys if key}


def _download_archive_is_deleted(item: dict[str, Any], deleted_keys: set[str]) -> bool:
    return bool(_download_archive_identity_candidates(item, include_legacy=True) & deleted_keys)


def _clean_download_archive_deleted_keys(value: Any) -> set[str]:
    """Return persisted archive tombstones."""
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value[:240]:
        key = str(item or "").strip()
        if key:
            out.add(key[:600])
    return out


def _deleted_download_archive_keys_from_items(value: Any) -> set[str]:
    """Extract tombstones from old archive rows saved with status=deleted."""
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value[:120]:
        if not isinstance(item, dict) or str(item.get("status") or "") != "deleted":
            continue
        candidate = {**item, "status": "cancelled"}
        cleaned = _clean_download_archive([candidate])
        if cleaned:
            out.update(_download_archive_identity_candidates(cleaned[0], include_legacy=True))
    return out


def _filter_deleted_download_archive(
    items: list[dict[str, Any]],
    deleted_keys: set[str],
) -> list[dict[str, Any]]:
    """Remove records the user explicitly deleted from history."""
    if not deleted_keys:
        return items
    return [item for item in items if not _download_archive_is_deleted(item, deleted_keys)]


def _download_archive_status_rank(item: dict[str, Any]) -> int:
    """Prefer terminal records over stale queue records when timestamps tie."""
    status = str(item.get("status") or "")
    if status in {"finished", "failed", "cancelled", "interrupted", "timeout"}:
        return 4
    if status == "paused":
        return 3
    if status == "running":
        return 2
    return 1


def _dedupe_download_archive(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate records for the same task, keeping the newest one."""
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _download_archive_identity(item)
        if not key:
            continue
        prev = by_key.get(key)
        item_ts = int(item.get("ts") or 0)
        prev_ts = int(prev.get("ts") or 0) if prev is not None else -1
        if (
            prev is None
            or item_ts > prev_ts
            or (
                item_ts == prev_ts
                and _download_archive_status_rank(item) > _download_archive_status_rank(prev)
            )
        ):
            by_key[key] = item
    return sorted(by_key.values(), key=lambda row: int(row.get("ts") or 0), reverse=True)[:40]


def _normalise_download_archive_for_startup(value: Any) -> list[dict[str, Any]]:
    """Convert stale running records from a previous process into interrupted records."""
    items = _clean_download_archive(value)
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("status") == "running":
            logs = list(item.get("logs") or [])
            logs.append("应用上次关闭时任务仍在运行；可重新开始同一输出目录以断点续传。")
            item = {
                **item,
                "status": "interrupted",
                "detail": f"上次关闭时仍在运行：{item.get('detail') or ''}".strip(),
                "logs": logs[-120:],
            }
        out.append(item)
    return _dedupe_download_archive(out)


def _merge_download_archive(
    incoming: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge UI-submitted task history with backend history without dropping rows."""
    return _dedupe_download_archive([*incoming, *existing])


def _normalise_downloadable_dem_dataset(value: Any, *, fallback: str = "COP30") -> str:
    """Keep the session DEM dataset on an OpenTopography-downloadable source."""
    name = str(value or "").strip().upper()
    try:
        from insar_prep.providers.dem.downloader import opentopo_demtype
    except Exception:  # noqa: BLE001 - fallback is safer than persisting USER_LOCAL
        return name or fallback
    if name and opentopo_demtype(name) is not None:
        return name
    return fallback


def _is_desktop_selftest_snapshot(data: Any) -> bool:
    """Detect old smoke-test state accidentally written to the real app profile."""
    if not isinstance(data, dict):
        return False
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        return False
    settings = workspace.get("global_settings")
    if not isinstance(settings, dict) or settings.get("display_name") != "selftest":
        return False
    projects = workspace.get("projects")
    if not isinstance(projects, list) or len(projects) != 1:
        return False
    project = projects[0]
    if not isinstance(project, dict) or project.get("project_name") != "p":
        return False
    regions = project.get("regions")
    if not isinstance(regions, list) or len(regions) != 1:
        return False
    region = regions[0]
    if not isinstance(region, dict) or region.get("region_name") != "r":
        return False
    scenes = region.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 1:
        return False
    scene = scenes[0]
    return (
        isinstance(scene, dict)
        and scene.get("scene_id")
        == "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C"
    )


def _is_empty_legacy_default_snapshot(data: Any) -> bool:
    """Detect old blank snapshots that only contain prefilled default settings."""
    if not isinstance(data, dict):
        return False
    if data.get("workspace") is not None:
        return False
    if data.get("current_project_id") or data.get("current_region_id"):
        return False
    settings = data.get("network_settings")
    if not isinstance(settings, dict):
        return False
    cache_dir = str(settings.get("cache_dir") or "").replace("/", "\\")
    return (
        str(settings.get("proxy_url") or "") == "http://127.0.0.1:10808"
        and bool(settings.get("cache_enabled")) is True
        and int(settings.get("cache_limit_mb") or 0) == 5120
        and cache_dir.endswith("\\InSAR Assistant\\cache")
    )


class Api:
    """The object exposed to the web UI as ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._state = GuiState()
        # The DEM dataset is chosen once (in the download step); the vertical-datum
        # conversion is then auto-detected from it, never chosen by the user.
        self._dem_dataset = "COP30"
        self._asf_download = AsfDownloadManager()
        self._orbit_download = OrbitDownloadJob()
        self._dem_download = DemDownloadJob()
        self._activity = ActivityLog()
        self._download_archive: list[dict[str, Any]] = []
        self._deleted_archive_keys: set[str] = set()
        self._standalone_scenes: list[Any] = []
        self._orbit_candidate_scenes: list[Any] = []
        self._last_orbit_report: Any | None = None
        self._metadata_status: dict[str, Any] = self._idle_metadata_status()
        self._asf_search_cancel = threading.Event()
        self._network_settings = self._default_network_settings()
        self._ui_flags: dict[str, bool] = {}
        self._applied_proxy_url: str | None = None
        self._earthdata_auth_failure_until = 0.0
        self._earthdata_auth_failure_cache: dict[str, Any] | None = None
        self._earthdata_auth_success_until = 0.0
        self._earthdata_auth_success_cache: dict[str, Any] | None = None
        self._earthdata_candidate_failure_until: dict[str, float] = {}
        self._earthdata_candidate_failure_message: dict[str, str] = {}
        self._window_maximized = False
        self._window_restore_bounds: dict[str, int] | None = None
        self._shutdown_started = False
        self._state_path = self._desktop_state_path()
        self._load_state()
        self._apply_network_settings()

    @staticmethod
    def _desktop_state_path() -> Path:
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "InSAR Assistant" / "desktop_state.json"

    @staticmethod
    def _windows_work_area() -> tuple[int, int, int, int] | None:
        """Return the Windows work area so frameless maximize does not cover the taskbar."""
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes  # noqa: PLC0415

            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = Rect()
            ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            if not ok:
                return None
            width = max(100, int(rect.right - rect.left))
            height = max(100, int(rect.bottom - rect.top))
            return int(rect.left), int(rect.top), width, height
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _normalise_window_work_area(value: object) -> tuple[int, int, int, int] | None:
        if not isinstance(value, dict):
            return None
        try:
            left = int(round(float(value.get("x", 0))))
            top = int(round(float(value.get("y", 0))))
            width = int(round(float(value.get("width", 0))))
            height = int(round(float(value.get("height", 0))))
        except (TypeError, ValueError):
            return None
        if width < 400 or height < 300:
            return None
        return left, top, width, height

    @staticmethod
    def _default_cache_dir() -> Path:
        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / "InSAR Assistant" / "cache"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Caches" / "InSAR Assistant"
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        return Path(base) / "insar-assistant"

    @classmethod
    def _normalise_network_settings(cls, settings: dict | None = None) -> dict:
        merged = {**cls._default_network_settings(), **(settings or {})}
        default_cache = cls._default_cache_dir()
        cache_dir = str(merged.get("cache_dir") or "").strip()
        legacy_default = str(Path("C:/InSAR/insar_assistant_cache")).replace("/", "\\").lower()
        normalised_cache = cache_dir.replace("/", "\\").rstrip("\\").lower()
        if not cache_dir or normalised_cache == legacy_default:
            cache_dir = str(default_cache)
        merged["cache_dir"] = cache_dir
        merged["cache_enabled"] = True
        try:
            merged["cache_limit_mb"] = max(0, int(merged.get("cache_limit_mb") or 10240))
        except (TypeError, ValueError):
            merged["cache_limit_mb"] = 10240
        return merged

    def _load_state(self) -> None:
        """Restore the last desktop workspace snapshot, if it exists."""
        if not self._state_path.exists():
            return
        try:
            from insar_prep.core.models import Workspace

            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if _is_desktop_selftest_snapshot(data) or _is_empty_legacy_default_snapshot(data):
                try:
                    self._state_path.unlink()
                except OSError:
                    pass
                self._activity.add("已清理旧版空白默认状态，启动为空白工作台。", kind="warning")
                return
            workspace = data.get("workspace")
            if workspace:
                self._state.workspace = Workspace.model_validate(workspace)
                self._state.current_project_id = data.get("current_project_id")
                self._state.current_region_id = data.get("current_region_id")
            dataset = data.get("dem_dataset")
            if isinstance(dataset, str) and dataset.strip():
                self._dem_dataset = _normalise_downloadable_dem_dataset(dataset)
            settings = data.get("network_settings")
            if isinstance(settings, dict):
                self._network_settings = self._normalise_network_settings(settings)
            flags = data.get("ui_flags")
            if isinstance(flags, dict):
                self._ui_flags = {
                    str(key): bool(value)
                    for key, value in flags.items()
                    if isinstance(key, str)
                }
            self._deleted_archive_keys = _clean_download_archive_deleted_keys(
                data.get("download_archive_deleted_keys")
            )
            self._deleted_archive_keys.update(
                _deleted_download_archive_keys_from_items(data.get("download_archive"))
            )
            self._download_archive = _filter_deleted_download_archive(
                _normalise_download_archive_for_startup(data.get("download_archive")),
                self._deleted_archive_keys,
            )
        except Exception as exc:  # noqa: BLE001 - corrupt snapshots should not break startup
            self._activity.add(f"本地项目状态恢复失败：{exc}", kind="warning")

    def _save_state(self) -> None:
        """Persist the current project tree so projects survive app restarts."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "workspace": self._state.workspace.model_dump(mode="json")
                if self._state.workspace is not None
                else None,
                "current_project_id": self._state.current_project_id,
                "current_region_id": self._state.current_region_id,
                "dem_dataset": self._dem_dataset,
                "network_settings": self._network_settings,
                "ui_flags": self._ui_flags,
                "download_archive": _filter_deleted_download_archive(
                    _clean_download_archive(self._download_archive),
                    self._deleted_archive_keys,
                ),
                "download_archive_deleted_keys": sorted(self._deleted_archive_keys)[-200:],
            }
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 - persistence is helpful, not fatal
            self._activity.add(f"本地项目状态保存失败：{exc}", kind="warning")

    def _act(self, text: str, *, kind: str = "info") -> None:
        self._activity.add(text, kind=kind)

    @staticmethod
    def _default_network_settings() -> dict:
        default_cache = Api._default_cache_dir()
        return {
            "proxy_enabled": False,
            "proxy_url": "",
            "cache_enabled": True,
            "cache_dir": str(default_cache),
            "cache_limit_mb": 10240,
            "tianditu_token": "",
            "asf_ssl_verify": True,
        }

    def _apply_network_settings(self) -> None:
        settings = self._network_settings
        proxy = str(settings.get("proxy_url") or "").strip()
        proxy_keys = (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
        for key in proxy_keys:
            os.environ.pop(key, None)
        self._applied_proxy_url = None
        if bool(settings.get("proxy_enabled")) and proxy:
            for key in proxy_keys:
                os.environ[key] = proxy
            self._applied_proxy_url = proxy
        cache_dir = str(settings.get("cache_dir") or "").strip()
        if bool(settings.get("cache_enabled")) and cache_dir:
            try:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._activity.add(f"缓存目录创建失败：{exc}", kind="warning")

    def _asf_search_cache_root(self) -> Path | None:
        settings = self._normalise_network_settings(self._network_settings)
        if not bool(settings.get("cache_enabled", True)):
            return None
        cache_dir = str(settings.get("cache_dir") or "").strip()
        if not cache_dir:
            return None
        return Path(cache_dir) / "asf_search"

    @staticmethod
    def _asf_search_cache_filter(value: object) -> str:
        parts = [
            item.strip().upper()
            for item in str(value or "").replace(";", ",").split(",")
            if item.strip()
        ]
        return ",".join(sorted(dict.fromkeys(parts)))

    @staticmethod
    def _asf_search_cache_date(value: object) -> str:
        return str(value or "").strip().replace("/", "-")

    @staticmethod
    def _asf_search_cache_bbox(bbox: Any) -> dict[str, Any] | None:
        if bbox is None:
            return None
        try:
            return {
                "west": round(float(getattr(bbox, "west")), 7),
                "east": round(float(getattr(bbox, "east")), 7),
                "south": round(float(getattr(bbox, "south")), 7),
                "north": round(float(getattr(bbox, "north")), 7),
                "crs": str(getattr(bbox, "crs", "EPSG:4326") or "EPSG:4326"),
            }
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _asf_search_cache_aoi_hash(aoi_geojson: Any) -> str:
        if not isinstance(aoi_geojson, dict):
            return ""

        def normalise(value: Any) -> Any:
            if isinstance(value, float):
                return round(value, 7)
            if isinstance(value, int) or value is None or isinstance(value, str):
                return value
            if isinstance(value, list):
                return [normalise(item) for item in value]
            if not isinstance(value, dict):
                return value
            obj_type = str(value.get("type") or "")
            if obj_type == "Feature":
                return normalise(value.get("geometry"))
            if obj_type == "FeatureCollection":
                return {
                    "type": "FeatureCollection",
                    "features": [
                        normalise(item.get("geometry") if isinstance(item, dict) and item.get("type") == "Feature" else item)
                        for item in value.get("features", [])
                        if isinstance(item, dict)
                    ],
                }
            if obj_type == "GeometryCollection":
                return {
                    "type": "GeometryCollection",
                    "geometries": [
                        normalise(item)
                        for item in value.get("geometries", [])
                        if isinstance(item, dict)
                    ],
                }
            if obj_type:
                return {
                    "type": obj_type,
                    "coordinates": normalise(value.get("coordinates")),
                }
            return {str(key): normalise(item) for key, item in sorted(value.items())}

        raw = json.dumps(normalise(aoi_geojson), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _asf_cache_value_set(value: object) -> set[str]:
        return {
            item.strip().upper()
            for item in str(value or "").replace(";", ",").split(",")
            if item.strip()
        }

    @staticmethod
    def _asf_cache_int_ranges(value: object) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        text = str(value or "").strip()
        if not text:
            return ranges
        for part in re.split(r"[,;]", text):
            item = part.strip()
            if not item:
                continue
            match = re.fullmatch(r"(\d+)(?:\s*[-:]\s*(\d+))?", item)
            if not match:
                continue
            start = int(match.group(1))
            end = int(match.group(2) or start)
            ranges.append((min(start, end), max(start, end)))
        return ranges

    @staticmethod
    def _asf_cache_ranges_cover(cached: object, requested: object) -> bool:
        requested_ranges = Api._asf_cache_int_ranges(requested)
        cached_ranges = Api._asf_cache_int_ranges(cached)
        if not requested_ranges:
            return not cached_ranges
        if not cached_ranges:
            return True
        return all(
            any(cached_start <= req_start and cached_end >= req_end for cached_start, cached_end in cached_ranges)
            for req_start, req_end in requested_ranges
        )

    @staticmethod
    def _asf_cache_filter_covers(cached: object, requested: object) -> bool:
        requested_values = Api._asf_cache_value_set(requested)
        cached_values = Api._asf_cache_value_set(cached)
        if not requested_values:
            return not cached_values
        if not cached_values:
            return True
        return requested_values.issubset(cached_values)

    @staticmethod
    def _asf_cache_date_covers(cached_start: object, cached_end: object, requested_start: object, requested_end: object) -> bool:
        c_start = Api._asf_search_cache_date(cached_start)
        c_end = Api._asf_search_cache_date(cached_end)
        r_start = Api._asf_search_cache_date(requested_start)
        r_end = Api._asf_search_cache_date(requested_end)
        if not r_start and c_start:
            return False
        if not r_end and c_end:
            return False
        if c_start and r_start and c_start > r_start:
            return False
        if c_end and r_end and c_end < r_end:
            return False
        return True

    @staticmethod
    def _asf_cache_query_covers(cached: dict[str, Any], requested: dict[str, Any]) -> bool:
        if cached.get("version") != requested.get("version"):
            return False
        if cached.get("dataset") != requested.get("dataset"):
            return False
        if cached.get("bbox") != requested.get("bbox"):
            return False
        if cached.get("aoi") != requested.get("aoi"):
            return False
        if cached.get("product_type") != requested.get("product_type"):
            return False
        if not Api._asf_cache_date_covers(cached.get("start"), cached.get("end"), requested.get("start"), requested.get("end")):
            return False
        for name in ("beam_mode", "polarization", "orbit_direction"):
            if not Api._asf_cache_filter_covers(cached.get(name), requested.get(name)):
                return False
        return Api._asf_cache_ranges_cover(cached.get("relative_orbit"), requested.get("relative_orbit")) and Api._asf_cache_ranges_cover(
            cached.get("frame"), requested.get("frame")
        )

    def _asf_search_cache_target(
        self,
        *,
        bbox: Any,
        aoi_geojson: Any,
        payload: dict[str, Any],
        relative_orbit: str | None,
        frame: str | None,
    ) -> tuple[str, Path | None, dict[str, Any]]:
        key_payload = {
            "version": 1,
            "dataset": "SENTINEL-1",
            "bbox": self._asf_search_cache_bbox(bbox),
            "aoi": self._asf_search_cache_aoi_hash(aoi_geojson),
            "start": self._asf_search_cache_date(payload.get("start")),
            "end": self._asf_search_cache_date(payload.get("end")),
            "product_type": self._asf_search_cache_filter(payload.get("product_type") or "SLC"),
            "beam_mode": self._asf_search_cache_filter(payload.get("beam_mode") or "IW"),
            "polarization": self._asf_search_cache_filter(payload.get("polarization")),
            "orbit_direction": self._asf_search_cache_filter(payload.get("orbit_direction")),
            "relative_orbit": relative_orbit,
            "frame": frame,
        }
        raw = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        root = self._asf_search_cache_root()
        return digest, (root / f"{digest}.json" if root is not None else None), key_payload

    @staticmethod
    def _asf_search_cache_max_age_seconds() -> int:
        return 7 * 24 * 60 * 60

    def _load_asf_search_cache(
        self,
        cache_key: str,
        cache_path: Path | None,
    ) -> dict[str, Any] | None:
        if cache_path is None or not cache_path.is_file():
            return None
        return self._load_asf_search_cache_file(cache_path, expected_key=cache_key)

    def _load_asf_search_cache_file(
        self,
        cache_path: Path,
        *,
        expected_key: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            from insar_prep.core.models import Scene

            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if expected_key is not None and data.get("cache_key") != expected_key:
                return None
            updated_at = float(data.get("updated_at") or data.get("created_at") or 0)
            if updated_at and time.time() - updated_at > self._asf_search_cache_max_age_seconds():
                return None
            scenes = [
                Scene.model_validate(item)
                for item in data.get("scenes", [])
                if isinstance(item, dict)
            ]
            if not scenes:
                return None
            return {
                "scenes": _sort_scenes_by_acquisition_date(scenes),
                "total_count": data.get("total_count"),
                "source": data.get("source") or "ASF",
                "complete": bool(data.get("complete")),
                "cache_key": data.get("cache_key"),
                "query": data.get("query") if isinstance(data.get("query"), dict) else {},
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "path": str(cache_path),
            }
        except Exception as exc:  # noqa: BLE001
            self._activity.add(f"ASF 检索缓存读取失败，已忽略：{exc}", kind="warning")
            return None

    def _find_covering_asf_search_cache(
        self,
        requested_query: dict[str, Any],
        requested_limit: int | None,
        exact_path: Path | None,
    ) -> dict[str, Any] | None:
        root = self._asf_search_cache_root()
        if root is None or not root.is_dir():
            return None
        candidates: list[dict[str, Any]] = []
        for cache_path in root.glob("*.json"):
            if exact_path is not None and cache_path == exact_path:
                continue
            entry = self._load_asf_search_cache_file(cache_path)
            if entry is None:
                continue
            query = entry.get("query") if isinstance(entry.get("query"), dict) else {}
            if not self._asf_cache_query_covers(query, requested_query):
                continue
            filtered = self._cached_asf_scenes_for_limit(entry, requested_limit, requested_query)
            if filtered is None:
                continue
            candidates.append({**entry, "scenes": filtered})
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                bool(item.get("complete")),
                len(item.get("scenes") or []),
                float(item.get("updated_at") or 0),
            ),
        )

    @staticmethod
    def _cached_asf_scenes_for_limit(
        entry: dict[str, Any] | None,
        requested_limit: int | None,
        requested_query: dict[str, Any] | None = None,
    ) -> list[Any] | None:
        if entry is None:
            return None
        scenes = Api._filter_cached_asf_scenes(list(entry.get("scenes") or []), requested_query or {})
        if not scenes:
            return None
        if requested_limit is None:
            return scenes if bool(entry.get("complete")) else None
        if len(scenes) < requested_limit:
            return None
        return scenes[:requested_limit]

    @staticmethod
    def _filter_cached_asf_scenes(scenes: list[Any], query: dict[str, Any]) -> list[Any]:
        if not query:
            return scenes

        def text(value: object) -> str:
            return str(value or "").strip().upper()

        def scene_date(scene: Any) -> str:
            value = getattr(scene, "acquisition_datetime", None)
            return str(value or "")[:10].replace("/", "-")

        def int_value(value: object) -> int | None:
            try:
                if value is None or value == "":
                    return None
                return int(float(str(value)))
            except (TypeError, ValueError):
                return None

        def in_ranges(value: object, ranges: list[tuple[int, int]]) -> bool:
            if not ranges:
                return True
            number = int_value(value)
            if number is None:
                return False
            return any(start <= number <= end for start, end in ranges)

        start = Api._asf_search_cache_date(query.get("start"))
        end = Api._asf_search_cache_date(query.get("end"))
        beam_values = Api._asf_cache_value_set(query.get("beam_mode"))
        pol_values = Api._asf_cache_value_set(query.get("polarization"))
        orbit_values = Api._asf_cache_value_set(query.get("orbit_direction"))
        path_ranges = Api._asf_cache_int_ranges(query.get("relative_orbit"))
        frame_ranges = Api._asf_cache_int_ranges(query.get("frame"))
        product_type = text(query.get("product_type"))

        out = []
        for scene in scenes:
            acquired = scene_date(scene)
            if start and acquired and acquired < start:
                continue
            if end and acquired and acquired > end:
                continue
            if product_type and text(getattr(scene, "product_type", "")) != product_type:
                continue
            if beam_values and text(getattr(scene, "beam_mode", "")) not in beam_values:
                continue
            if pol_values and text(getattr(scene, "polarization", "")) not in pol_values:
                continue
            if orbit_values and text(getattr(scene, "orbit_direction", "")) not in orbit_values:
                continue
            if not in_ranges(getattr(scene, "relative_orbit", None) or getattr(scene, "path", None), path_ranges):
                continue
            if not in_ranges(getattr(scene, "frame", None), frame_ranges):
                continue
            out.append(scene)
        return _sort_scenes_by_acquisition_date(out)

    def _write_asf_search_cache(
        self,
        *,
        cache_key: str,
        cache_path: Path | None,
        key_payload: dict[str, Any],
        scenes: list[Any],
        stats: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> None:
        if cache_path is None or not scenes:
            return
        if str(stats.get("source") or "ASF").upper() not in {"ASF", "ASF_BATCH"}:
            return
        try:
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes

            previous = list(existing.get("scenes") or []) if existing else []
            merged, _ = deduplicate_scenes([*previous, *scenes])
            merged = _sort_scenes_by_acquisition_date(merged)
            total_count = stats.get("total_count")
            try:
                total_int = int(total_count) if total_count is not None else None
            except (TypeError, ValueError):
                total_int = None
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            now = int(time.time())
            created_at = existing.get("created_at") if existing else None
            payload = {
                "version": 1,
                "cache_key": cache_key,
                "query": key_payload,
                "source": "ASF",
                "created_at": created_at or now,
                "updated_at": now,
                "total_count": total_int,
                "complete": bool(total_int is not None and len(merged) >= total_int),
                "scenes": [scene.model_dump(mode="json") for scene in merged],
            }
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._activity.add(f"ASF 检索缓存写入失败，已跳过：{exc}", kind="warning")

    def _default_workspace_root(self) -> Path:
        """Return the low-friction workspace root used for direct AOI/SAR actions."""
        return Path("C:/InSAR/projects")

    def _ensure_current_region(self) -> Any:
        """Create a minimal default workspace/project/region when the user starts with AOI.

        The workbench intentionally lets users begin from a map selection without
        understanding the old project tree first. Core state still needs a region
        object, so this helper prepares one quietly and keeps existing selections
        untouched whenever they already exist.
        """
        if self._state.workspace is None:
            root = self._default_workspace_root()
            self._state.create_workspace(root, "默认工作区")

        project = self._state.current_project()
        if project is None:
            if self._state.workspace and self._state.workspace.projects:
                project = self._state.select_project(self._state.workspace.projects[0].project_id)
            else:
                project = self._state.add_project("default_task")

        region = self._state.current_region()
        if region is None:
            if project.regions:
                region = self._state.select_region(project.regions[0].region_id)
            else:
                region = self._state.add_region("default_area")
        return region

    def get_network_settings(self) -> dict:
        """Return proxy/cache/map-token settings used by the desktop shell."""
        return {"ok": True, **self._network_settings}

    def save_network_settings(self, settings: dict | None = None) -> dict:
        """Persist network, proxy and cache preferences for future requests."""
        incoming = settings or {}
        current = self._normalise_network_settings(self._network_settings)

        proxy_enabled = bool(incoming.get("proxy_enabled", current["proxy_enabled"]))
        proxy_url = _normalise_proxy_url(incoming.get("proxy_url", current["proxy_url"]))
        proxy_auto_detected = False
        if proxy_enabled and not proxy_url:
            proxy_url = _detect_system_proxy()
            proxy_auto_detected = bool(proxy_url)
        cache_dir = str(incoming.get("cache_dir", current["cache_dir"]) or "").strip()
        if not cache_dir:
            cache_dir = str(self._default_cache_dir())
        tianditu_token = str(incoming.get("tianditu_token", current["tianditu_token"]) or "").strip()
        previous_tianditu_token = str(current.get("tianditu_token") or "").strip()
        try:
            cache_limit = int(incoming.get("cache_limit_mb", current["cache_limit_mb"]) or 0)
        except (TypeError, ValueError):
            return _error_msg("缓存容量必须是数字", "GUI003")
        if tianditu_token and tianditu_token != previous_tianditu_token:
            results, error = _search_tianditu_admin_boundaries(
                token=tianditu_token,
                candidates=["北京市"],
                limit=1,
            )
            if not results:
                return _error_msg(
                    f"天地图 Key 校验失败，网络与缓存设置未保存：{mask_text(error or '未返回行政边界数据')}",
                    "GUI003",
                )

        self._network_settings = {
            "proxy_enabled": proxy_enabled,
            "proxy_url": proxy_url,
            "cache_enabled": True,
            "cache_dir": cache_dir,
            "cache_limit_mb": max(0, cache_limit),
            "tianditu_token": tianditu_token,
            "asf_ssl_verify": bool(incoming.get("asf_ssl_verify", current["asf_ssl_verify"])),
        }
        if cache_dir:
            try:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return _error_msg(f"无法创建缓存目录：{exc}", "GUI003")
        self._apply_network_settings()
        self._clear_earthdata_auth_failure()
        self._save_state()
        if proxy_enabled and proxy_auto_detected:
            self._act(f"已自动使用系统代理：{proxy_url}", kind="settings")
        elif proxy_enabled and not proxy_url:
            self._act("已启用代理，但未填写代理地址，也未检测到系统代理", kind="warning")
        else:
            self._act("已保存网络代理与缓存设置", kind="settings")
        return self.get_network_settings()

    def get_activity(self, limit: int = 12) -> dict:
        """Return recent in-session actions for the overview feed."""
        return self._activity.list(limit=limit)

    def get_ui_flags(self) -> dict:
        """Return small persistent UI flags, such as first-run guide state."""
        return {"ok": True, "flags": dict(self._ui_flags)}

    def set_ui_flag(self, key: str, value: bool = True) -> dict:
        """Persist a small UI flag without touching user data or credentials."""
        name = str(key or "").strip()
        if not name:
            return _error_msg("UI 标记名称不能为空。", "GUI003")
        self._ui_flags[name] = bool(value)
        self._save_state()
        return self.get_ui_flags()

    def get_download_archive(self) -> dict:
        """Return persisted download/task history across app restarts."""
        return {
            "ok": True,
            "items": _dedupe_download_archive(
                _filter_deleted_download_archive(
                    _clean_download_archive(self._download_archive),
                    self._deleted_archive_keys,
                )
            ),
        }

    def _upsert_download_archive_item(self, item: dict[str, Any]) -> None:
        cleaned = _clean_download_archive([item])
        if not cleaned:
            return
        next_item = cleaned[0]
        next_keys = _download_archive_identity_candidates(next_item)
        if next_keys & self._deleted_archive_keys:
            return
        previous = next(
            (
                old
                for old in self._download_archive
                if _download_archive_identity_candidates(old) & next_keys
            ),
            None,
        )
        if previous is not None:
            same = all(
                previous.get(key) == next_item.get(key)
                for key in ("name", "status", "detail", "logs")
            )
            if same:
                return
            if previous.get("status") == "paused" and next_item.get("status") == "paused":
                next_item["ts"] = previous.get("ts") or next_item["ts"]
        self._download_archive = _dedupe_download_archive([
            next_item,
            *(
                old
                for old in self._download_archive
                if not (_download_archive_identity_candidates(old) & next_keys)
            ),
        ])
        self._save_state()

    def _forget_deleted_archive_key(
        self,
        kind: str,
        output_dir: str,
        *,
        use_product_subdirs: bool = False,
        use_orbit_subdir: bool = False,
    ) -> None:
        """Allow an explicitly started new task to reuse a previously deleted slot."""
        cleaned = _clean_download_archive(
            [
                {
                    "id": f"{kind}:{output_dir}:0",
                    "name": kind,
                    "status": "running",
                    "detail": "new task",
                    "ts": int(time.time() * 1000),
                    "kind": kind,
                    "output_dir": output_dir,
                    "use_product_subdirs": use_product_subdirs,
                    "use_orbit_subdir": use_orbit_subdir,
                }
            ]
        )
        if cleaned:
            keys = _download_archive_identity_candidates(cleaned[0], include_legacy=True)
            stable_path = _normalise_download_archive_path(output_dir)
            stable_prefixes = {f"{kind}:{stable_path}"} if stable_path else set()
            self._deleted_archive_keys.difference_update(keys)
            for prefix in stable_prefixes:
                self._deleted_archive_keys = {
                    key
                    for key in self._deleted_archive_keys
                    if key != prefix
                    and not key.startswith(f"{prefix}:")
                    and not key.startswith(f"{prefix}\\")
                }

    def _archive_asf_status(self, status: dict[str, Any]) -> None:
        tasks = status.get("asf_tasks")
        if isinstance(tasks, list) and tasks:
            for task in tasks:
                if isinstance(task, dict):
                    self._archive_asf_status(task)
            return
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "paused", "finished", "failed", "cancelled", "interrupted"}:
            return
        active = status.get("active_downloads")
        active_names = ""
        if isinstance(active, list):
            active_names = "；".join(
                str(item.get("scene_id") or "")
                for item in active[: int(status.get("concurrency") or 1)]
                if isinstance(item, dict) and item.get("scene_id")
            )
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or (f"正在下载：{active_names}" if active_names else "")
            or f"{int(status.get('done') or 0)}/{int(status.get('total') or 0)}"
        )
        logs = [
            _format_status_log_entry(entry)
            for entry in (status.get("log") or [])
            if isinstance(entry, dict) and entry.get("detail")
        ]
        archive_key = status.get("results_path") or status.get("output_dir") or "active"
        self._upsert_download_archive_item(
            {
                "id": f"asf:{archive_key}:{int(status.get('total') or 0)}",
                "name": "Sentinel-1 下载任务",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "asf",
                "output_dir": str(status.get("output_dir") or ""),
                "total": int(status.get("total") or 0),
                "concurrency": int(status.get("concurrency") or 0),
                "use_product_subdirs": _coerce_bool(status.get("use_product_subdirs"), False),
                "download_layout": str(status.get("download_layout") or "flat"),
                "logs": logs,
            }
        )

    def _archive_orbit_status(self, status: dict[str, Any]) -> None:
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "paused", "finished", "failed", "cancelled", "interrupted"}:
            return
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or (
                f"正在处理：{status.get('current_scene')}"
                if status.get("current_scene")
                else ""
            )
            or f"{int(status.get('done') or 0)}/{int(status.get('total') or 0)}"
        )
        logs = [
            _format_status_log_entry(entry)
            for entry in (status.get("log") or [])
            if isinstance(entry, dict) and entry.get("detail")
        ]
        archive_key = status.get("orbit_dir") or "active"
        self._upsert_download_archive_item(
            {
                "id": f"orbit:{archive_key}:{int(status.get('total') or 0)}",
                "name": "Sentinel-1 精密轨道下载",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "orbit",
                "output_dir": str(status.get("orbit_dir") or ""),
                "total": int(status.get("total") or 0),
                "use_orbit_subdir": _coerce_bool(status.get("use_orbit_subdir"), False),
                "download_layout": str(status.get("download_layout") or "flat"),
                "logs": logs,
            }
        )

    def _archive_dem_status(self, status: dict[str, Any]) -> None:
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "finished", "failed", "cancelled", "interrupted"}:
            return
        output_dir = str(status.get("output_dir") or "").strip()
        dataset = str(status.get("dataset") or "DEM").strip()
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or f"正在下载：{dataset}"
        )
        logs = [
            _format_status_log_entry(entry)
            for entry in (status.get("log") or [])
            if isinstance(entry, dict) and entry.get("detail")
        ]
        self._upsert_download_archive_item(
            {
                "id": f"dem:{output_dir or status.get('results_path') or dataset}:{int(status.get('total') or 1)}:{dataset}",
                "name": "DEM 下载并转换椭球高" if bool(status.get("convert")) else "DEM 下载",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "dem",
                "output_dir": output_dir,
                "total": int(status.get("total") or 1),
                "concurrency": 1,
                "logs": logs,
            }
        )

    def save_download_archive(self, items: list[dict[str, Any]] | None = None) -> dict:
        """Persist the UI download/task history."""
        incoming = _filter_deleted_download_archive(
            _clean_download_archive(items or [])[:40],
            self._deleted_archive_keys,
        )
        if not incoming and self._download_archive:
            return self.get_download_archive()
        self._download_archive = _merge_download_archive(
            incoming,
            _filter_deleted_download_archive(
                _clean_download_archive(self._download_archive),
                self._deleted_archive_keys,
            ),
        )
        self._save_state()
        return self.get_download_archive()

    def delete_download_archive_item(self, item: dict[str, Any] | None = None) -> dict:
        """Delete a persisted history record without touching output files."""
        cleaned = _clean_download_archive([item] if isinstance(item, dict) else [])
        if not cleaned:
            return _error_msg("Missing download history item", "GUI003")
        key = _download_archive_identity(cleaned[0])
        if not key:
            return _error_msg("Missing download history item identity", "GUI003")
        keys = _download_archive_identity_candidates(cleaned[0], include_legacy=True)
        self._deleted_archive_keys.update(keys)
        self._download_archive = [
            row
            for row in self._download_archive
            if not (_download_archive_identity_candidates(row) & keys)
        ]
        self._save_state()
        return self.get_download_archive()

    # ------------------------------------------------------------------ app
    def get_app_info(self) -> dict:
        """Return basic app identity (proves the JS<->Python bridge is live)."""
        return {
            "ok": True,
            "name": "InSAR Studio",
            "version": __version__,
            "offline": True,
        }

    def check_for_update(self, force: bool = False) -> dict:
        """Best-effort desktop update check against the public GitHub release."""
        try:
            from insar_prep.core.update_check import (
                check_for_update,
                maybe_check_for_update,
                preferred_release_asset,
                releases_page_url,
            )

            info = (
                check_for_update(timeout=10)
                if bool(force)
                else maybe_check_for_update(force=False, interval_seconds=60 * 60)
            )
            fallback_url = releases_page_url()
        except Exception as exc:  # noqa: BLE001 - update checks must never disturb startup
            return {
                "ok": True,
                "checked": False,
                "update_available": False,
                "current_version": __version__,
                "latest_version": __version__,
                "html_url": "https://github.com/hhanmj/insar_studio/releases/latest",
                "download_url": "",
                "asset_name": "",
                "asset_size": 0,
                "release_name": "",
                "changelog": "",
                "published_at": "",
                "online_update_supported": False,
                "install_mode": "manual",
                "message": f"暂时无法检查更新：{exc}",
            }
        if info is None:
            return {
                "ok": True,
                "checked": True,
                "update_available": False,
                "current_version": __version__,
                "latest_version": __version__,
                "html_url": fallback_url,
                "download_url": "",
                "asset_name": "",
                "asset_size": 0,
                "release_name": "",
                "changelog": "",
                "published_at": "",
                "online_update_supported": False,
                "install_mode": "manual",
                "message": "当前没有发现新版本，或暂时无法连接更新服务。",
            }
        asset = preferred_release_asset(info)
        install_mode = "manual"
        if asset is not None:
            name = asset.name.lower()
            install_mode = (
                "installer"
                if name.endswith((".exe", ".msi")) and ("setup" in name or "installer" in name)
                else "download"
            )
        return {
            "ok": True,
            "checked": True,
            "update_available": bool(info.update_available),
            "current_version": info.current_version,
            "latest_version": info.latest_version,
            "html_url": info.html_url,
            "download_url": asset.download_url if asset else "",
            "asset_name": asset.name if asset else "",
            "asset_size": asset.size if asset else 0,
            "release_name": info.release_name,
            "changelog": info.changelog,
            "published_at": info.published_at,
            "online_update_supported": asset is not None,
            "install_mode": install_mode,
            "message": (
                "发现新版本，可在软件内下载更新包；便携版仍需要关闭后替换，安装版可运行安装包覆盖升级。"
                if info.update_available
                else "当前已经是最新版本。"
            ),
        }

    def download_app_update(self, download_url: str = "", asset_name: str = "") -> dict:
        """Download the selected release asset into the user's cache directory."""
        url = str(download_url or "").strip()
        name = str(asset_name or "").strip()
        if not url:
            info = self.check_for_update(True)
            if not info.get("ok"):
                return info
            url = str(info.get("download_url") or "").strip()
            name = str(info.get("asset_name") or "").strip()
        if not url:
            return _error_msg("当前 Release 没有可直接下载的更新包。", "GUI003")
        try:
            import urllib.parse  # noqa: PLC0415
            import urllib.request  # noqa: PLC0415

            parsed = urllib.parse.urlparse(url)
            if parsed.scheme.lower() != "https":
                return _error_msg("更新包下载地址必须是 HTTPS。", "GUI003")
            if not name:
                name = Path(parsed.path).name or "InSAR-Studio-update.exe"
            safe_name = Path(name).name
            updates_dir = self._default_cache_dir() / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            dest = updates_dir / safe_name
            part = dest.with_suffix(dest.suffix + ".part")
            request = urllib.request.Request(  # noqa: S310 - HTTPS release asset URL.
                url,
                headers={"User-Agent": f"insar-prep/{__version__}"},
            )
            total = 0
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                with part.open("wb") as file:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        file.write(chunk)
                        total += len(chunk)
            part.replace(dest)
            is_installer = _is_update_installer(dest)
            launched = False
            message = "更新包已下载。请关闭软件后运行安装包或替换便携版 exe。"
            if is_installer:
                _launch_update_installer(dest)
                launched = True
                message = "安装器已下载并启动。若当前窗口没有自动关闭，请手动关闭后等待覆盖安装完成。"
            self._act(f"更新包已下载：{dest}", kind="settings")
            return {
                "ok": True,
                "path": str(dest),
                "folder": str(updates_dir),
                "size": total,
                "can_run": dest.suffix.lower() in {".exe", ".msi"},
                "launched": launched,
                "install_mode": "installer" if is_installer else "download",
                "message": message,
            }
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"下载更新包失败：{exc}", "NET001")

    def get_component_status(self, refresh: bool = False) -> dict:
        """Return optional runtime component status."""
        try:
            from insar_prep.core.component_manager import get_component_status

            return get_component_status(refresh=bool(refresh))
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"组件状态读取失败：{exc}", "GUI003")

    def install_component(self, component_id: str) -> dict:
        """Install an optional runtime component from the online manifest."""
        try:
            from insar_prep.core.component_manager import ComponentError, install_component

            return install_component(str(component_id or "").strip())
        except ComponentError as exc:
            return _error_msg(str(exc), "GUI003")
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"组件安装失败：{exc}", "NET001")

    def remove_component(self, component_id: str) -> dict:
        """Remove an optional runtime component."""
        try:
            from insar_prep.core.component_manager import remove_component

            return remove_component(str(component_id or "").strip())
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"组件移除失败：{exc}", "GUI003")

    def get_workflow_status(self) -> dict:
        """Return one dashboard-friendly snapshot of the current preparation flow.

        The React shell uses this as its single source of truth for the overview:
        it mirrors the task-console pattern from downloader tools while staying
        InSAR-specific (workspace -> AOI -> scenes -> DEM/GACOS -> report).
        It is read-only: no network, no downloads, no files are created.
        """
        ctx = self.get_context()
        region = self._state.current_region()
        dl = self._asf_download.get_status()
        creds = self.get_credential_status()

        has_workspace = ctx.get("workspace") is not None
        has_project = ctx.get("project") is not None
        has_region = region is not None
        has_aoi = bool(
            region is not None and region.aoi is not None and region.aoi.bbox is not None
        )
        scene_count = len(region.scenes) if region is not None else len(self._standalone_scenes)
        has_scenes = scene_count > 0
        dl_active = dl.get("state") in {"running", "paused"}
        dl_finished = dl.get("state") == "finished"
        credentials_ready = all(
            creds.get(key) not in {None, "none", "unavailable"}
            for key in ("earthdata", "opentopography", "gacos")
        )

        workspace_ready = has_workspace and has_project and has_region
        aoi_ready = workspace_ready and has_aoi
        scenes_ready = has_scenes

        stages = [
            {
                "id": "settings",
                "label": "设置",
                "nav": "settings",
                "status": "done" if credentials_ready else "active",
                "summary": "配置 Earthdata、OpenTopography 和 GACOS。",
                "ready": credentials_ready,
                "count": 1 if credentials_ready else 0,
            },
            {
                "id": "workspace",
                "label": "项目",
                "nav": "workspace",
                "status": "done" if workspace_ready else "active",
                "summary": "创建或选择当前项目和研究区。",
                "ready": workspace_ready,
                "count": 1 if workspace_ready else 0,
            },
            {
                "id": "aoi",
                "label": "AOI",
                "nav": "aoi",
                "status": "done" if aoi_ready else ("blocked" if not workspace_ready else "active"),
                "summary": "绘制或导入处理范围。",
                "ready": aoi_ready,
                "count": 1 if has_aoi else 0,
            },
            {
                "id": "scenes",
                "label": "影像",
                "nav": "download",
                "status": "done" if scenes_ready else "active",
                "summary": "导入 ASF 购物车或本地目录；AOI 可选绑定。",
                "ready": scenes_ready,
                "count": scene_count,
            },
            {
                "id": "downloads",
                "label": "下载",
                "nav": "download",
                "status": (
                    "running"
                    if dl_active
                    else ("done" if dl_finished else ("blocked" if not scenes_ready else "active"))
                ),
                "summary": "规划并执行 SLC、DEM 和 GACOS。",
                "ready": scenes_ready,
                "count": int(dl.get("done") or 0),
            },
            {
                "id": "convert",
                "label": "DEM 转换",
                "nav": "convert",
                "status": "blocked" if not aoi_ready else "active",
                "summary": "生成 SARscape 可用的椭球高 DEM。",
                "ready": aoi_ready,
                "count": 0,
            },
            {
                "id": "report",
                "label": "报告",
                "nav": "report",
                "status": "blocked" if not scenes_ready else "active",
                "summary": "生成报告、清单和警告表。",
                "ready": scenes_ready,
                "count": 0,
            },
        ]

        if not credentials_ready:
            next_action = {"label": "配置下载凭据", "nav": "settings"}
        elif not workspace_ready:
            next_action = {"label": "创建项目", "nav": "workspace"}
        elif not scenes_ready:
            next_action = {"label": "导入影像", "nav": "download"}
        elif not aoi_ready:
            next_action = {"label": "可选绑定 AOI", "nav": "aoi"}
        elif dl_active:
            next_action = {"label": "查看下载", "nav": "download"}
        else:
            next_action = {"label": "生成报告", "nav": "report"}

        sources = [
            {
                "id": "asf",
                "label": "Sentinel-1",
                "credential": creds.get("earthdata"),
                "status": (
                    "configured"
                    if creds.get("earthdata") not in {None, "none", "unavailable"}
                    else "needs_config"
                ),
                "capabilities": ["cart import", "consistency check", "real download"],
            },
            {
                "id": "dem",
                "label": "OpenTopography DEM",
                "credential": creds.get("opentopography"),
                "status": (
                    "configured"
                    if creds.get("opentopography") not in {None, "none", "unavailable"}
                    else "needs_config"
                ),
                "capabilities": ["request plan", "real download", "vertical conversion"],
            },
            {
                "id": "gacos",
                "label": "GACOS",
                "credential": creds.get("gacos"),
                "status": (
                    "configured"
                    if creds.get("gacos") not in {None, "none", "unavailable"}
                    else "needs_config"
                ),
                "capabilities": ["request plan", "email result import"],
            },
            {
                "id": "report",
                "label": "Preparation report",
                "credential": "local",
                "status": "ready" if scenes_ready else "waiting",
                "capabilities": ["html", "markdown", "manifest", "warnings"],
            },
        ]

        return {
            "ok": True,
            "context": ctx,
            "stages": stages,
            "sources": sources,
            "download": dl,
            "next_action": next_action,
            "counts": {
                "projects": len(self._state.workspace.projects) if self._state.workspace else 0,
                "regions": sum(len(p.regions) for p in self._state.workspace.projects)
                if self._state.workspace
                else 0,
                "scenes": scene_count,
            },
            "scene_coverage": {
                "bbox": _dump_optional(_scene_coverage_bbox(region.scenes))
                if region is not None
                else None,
                "count": sum(1 for s in (region.scenes if region is not None else []) if s.footprint_bbox),
            },
            "dem_dataset": self._dem_dataset,
        }

    def get_context(self) -> dict:
        """Return the current workspace/project/region selection for any panel."""
        ws = self._state.workspace
        proj = self._state.current_project()
        region = self._state.current_region()
        ctx: dict = {"ok": True, "workspace": None, "project": None, "region": None}
        if ws is not None:
            ctx["workspace"] = {
                "workspace_id": ws.workspace_id,
                "root": str(ws.workspace_root),
                "name": workspace_display_name(ws),
            }
        if proj is not None:
            ctx["project"] = {
                "project_id": proj.project_id,
                "name": proj.project_name,
                "safe_name": proj.safe_name,
                "root": str(proj.project_root),
            }
        if region is not None:
            has_bbox = region.aoi is not None and region.aoi.bbox is not None
            ctx["region"] = {
                "region_id": region.region_id,
                "name": region.region_name,
                "safe_name": region.region_safe_name,
                "root": str(region.region_root),
                "has_aoi": has_bbox,
                "bbox": _dump(region.aoi.bbox) if has_bbox else None,
                "aoi_geojson": _aoi_geojson(region),
                "scene_footprint_bbox": _dump_optional(_scene_coverage_bbox(region.scenes)),
                "scene_count": len(region.scenes),
            }
        ctx["dem_dataset"] = self._dem_dataset
        return ctx

    def get_tree(self) -> dict:
        """Return the full Workspace > Project > Region tree (survives nav).

        The panels rebuild their view from this on mount, so the hierarchy is
        never lost just because the user navigated away and back.
        """
        ws = self._state.workspace
        if ws is None:
            return {
                "ok": True,
                "workspace": None,
                "projects": [],
                "current_project_id": None,
                "current_region_id": None,
            }
        projects = []
        for project in ws.projects:
            regions = []
            for region in project.regions:
                has_bbox = region.aoi is not None and region.aoi.bbox is not None
                regions.append(
                    {
                        "region_id": region.region_id,
                        "name": region.region_name,
                        "safe_name": region.region_safe_name,
                        "root": str(region.region_root),
                        "has_aoi": has_bbox,
                        "scene_count": len(region.scenes),
                    }
                )
            projects.append(
                {
                    "project_id": project.project_id,
                    "name": project.project_name,
                    "safe_name": project.safe_name,
                    "root": str(project.project_root),
                    "regions": regions,
                }
            )
        return {
            "ok": True,
            "workspace": {
                "workspace_id": ws.workspace_id,
                "root": str(ws.workspace_root),
                "name": workspace_display_name(ws),
            },
            "projects": projects,
            "current_project_id": self._state.current_project_id,
            "current_region_id": self._state.current_region_id,
        }

    # ----------------------------------------------------- native dialogs
    def window_minimize(self) -> dict:
        """Minimize the frameless desktop window."""
        try:
            import webview  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("无可用窗口", "GUI000")
            window.minimize()
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("窗口最小化", exc)
        return {"ok": True}

    def window_toggle_maximize(self, work_area: dict | None = None) -> dict:
        """Toggle maximize/restore for the frameless desktop window."""
        try:
            import webview  # noqa: PLC0415
            from webview.window import FixPoint  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("无可用窗口", "GUI000")
            if self._window_maximized:
                bounds = self._window_restore_bounds
                if bounds is not None:
                    window.move(int(bounds["x"]), int(bounds["y"]))
                    window.resize(int(bounds["width"]), int(bounds["height"]), FixPoint.NORTH | FixPoint.WEST)
                else:
                    window.restore()
                self._window_maximized = False
                self._window_restore_bounds = None
            else:
                self._window_restore_bounds = {
                    "x": int(window.x),
                    "y": int(window.y),
                    "width": int(window.width),
                    "height": int(window.height),
                }
                target_area = self._normalise_window_work_area(work_area) or self._windows_work_area()
                if target_area is None:
                    window.maximize()
                else:
                    left, top, width, height = target_area
                    window.move(left, top)
                    window.resize(width, height, FixPoint.NORTH | FixPoint.WEST)
                self._window_maximized = True
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("窗口最大化", exc)
        return {"ok": True, "maximized": self._window_maximized}

    def window_close(self) -> dict:
        """Close the desktop window."""
        try:
            import webview  # noqa: PLC0415

            self.shutdown()
            window = webview.active_window()
            if window is None:
                return _error_msg("无可用窗口", "GUI000")
            window.destroy()
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("关闭窗口", exc)
        return {"ok": True}

    def shutdown(self) -> dict:
        """Persist state and stop background workers before the desktop exits."""
        if self._shutdown_started:
            return {"ok": True, "already_shutdown": True}
        self._shutdown_started = True
        errors: list[str] = []
        try:
            asf_before = self._asf_download.get_status()
            self._archive_asf_status(asf_before)
            self._asf_download.shutdown()
            self._archive_asf_status(asf_before if asf_before.get("state") == "paused" else self._asf_download.get_status())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ASF 下载收尾失败：{exc}")
        try:
            orbit_before = self._orbit_download.get_status()
            self._archive_orbit_status(orbit_before)
            self._orbit_download.shutdown()
            self._archive_orbit_status(orbit_before if orbit_before.get("state") == "paused" else self._orbit_download.get_status())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"轨道下载收尾失败：{exc}")
        try:
            self._archive_dem_status(self._dem_download.get_status())
            self._dem_download.shutdown()
            self._archive_dem_status(self._dem_download.get_status())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"DEM 下载收尾失败：{exc}")
        try:
            self._save_state()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"状态保存失败：{exc}")
        if errors:
            return {"ok": False, "error": "；".join(errors), "code": "GUI003"}
        return {"ok": True}

    def window_get_size(self) -> dict:
        """Return current native window size for frameless resize handles."""
        try:
            import webview  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("No active window", "GUI000")
            return {
                "ok": True,
                "width": int(window.width),
                "height": int(window.height),
                "x": int(window.x),
                "y": int(window.y),
            }
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("window size", exc)

    def window_resize_from_edge(
        self,
        edge: str,
        start_width: int,
        start_height: int,
        delta_x: int,
        delta_y: int,
    ) -> dict:
        """Resize a frameless window from a transparent edge/corner handle."""
        try:
            import webview  # noqa: PLC0415
            from webview.window import FixPoint  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("No active window", "GUI000")
            edge_key = str(edge or "").lower()
            min_width, min_height = (920, 620)
            try:
                min_width, min_height = window.min_size
            except Exception:  # noqa: BLE001
                pass

            width = int(start_width)
            height = int(start_height)
            if "e" in edge_key:
                width = int(start_width) + int(delta_x)
            if "w" in edge_key:
                width = int(start_width) - int(delta_x)
            if "s" in edge_key:
                height = int(start_height) + int(delta_y)
            if "n" in edge_key:
                height = int(start_height) - int(delta_y)
            width = max(int(min_width), width)
            height = max(int(min_height), height)

            horizontal = FixPoint.WEST if "e" in edge_key else FixPoint.EAST
            vertical = FixPoint.NORTH if "s" in edge_key else FixPoint.SOUTH
            if edge_key in {"e", "w"}:
                vertical = FixPoint.NORTH
            if edge_key in {"n", "s"}:
                horizontal = FixPoint.WEST
            if self._window_maximized:
                window.restore()
                self._window_maximized = False
            window.resize(width, height, vertical | horizontal)
            return {"ok": True, "width": width, "height": height}
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("绐楀彛缂╂斁", exc)

    def pick_open_file(self, title: str = "", filters: list | None = None) -> dict:
        """Open a native file picker; return {ok, path} ('' if cancelled)."""
        try:
            import webview  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("无可用窗口", "GUI000")
            file_types = tuple(filters) if filters else ("All files (*.*)",)
            result = window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("文件选择", exc)
        path = ""
        if result:
            path = str(result[0] if isinstance(result, (list, tuple)) else result)
        return {"ok": True, "path": path}

    def pick_directory(self, title: str = "") -> dict:
        """Open a native folder picker; return {ok, path} ('' if cancelled)."""
        try:
            import webview  # noqa: PLC0415

            window = webview.active_window()
            if window is None:
                return _error_msg("无可用窗口", "GUI000")
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("目录选择", exc)
        path = ""
        if result:
            path = str(result[0] if isinstance(result, (list, tuple)) else result)
        return {"ok": True, "path": path}

    def ensure_directory(self, path: str) -> dict:
        """Create a directory (including parents) for the desktop setup flow."""
        raw = (path or "").strip()
        if not raw:
            return _error_msg("目录路径不能为空", "GUI003")
        target = Path(raw)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _error_msg(f"无法创建目录：{exc}", "GUI003")
        self._act(f"确认项目根目录：{target}", kind="workspace")
        return {"ok": True, "path": str(target)}

    def open_external_url(self, url: str) -> dict:
        """Open an onboarding/register URL in the system browser."""
        target = (url or "").strip()
        if not (target.startswith("https://") or target.startswith("http://")):
            return _error_msg("仅支持打开 http/https 链接", "GUI003")
        try:
            import webbrowser  # noqa: PLC0415

            opened = webbrowser.open(target)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"无法打开浏览器：{exc}", "GUI000")
        return {"ok": bool(opened), "url": target}

    def open_path(self, path: str) -> dict:
        """Open a local file or folder in Windows Explorer."""
        raw = (path or "").strip().strip('"')
        if not raw:
            return _error_msg("路径不能为空", "GUI003")
        target = Path(raw)
        if target.is_file():
            target = target.parent
        elif not target.exists() and target.parent.exists():
            target = target.parent
        if not target.exists():
            return _error_msg(f"路径不存在：{raw}", "GUI003")
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"无法打开目录：{exc}", "GUI000")
        return {"ok": True, "path": str(target)}

    def set_dem_dataset(self, dataset: str) -> dict:
        """Set the DEM dataset for the session (conversion is auto-derived)."""
        name = (dataset or "").strip().upper()
        try:
            from insar_prep.core.enums import DemDataset
            from insar_prep.providers.dem.downloader import opentopo_demtype

            valid = {d.value for d in DemDataset}
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 数据集", exc)
        if name not in valid:
            return _error_msg(f"未知 DEM 数据集：{dataset}", "DEM004")
        if opentopo_demtype(name) is None:
            return _error_msg(
                "USER_LOCAL 是本地 DEM 转换来源，不能通过 OpenTopography 在线下载；"
                "请选择 COP30、COP90、SRTM 或 AW3D30 椭球版，或使用“本地 DEM 转换”。",
                "DEM001",
            )
        self._dem_dataset = name
        self._save_state()
        return {"ok": True, "dataset": name}

    # ------------------------------------------------------ workspace / tree
    def create_workspace(self, root: str, name: str | None = None) -> dict:
        """Create the desktop workspace and ensure its root folder exists."""
        ensured = self.ensure_directory(root)
        if not ensured.get("ok"):
            return ensured
        raw = str(Path(root).expanduser())
        current = self._state.workspace
        if current is not None and str(current.workspace_root) == raw:
            if name and name.strip():
                current.global_settings["display_name"] = name.strip()
            self._save_state()
            return {
                "ok": True,
                "workspace_id": current.workspace_id,
                "root": str(current.workspace_root),
                "projects": [
                    {
                        "project_id": project.project_id,
                        "name": project.project_name,
                        "safe_name": project.safe_name,
                    }
                    for project in current.projects
                ],
            }
        try:
            ws = self._state.create_workspace(root, name)
        except InsarPrepError as exc:
            return _error(exc)
        self._save_state()
        self._act(f"创建工作区：{workspace_display_name(ws)}", kind="workspace")
        return {
            "ok": True,
            "workspace_id": ws.workspace_id,
            "root": str(ws.workspace_root),
            "projects": [],
        }

    def add_project(self, name: str) -> dict:
        """Create a project under the current workspace."""
        try:
            project = self._state.add_project(name)
        except InsarPrepError as exc:
            return _error(exc)
        try:
            project.project_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _error_msg(f"无法创建项目目录：{exc}", "GUI003")
        self._save_state()
        self._act(f"添加项目：{project.project_name}", kind="workspace")
        return {
            "ok": True,
            "project_id": project.project_id,
            "name": project.project_name,
            "safe_name": project.safe_name,
        }

    def select_project(self, project_id: str) -> dict:
        """Make an existing project current (so new regions attach to it)."""
        try:
            project = self._state.select_project(project_id)
        except InsarPrepError as exc:
            return _error(exc)
        self._save_state()
        return {
            "ok": True,
            "project_id": project.project_id,
            "name": project.project_name,
            "safe_name": project.safe_name,
        }

    def add_region(self, name: str) -> dict:
        """Create a region under the current project and make it current."""
        try:
            region = self._state.add_region(name)
        except InsarPrepError as exc:
            return _error(exc)
        try:
            region.region_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _error_msg(f"无法创建研究区目录：{exc}", "GUI003")
        self._save_state()
        self._act(f"添加区域：{region.region_name}", kind="workspace")
        return {
            "ok": True,
            "region_id": region.region_id,
            "name": region.region_name,
            "safe_name": region.region_safe_name,
        }

    def select_region(self, region_id: str) -> dict:
        """Make an existing region current."""
        try:
            region = self._state.select_region(region_id)
        except InsarPrepError as exc:
            return _error(exc)
        self._save_state()
        return {
            "ok": True,
            "region_id": region.region_id,
            "name": region.region_name,
            "safe_name": region.region_safe_name,
        }

    # --------------------------------------------------------------- 1. AOI
    def set_region_aoi_bbox(self, west: float, east: float, south: float, north: float) -> dict:
        """Bind a manual bbox (W/E/S/N) as the current region's processing AOI."""
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox
        except Exception as exc:  # noqa: BLE001 - optional geo deps
            return _missing_dep("AOI 处理", exc)
        try:
            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError etc.
            return _error_msg(_format_validation(exc), "AOI001")
        try:
            self._ensure_current_region()
            region = self._state.set_current_region_aoi(aoi)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GUI003")
        self._save_state()
        self._act(
            f"绑定 AOI（{region.region_name}）W{west} E{east} S{south} N{north}",
            kind="aoi",
        )
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def set_region_aoi_file(self, path: str) -> dict:
        """Bind an AOI loaded from a vector file (shp/kml/kmz/geojson/json)."""
        try:
            from insar_prep.processing.aoi_vector import load_aoi_from_file
        except Exception as exc:  # noqa: BLE001 - optional geo deps
            return _missing_dep("矢量文件导入", exc)
        try:
            aoi = load_aoi_from_file(path)
            self._ensure_current_region()
            region = self._state.set_current_region_aoi(aoi)
            preview_geojson = _geojson_from_aoi_file(path)
            feature_count = _geojson_feature_count_from_file(path)
            if preview_geojson is not None:
                saved_geojson = _write_region_aoi_geojson(region, preview_geojson)
                region.aoi.geometry_path = saved_geojson or Path(path)
            else:
                region.aoi.geometry_path = Path(path)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001 - file/parse errors
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        self._act(f"从文件导入 AOI：{Path(path).name} → {region.region_name}", kind="aoi")
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(preview_geojson) if preview_geojson is not None else None,
            "aoi_feature_count": feature_count,
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def preview_aoi_file(self, path: str) -> dict:
        """Return selectable features from a local AOI vector file."""
        try:
            features = _read_aoi_vector_features(path)
        except InsarPrepError as exc:
            return _error(exc)
        except FileNotFoundError as exc:
            return _error_msg(_friendly_aoi_error(exc, path), "AOI001")
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, path), "AOI001")
        return self._aoi_preview_response(path, features)

    def preview_aoi_file_content(self, file_name: str, text: str) -> dict:
        """Return selectable features from dragged KML/GeoJSON text content."""
        try:
            features = _read_aoi_vector_features_from_text(file_name, text)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        return self._aoi_preview_response(file_name, features, source_kind="content", include_geojson=True)

    def preview_aoi_file_bytes(self, file_name: str, base64_data: str) -> dict:
        """Return selectable features from dragged binary AOI content."""
        try:
            raw = base64.b64decode(str(base64_data or ""), validate=True)
            features = _read_aoi_vector_features_from_bytes(file_name, raw)
        except (binascii.Error, ValueError) as exc:
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        return self._aoi_preview_response(file_name, features, source_kind="content", include_geojson=True)

    def set_region_aoi_geojson_features(
        self,
        geojson: dict,
        feature_ids: list[Any] | None = None,
        name_field: str = "",
        download_mode: str = "merge",
    ) -> dict:
        """Bind selected features from dragged GeoJSON/KML content."""
        try:
            selected_geojson = _selected_geojson_from_feature_collection(
                geojson,
                feature_ids=feature_ids,
                name_field=name_field,
                download_mode=download_mode,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, "拖入边界"), "AOI001")
        return self.set_region_aoi_geojson(selected_geojson)

    @staticmethod
    def _aoi_preview_response(
        path: str,
        features: list[dict[str, Any]],
        *,
        source_kind: str = "path",
        include_geojson: bool = False,
    ) -> dict:
        fields = _aoi_feature_fields(features)
        display_field = _suggest_aoi_name_field(fields)
        response = {
            "ok": True,
            "path": str(path),
            "file_name": Path(path).name,
            "source_kind": source_kind,
            "total_features": len(features),
            "fields": fields,
            "display_field": display_field,
            "features": [
                _aoi_feature_preview_row(index, feature, display_field)
                for index, feature in enumerate(features)
            ],
        }
        if include_geojson:
            response["geojson"] = _feature_collection_from_aoi_features(features, str(path))
        return response

    def set_region_aoi_file_features(
        self,
        path: str,
        feature_ids: list[Any] | None = None,
        name_field: str = "",
        download_mode: str = "merge",
    ) -> dict:
        """Bind selected features from a local AOI vector file as the current AOI."""
        try:
            from shapely.geometry import shape
            from shapely.ops import unary_union

            from insar_prep.core.enums import AoiSource
            from insar_prep.processing.aoi_import import (
                _coerce_to_areal_geometry,
                geometry_to_processing_aoi,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("多要素 AOI 导入", exc)
        try:
            features = _read_aoi_vector_features(path)
            selected_indices = _normalise_feature_indices(feature_ids, len(features))
            if not selected_indices:
                return _error_msg("请至少选择一个边界要素。", "AOI001")
            selected = [features[index] for index in selected_indices]
            geometries = [
                _coerce_to_areal_geometry(shape(feature["geometry"]))
                for feature in selected
                if isinstance(feature.get("geometry"), dict)
            ]
            if not geometries:
                return _error_msg("选中的要素没有可用面边界。", "AOI001")
            merged_geometry = _coerce_to_areal_geometry(unary_union(geometries))
            aoi = geometry_to_processing_aoi(merged_geometry, source=AoiSource.VECTOR_FILE)
            self._ensure_current_region()
            region = self._state.set_current_region_aoi(aoi)
            field = str(name_field or "").strip()
            selected_geojson = {
                "type": "FeatureCollection",
                "properties": {
                    "source_file": str(path),
                    "feature_count": len(selected),
                    "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
                    "name_field": field,
                },
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            **dict(feature.get("properties") or {}),
                            "_insar_feature_index": selected_indices[i],
                            "_insar_feature_name": _aoi_feature_name(feature, field),
                        },
                        "geometry": feature["geometry"],
                    }
                    for i, feature in enumerate(selected)
                ],
            }
            saved_geojson = _write_region_aoi_geojson(region, selected_geojson)
            if saved_geojson is not None:
                region.aoi.geometry_path = saved_geojson
            else:
                region.aoi.geometry_path = Path(path)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        mode_label = "拆分下载" if str(download_mode).strip() == "split" else "合并下载"
        self._act(
            f"导入边界要素 {len(selected)} / {len(features)} 个并绑定 AOI：{Path(path).name}（{mode_label}）",
            kind="aoi",
        )
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(selected_geojson),
            "aoi_feature_count": len(selected),
            "aoi_total_feature_count": len(features),
            "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def set_region_aoi_geojson(self, geojson: dict) -> dict:
        """Bind an AOI from an in-memory GeoJSON Feature / Geometry (map drawing)."""
        try:
            from insar_prep.core.enums import AoiSource
            from insar_prep.processing.aoi_import import (
                _geometry_from_geojson,
                geometry_to_processing_aoi,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("GeoJSON AOI", exc)
        if not isinstance(geojson, dict):
            return _error_msg("GeoJSON 必须是对象", "AOI001")
        try:
            geometry = _geometry_from_geojson(geojson)
            aoi = geometry_to_processing_aoi(geometry, source=AoiSource.MANUAL_BBOX)
            self._ensure_current_region()
            region = self._state.set_current_region_aoi(aoi)
            saved_geojson = _write_region_aoi_geojson(region, geojson)
            if saved_geojson is not None:
                region.aoi.geometry_path = saved_geojson
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        self._act(f"地图绘制 AOI 已绑定：{region.region_name}", kind="aoi")
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(geojson),
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def search_admin_boundaries(
        self,
        query: str = "",
        province: str = "",
        city: str = "",
        district: str = "",
        limit: int = 8,
    ) -> dict:
        """Search administrative/place boundaries.

        Prefer Tianditu administrative divisions when a desktop Tianditu token is
        configured, then fall back to OpenStreetMap/Nominatim for quick previews.
        Users can still upload authoritative local shp/kml/geojson boundaries via
        :meth:`set_region_aoi_file`.
        """
        terms = [
            str(district or "").strip(),
            str(city or "").strip(),
            str(province or "").strip(),
            str(query or "").strip(),
        ]
        if _is_national_admin_request(
            province=str(province or ""),
            city=str(city or ""),
            district=str(district or ""),
            query=str(query or ""),
        ):
            self._act("行政边界搜索：全国（内置范围）", kind="aoi")
            return {
                "ok": True,
                "query": "全国",
                "provider": "builtin",
                "results": [_builtin_china_boundary()],
                "warning": "全国范围使用内置省级边界合成预览；正式项目建议上传权威国界面文件。",
            }
        terms = [term for term in terms if term and term not in {"全部", "不限"}]
        search_text = " ".join(dict.fromkeys(terms)).strip()
        if not search_text:
            return _error_msg("请输入地名，或选择省/市/区后再加载行政边界", "AOI001")

        source_warnings: list[str] = []
        local_results, local_error = _search_local_admin_boundaries(
            province=str(province or ""),
            city=str(city or ""),
            district=str(district or ""),
            query=str(query or ""),
            limit=limit,
        )
        if local_results:
            self._act(f"本地行政边界搜索：{search_text}（{len(local_results)} 条）", kind="aoi")
            return {
                "ok": True,
                "query": search_text,
                "provider": "local",
                "results": local_results,
                "warning": None,
            }
        if local_error:
            source_warnings.append(local_error)

        token = str(self._network_settings.get("tianditu_token") or "").strip()
        if token:
            tianditu_results, tianditu_error = _search_tianditu_admin_boundaries(
                token=token,
                candidates=[*terms, search_text],
                limit=limit,
            )
            if tianditu_results:
                self._act(f"天地图行政边界搜索：{search_text}（{len(tianditu_results)} 条）", kind="aoi")
                return {
                    "ok": True,
                    "query": search_text,
                    "provider": "tianditu",
                    "results": tianditu_results,
                    "warning": None,
                }
            if tianditu_error:
                source_warnings.append(f"天地图未返回可用边界：{tianditu_error}")
        else:
            source_warnings.append("未配置天地图 Token，已尝试使用备用开放地名源。")

        if "中国" not in search_text and "China" not in search_text:
            search_text = f"{search_text} 中国"
        try:
            import requests  # noqa: PLC0415 - optional download extra
        except ImportError as exc:
            return _missing_dep("行政边界搜索", exc)
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": search_text,
                    "format": "geojson",
                    "polygon_geojson": "1",
                    "addressdetails": "1",
                    "limit": str(max(1, min(int(limit or 8), 20))),
                    "accept-language": "zh-CN,zh,en",
                },
                headers={"User-Agent": "InSAR-Assistant/0.1 local desktop AOI search"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            if source_warnings:
                return _error_msg(
                    f"{'；'.join(source_warnings)} 备用源也检索失败：{exc}。"
                    "请在设置填写天地图 Token，或直接上传 shp/kml/kmz/geojson 边界作为 AOI。",
                    "AOI001",
                )
            return _error_msg(f"行政边界搜索失败：{exc}", "AOI001")

        features = data.get("features", []) if isinstance(data, dict) else []
        results: list[dict] = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            bbox = _boundary_bbox(feature)
            if bbox is None:
                continue
            props = feature.get("properties") or {}
            if not isinstance(props, dict):
                props = {}
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
            results.append(
                {
                    "label": str(
                        props.get("display_name")
                        or props.get("name")
                        or props.get("name:zh")
                        or search_text
                    ),
                    "bbox": bbox,
                    "geojson": geometry,
                    "source": "Nominatim / OpenStreetMap",
                    "class": props.get("class"),
                    "type": props.get("type"),
                    "osm_type": props.get("osm_type"),
                    "osm_id": props.get("osm_id"),
                }
            )
        self._act(f"行政边界搜索：{search_text}（{len(results)} 条）", kind="aoi")
        return {
            "ok": True,
            "query": search_text,
            "provider": "nominatim",
            "results": results,
            "warning": "；".join(source_warnings) if source_warnings else None,
        }

    def get_admin_options(self, province: str = "", city: str = "") -> dict:
        """Return province/city/county option lists from the bundled local boundaries."""
        try:
            options = _local_admin_options(province=province, city=city)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"本地行政区划选项读取失败：{exc}", "AOI001")
        return {"ok": True, **options}

    # ------------------------------------------------------------ 2. SCENES
    def import_scenes_text(self, text: str) -> dict:
        """Parse pasted granule names / URLs (one per line) into the region."""
        try:
            from insar_prep.providers.asf.scene_parser import (
                deduplicate_scenes,
                parse_scene_name,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("场景解析", exc)
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines:
            return _error_msg("请粘贴至少一个 Sentinel-1 颗粒名或下载链接", "ASF001")
        scenes = []
        errors: list[dict] = []
        for line in lines:
            try:
                scenes.append(parse_scene_name(line))
            except InsarPrepError as exc:
                errors.append({"line": line, "error": str(exc)})
        if not scenes:
            return {
                "ok": False,
                "error": "未能解析出任何有效的 Sentinel-1 场景",
                "code": "ASF001",
                "errors": errors,
            }
        unique, dups = deduplicate_scenes(scenes)
        self._set_metadata_status("running", 0, max(1, len(unique)), "正在补全 ASF 元数据")
        unique = _enrich_scenes_best_effort(
            unique,
            activity=self._activity,
            progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
        )
        self._set_metadata_status("finished", 1, 1, "ASF 元数据补全完成")
        try:
            stored, label = self._store_imported_scenes(unique)
        except InsarPrepError as exc:
            return _error(exc)
        self._act(
            f"导入 {len(stored)} 景场景 → {label}",
            kind="scenes",
        )
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in stored],
            "duplicates": dups,
            "errors": errors,
        }

    def import_scenes_file(self, path: str) -> dict:
        """Parse an ASF cart file (.py/.metalink/.txt/.csv/.geojson/.json) into the region."""
        try:
            from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("购物车解析", exc)
        try:
            scenes = parse_asf_cart_file(path)
            unique, dups = deduplicate_scenes(scenes)
            self._set_metadata_status("running", 0, max(1, len(unique)), "正在补全 ASF 元数据")
            unique = _enrich_scenes_best_effort(
                unique,
                activity=self._activity,
                progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
            )
            self._set_metadata_status("finished", 1, 1, "ASF 元数据补全完成")
            stored, label = self._store_imported_scenes(unique)
        except InsarPrepError as exc:
            return _error(exc)
        self._act(
            f"从购物车导入 {len(stored)} 景：{Path(path).name} → {label}",
            kind="scenes",
        )
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in stored],
            "duplicates": dups,
            "errors": [],
        }

    def import_scenes_directory(self, path: str) -> dict:
        """Scan a local Sentinel-1 directory for .zip / .SAFE scene names."""
        root = Path((path or "").strip())
        if not root:
            return _error_msg("请提供 Sentinel-1 数据目录", "ASF001")
        if not root.exists() or not root.is_dir():
            return _error_msg(f"Sentinel-1 数据目录不存在：{root}", "ASF001")
        try:
            from insar_prep.providers.asf.scene_parser import (
                deduplicate_scenes,
                parse_scene_name,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("本地 Sentinel-1 目录识别", exc)
        scenes = []
        errors: list[dict] = []
        for entry in sorted(root.rglob("*")):
            suffix = entry.suffix.lower()
            if not (
                (entry.is_file() and suffix == ".zip")
                or (entry.is_dir() and suffix == ".safe")
            ):
                continue
            try:
                scene = parse_scene_name(str(entry))
                scenes.append(scene.model_copy(update={"local_path": entry}))
            except InsarPrepError as exc:
                errors.append({"line": str(entry), "error": str(exc)})
        if not scenes:
            return _error_msg("目录内没有识别到 Sentinel-1 .zip 或 .SAFE", "ASF001")
        unique, dups = deduplicate_scenes(scenes)
        self._set_metadata_status("running", 0, max(1, len(unique)), "正在补全 ASF 元数据")
        unique = _enrich_scenes_best_effort(
            unique,
            activity=self._activity,
            progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
        )
        self._set_metadata_status("finished", 1, 1, "ASF 元数据补全完成")
        try:
            stored, label = self._store_imported_scenes(unique)
        except InsarPrepError as exc:
            return _error(exc)
        self._act(f"从 Sentinel-1 目录识别 {len(stored)} 景 → {label}", kind="scenes")
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in stored],
            "duplicates": dups,
            "errors": errors,
        }

    def preview_scenes_file(self, path: str) -> dict:
        """Parse an ASF cart file without replacing the current Sentinel-1 list."""
        try:
            from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("购物车解析", exc)
        try:
            scenes = parse_asf_cart_file(path)
            unique, dups = deduplicate_scenes(scenes)
            self._set_metadata_status("running", 0, max(1, len(unique)), "正在解析轨道匹配候选")
            unique = _enrich_scenes_best_effort(
                unique,
                activity=self._activity,
                progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
            )
            self._set_metadata_status("finished", 1, 1, "轨道匹配候选解析完成")
        except InsarPrepError as exc:
            return _error(exc)
        self._act(f"预览轨道匹配候选 {len(unique)} 景：{Path(path).name}", kind="orbit")
        self._orbit_candidate_scenes = unique
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in _sort_scenes_by_acquisition_date(unique)],
            "duplicates": dups,
            "errors": [],
        }

    def preview_scenes_directory(self, path: str) -> dict:
        """Scan a local SAR directory without replacing the current Sentinel-1 list."""
        root = Path((path or "").strip())
        if not root:
            return _error_msg("请提供 Sentinel-1 数据目录", "ASF001")
        if not root.exists() or not root.is_dir():
            return _error_msg(f"Sentinel-1 数据目录不存在：{root}", "ASF001")
        try:
            from insar_prep.providers.asf.scene_parser import (
                deduplicate_scenes,
                parse_scene_name,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("本地 Sentinel-1 目录识别", exc)
        scenes = []
        errors: list[dict] = []
        for entry in sorted(root.rglob("*")):
            suffix = entry.suffix.lower()
            if not (
                (entry.is_file() and suffix == ".zip")
                or (entry.is_dir() and suffix == ".safe")
            ):
                continue
            try:
                scene = parse_scene_name(str(entry))
                scenes.append(scene.model_copy(update={"local_path": entry}))
            except InsarPrepError as exc:
                errors.append({"line": str(entry), "error": str(exc)})
        if not scenes:
            return _error_msg("目录内没有识别到 Sentinel-1 .zip 或 .SAFE", "ASF001")
        unique, dups = deduplicate_scenes(scenes)
        self._set_metadata_status("running", 0, max(1, len(unique)), "正在解析轨道匹配候选")
        unique = _enrich_scenes_best_effort(
            unique,
            activity=self._activity,
            progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
        )
        self._set_metadata_status("finished", 1, 1, "轨道匹配候选解析完成")
        self._act(f"预览轨道匹配候选 {len(unique)} 景：{root.name}", kind="orbit")
        self._orbit_candidate_scenes = unique
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in _sort_scenes_by_acquisition_date(unique)],
            "duplicates": dups,
            "errors": errors,
        }

    def clear_orbit_candidate_scenes(self) -> dict:
        """Clear preview-only orbit candidates so orbit tools fall back to active scenes."""
        cleared = len(self._orbit_candidate_scenes)
        self._orbit_candidate_scenes = []
        self._act(f"已清除 {cleared} 景精密轨道预览候选，恢复沿用 Sentinel-1 检索结果", kind="orbit")
        return {"ok": True, "cleared": cleared}

    def list_scenes(self) -> dict:
        """Return imported scenes for the current region or standalone task."""
        scenes, _, _ = self._active_scene_context()
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in _sort_scenes_by_acquisition_date(scenes)],
            "duplicates": [],
            "errors": [],
        }

    def get_metadata_status(self) -> dict:
        """Return current ASF metadata/search progress."""
        return {"ok": True, **self._metadata_status}

    def cancel_asf_search(self) -> dict:
        """Request cancellation for the active ASF metadata search."""
        self._asf_search_cancel.set()
        self._set_metadata_status("cancelled", 0, 1, "ASF 检索已请求停止")
        return {"ok": True, "cancelled": True}

    def clear_scenes(self) -> dict:
        """Clear imported/searched Sentinel-1 scenes from the active context."""
        region = self._state.current_region()
        if region is None:
            cleared = len(self._standalone_scenes)
            self._standalone_scenes = []
            label = "独立下载任务"
        else:
            cleared = len(region.scenes)
            region = self._state.set_current_region_scenes([])
            self._save_state()
            label = region.region_name
        self._last_orbit_report = None
        self._act(f"已清除 {label} 的 {cleared} 景影像结果", kind="scenes")
        return {"ok": True, "cleared": cleared}

    def clear_map_layers(self) -> dict:
        """Clear visible map overlays: AOI, scene footprints and transient reports."""
        region = self._state.current_region()
        if region is None:
            cleared_scenes = len(self._standalone_scenes)
            self._standalone_scenes = []
            label = "独立下载任务"
            cleared_aoi = False
        else:
            from insar_prep.core.enums import AoiRole, AoiSource
            from insar_prep.core.models import Aoi

            cleared_scenes = len(region.scenes)
            cleared_aoi = bool(region.aoi is not None and region.aoi.bbox is not None)
            region.scenes = []
            region.aoi = Aoi(
                source=AoiSource.MANUAL_BBOX,
                role=AoiRole.PROCESSING_AOI,
                bbox=None,
            )
            label = region.region_name
            self._save_state()
        self._last_orbit_report = None
        self._orbit_candidate_scenes = []
        self._metadata_status = self._idle_metadata_status()
        self._act(
            f"已清空 {label} 的地图图层：AOI {1 if cleared_aoi else 0} 个，影像 {cleared_scenes} 景",
            kind="aoi",
        )
        return {"ok": True, "cleared_scenes": cleared_scenes, "cleared_aoi": cleared_aoi}

    def search_asf_scenes(self, params: dict | None = None) -> dict:
        """Search ASF metadata by AOI/date/product and import the results."""
        payload = params or {}
        try:
            from insar_prep.core.models import BBox
            from insar_prep.providers.asf.metadata import search_scenes_from_asf
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("ASF 检索", exc)

        bbox = None
        aoi_geojson = payload.get("aoi_geojson") if isinstance(payload.get("aoi_geojson"), dict) else None
        raw_bbox = payload.get("bbox")
        if isinstance(raw_bbox, dict):
            try:
                bbox = BBox(
                    west=float(raw_bbox.get("west")),
                    east=float(raw_bbox.get("east")),
                    south=float(raw_bbox.get("south")),
                    north=float(raw_bbox.get("north")),
                    crs=str(raw_bbox.get("crs") or "EPSG:4326"),
                )
            except Exception as exc:  # noqa: BLE001
                return _error_msg(_format_validation(exc), "AOI001")
        elif bool(payload.get("use_current_aoi", True)):
            region = self._state.current_region()
            if region is not None and region.aoi is not None and region.aoi.bbox is not None:
                bbox = region.aoi.bbox
            if aoi_geojson is None and region is not None:
                aoi_geojson = _aoi_geojson(region)
        if aoi_geojson is None and bool(payload.get("use_current_aoi", True)):
            region = self._state.current_region()
            if region is not None:
                aoi_geojson = _aoi_geojson(region)

        def _optional_int(name: str) -> int | None:
            value = payload.get(name)
            if value in (None, ""):
                return None
            return int(float(str(value).strip()))

        def _optional_asf_int_filter(
            name: str,
            *,
            start_name: str = "",
            end_name: str = "",
        ) -> str | None:
            value = str(payload.get(name) or "").strip()
            if not value and start_name:
                start_value = str(payload.get(start_name) or "").strip()
                end_value = str(payload.get(end_name) or "").strip() if end_name else ""
                if start_value and end_value:
                    value = f"{start_value}-{end_value}"
                else:
                    value = start_value or end_value
            return value or None

        try:
            self._asf_search_cancel.clear()
            self._set_metadata_status("running", 0, 1, "正在准备 ASF 检索")
            search_stats: dict[str, Any] = {}
            explicit_limit = _optional_int("max_results")
            relative_orbit = _optional_asf_int_filter(
                "relative_orbit",
                start_name="relative_orbit_start",
                end_name="relative_orbit_end",
            )
            frame = _optional_asf_int_filter("frame", start_name="frame_start", end_name="frame_end")
            cache_key, cache_path, cache_query = self._asf_search_cache_target(
                bbox=bbox,
                aoi_geojson=aoi_geojson,
                payload=payload,
                relative_orbit=relative_orbit,
                frame=frame,
            )
            cache_entry = self._load_asf_search_cache(cache_key, cache_path)
            cached_scenes = self._cached_asf_scenes_for_limit(cache_entry, explicit_limit, cache_query)
            if cached_scenes is None:
                covering_entry = self._find_covering_asf_search_cache(cache_query, explicit_limit, cache_path)
                if covering_entry is not None:
                    cache_entry = covering_entry
                    cached_scenes = list(covering_entry.get("scenes") or [])
            if cached_scenes is not None:
                scenes = cached_scenes
                stored, label = self._store_imported_scenes(scenes)
                cached_total = cache_entry.get("total_count") if cache_entry else None
                self._set_metadata_status("finished", 1, 1, f"已从本地缓存读取 ASF 检索结果：{len(stored)} 景")
                self._act(f"ASF 检索缓存导入 {len(stored)} 景 → {label}", kind="scenes")
                return {
                    "ok": True,
                    "scenes": [_scene_row(s) for s in stored],
                    "duplicates": [],
                    "errors": [],
                    "queried": len(scenes),
                    "search": {
                        "requested_limit": explicit_limit,
                        "query_limit": len(cache_entry.get("scenes") or []) if cache_entry else len(scenes),
                        "total_count": cached_total,
                        "returned_count": len(stored),
                        "source": "ASF_CACHE",
                    },
                    "cache": {
                        "hit": True,
                        "key": cache_entry.get("cache_key") if cache_entry else cache_key,
                        "count": len(cache_entry.get("scenes") or []) if cache_entry else len(scenes),
                        "path": cache_entry.get("path") if cache_entry else "",
                    },
                }
            scenes = search_scenes_from_asf(
                bbox=bbox,
                aoi_geojson=aoi_geojson,
                start=str(payload.get("start") or "").strip() or None,
                end=str(payload.get("end") or "").strip() or None,
                product_type=str(payload.get("product_type") or "SLC"),
                beam_mode=str(payload.get("beam_mode") or "IW"),
                polarization=str(payload.get("polarization") or ""),
                orbit_direction=str(payload.get("orbit_direction") or ""),
                relative_orbit=relative_orbit,
                frame=frame,
                max_results=explicit_limit,
                progress=lambda done, total, msg: self._set_metadata_status("running", done, total, msg),
                stats=search_stats,
                cancelled=lambda: self._asf_search_cancel.is_set(),
                allow_cmr_fallback=True,
            )
            if self._asf_search_cancel.is_set():
                self._set_metadata_status("cancelled", 0, 1, "ASF 检索已停止")
                return {"ok": False, "cancelled": True, "error": "ASF 检索已停止", "code": "DL001"}
            self._write_asf_search_cache(
                cache_key=cache_key,
                cache_path=cache_path,
                key_payload=cache_query,
                scenes=scenes,
                stats=search_stats,
                existing=cache_entry,
            )
            stored, label = self._store_imported_scenes(scenes)
            self._set_metadata_status("finished", 1, 1, "ASF 检索与元数据解析完成")
        except InsarPrepError as exc:
            if getattr(exc, "code", None) and str(getattr(exc, "code")) == "DL001":
                self._set_metadata_status("cancelled", 0, 1, "ASF 检索已停止")
                return {"ok": False, "cancelled": True, "error": "ASF 检索已停止", "code": "DL001"}
            self._set_metadata_status("failed", 0, 1, str(exc))
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            self._set_metadata_status("failed", 0, 1, str(exc))
            return _error_msg(str(exc), "ASF002")

        self._act(f"ASF 检索导入 {len(stored)} 景 → {label}", kind="scenes")
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in stored],
            "duplicates": [],
            "errors": [],
            "queried": len(scenes),
            "search": {
                "requested_limit": search_stats.get("requested_limit"),
                "query_limit": search_stats.get("query_limit"),
                "total_count": search_stats.get("total_count"),
                "returned_count": len(stored),
                "source": search_stats.get("source") or "ASF",
            },
            "cache": {
                "hit": False,
                "key": cache_key,
                "count": len(scenes),
                "path": str(cache_path) if cache_path is not None else "",
            },
        }

    def check_scenes(self) -> dict:
        """Run the consistency check on region or standalone scenes."""
        scenes, _, label = self._active_scene_context()
        if not scenes:
            return _error_msg("请先导入场景", "ASF001")
        try:
            from insar_prep.quality.scene_checks import check_scene_collection
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("一致性核查", exc)
        try:
            report = check_scene_collection(
                scenes,
                expected_product_type=None,
                expected_beam_mode=None,
            )
        except InsarPrepError as exc:
            return _error(exc)
        has_err = bool(getattr(report, "has_errors", False))
        self._act(
            f"场景核查：{label} {report.total_scenes} 景"
            + ("（有阻断项）" if has_err else "（通过）"),
            kind="scenes",
        )
        return {"ok": True, "report": _dump(report)}

    def match_orbits_directory(self, orbit_dir: str) -> dict:
        """Scan a local EOF directory and match POEORB/RESORB/MOEORB to scenes."""
        scenes, label = self._orbit_scene_context()
        if not scenes:
            return _error_msg("请先导入 ASF 场景或本地 SLC 目录", "ASF001")
        raw = (orbit_dir or "").strip()
        if not raw:
            return _error_msg("请提供精密轨道目录", "ORB001")
        try:
            from insar_prep.providers.orbit import (
                match_orbits_for_scenes,
                scan_orbit_directory,
            )

            orbit_files = scan_orbit_directory(raw, recursive=True)
            report = match_orbits_for_scenes(scenes, orbit_files)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "ORB001")
        self._last_orbit_report = report
        self._act(
            f"轨道匹配：{label} {report.matched_scenes}/{report.total_scenes} 景",
            kind="download",
        )
        return {
            "ok": True,
            "orbit_dir": str(Path(raw)),
            "orbit_files": len(orbit_files),
            "report": _dump(report),
        }

    def download_orbits(
        self,
        output_dir: str = "",
        scene_ids: list[str] | None = None,
        use_orbit_subdir: bool = False,
    ) -> dict:
        """Download POEORB companion files from ASF, then match them to scenes."""
        scenes, label = self._orbit_scene_context(scene_ids)
        if not scenes:
            return _error_msg("请先导入 ASF 场景或本地 SLC 目录", "ASF001")
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定输出目录；未勾选子目录时轨道将直接保存到所选目录", "GUI003")
        try:
            from insar_prep.providers.orbit import (
                download_orbits_for_scenes,
                match_orbits_for_scenes,
                scan_orbit_directory,
            )

            summary = download_orbits_for_scenes(
                scenes,
                out,
                use_orbit_subdir=_coerce_bool(use_orbit_subdir, False),
            )
            orbit_files = scan_orbit_directory(summary.orbit_dir, recursive=True)
            report = match_orbits_for_scenes(scenes, orbit_files)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "ORB001")
        self._last_orbit_report = report
        self._act(
            f"精密轨道下载：{label}，{summary.summary_line()}，匹配 {report.matched_scenes}/{report.total_scenes} 景",
            kind="download",
        )
        return {
            "ok": True,
            "orbit_dir": str(summary.orbit_dir),
            "summary_line": summary.summary_line(),
            "total": summary.total,
            "succeeded": summary.succeeded,
            "skipped": summary.skipped,
            "unavailable": summary.unavailable,
            "failed": summary.failed,
            "has_failures": summary.has_failures,
            "results": [result.to_dict() for result in summary.results],
            "report": _dump(report),
        }

    def start_orbit_download(
        self,
        output_dir: str = "",
        scene_ids: list[str] | None = None,
        max_concurrent: int = 10,
        use_orbit_subdir: bool = False,
    ) -> dict:
        """Start POEORB companion downloads in the background."""
        scenes, label = self._orbit_scene_context(scene_ids)
        return self._start_orbit_download_for_scenes(
            scenes,
            label=label,
            output_dir=output_dir,
            max_concurrent=max_concurrent,
            use_orbit_subdir=use_orbit_subdir,
        )

    def start_orbit_download_snapshot(
        self,
        output_dir: str = "",
        scenes_snapshot: list[dict[str, Any]] | None = None,
        scene_ids: list[str] | None = None,
        max_concurrent: int = 10,
        use_orbit_subdir: bool = False,
    ) -> dict:
        """Start POEORB downloads from a frozen Orbit task snapshot."""
        try:
            scenes = [_scene_from_row(row) for row in (scenes_snapshot or []) if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"任务快照解析失败：{exc}", "ASF001")
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
        return self._start_orbit_download_for_scenes(
            scenes,
            label=f"轨道任务快照（选中 {len(scenes)} 景）",
            output_dir=output_dir,
            max_concurrent=max_concurrent,
            use_orbit_subdir=use_orbit_subdir,
        )

    def _start_orbit_download_for_scenes(
        self,
        scenes: list[Any],
        *,
        label: str,
        output_dir: str = "",
        max_concurrent: int = 10,
        use_orbit_subdir: bool = False,
    ) -> dict:
        if not scenes:
            return _error_msg("请先导入 ASF 场景或本地 SLC 目录", "ASF001")
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定输出目录；未勾选子目录时轨道将直接保存到所选目录", "GUI003")
        self._act(f"开始精密轨道下载：{label}（{len(scenes)} 景）", kind="download")
        use_subdir = _coerce_bool(use_orbit_subdir, False)
        orbit_dir = Path(out) / "Sentinel_Orbit" if use_subdir else Path(out)
        self._forget_deleted_archive_key("orbit", str(orbit_dir), use_orbit_subdir=use_subdir)
        result = self._orbit_download.start(
            scenes,
            out,
            max_concurrent=max_concurrent,
            use_orbit_subdir=use_subdir,
            activity=self._activity,
        )
        self._archive_orbit_status(self._orbit_download.get_status())
        return result

    def pause_orbit_download(self) -> dict:
        """Pause orbit downloads between scenes."""
        result = self._orbit_download.pause()
        self._archive_orbit_status(self._orbit_download.get_status())
        return result

    def resume_orbit_download(self) -> dict:
        """Resume a paused orbit download."""
        result = self._orbit_download.resume()
        self._archive_orbit_status(self._orbit_download.get_status())
        return result

    def stop_orbit_download(self) -> dict:
        """Cancel the in-progress orbit download."""
        result = self._orbit_download.stop()
        self._archive_orbit_status(self._orbit_download.get_status())
        return result

    def get_orbit_download_status(self) -> dict:
        """Poll orbit download progress."""
        status = self._orbit_download.get_status()
        self._archive_orbit_status(status)
        return status

    # ----------------------------------------------------------- 3. DOWNLOAD
    def plan_asf_download(
        self,
        output_dir: str = "",
        scene_ids: list[str] | None = None,
        use_product_subdirs: bool = False,
    ) -> dict:
        """Build (dry-run) an ASF Sentinel-1 download plan."""
        scenes, region_safe_name, _ = self._active_scene_context()
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
        if not scenes:
            return _error_msg("请先在『影像核查』导入场景", "ASF001")
        try:
            from insar_prep.providers.asf.download_plan import build_asf_download_plan
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("ASF 下载规划", exc)
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("独立下载任务需要先指定输出根目录", "GUI003")
        try:
            unique, _ = deduplicate_scenes(scenes)
            plan = build_asf_download_plan(
                scenes=unique,
                output_dir=out,
                region_safe_name=region_safe_name,
                use_product_subdirs=_coerce_bool(use_product_subdirs, False),
                product_subdir_root="",
            )
        except InsarPrepError as exc:
            return _error(exc)
        self._act(
            f"ASF 下载规划：{plan.planned_count} 景可下载 / {plan.scene_count} 景",
            kind="download",
        )
        return {"ok": True, "plan": _dump(plan)}

    def start_asf_download(
        self,
        output_dir: str = "",
        credential_source: str = "auto",
        max_concurrent: int = 1,
        scene_ids: list[str] | None = None,
        use_product_subdirs: bool = False,
    ) -> dict:
        """Start a real ASF Sentinel-1 download on a background thread."""
        scenes, _, label = self._active_scene_context()
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
            label = f"{label}（选中 {len(scenes)} 景）"
        return self._start_asf_download_for_scenes(
            scenes,
            label=label,
            output_dir=output_dir,
            credential_source=credential_source,
            max_concurrent=max_concurrent,
            use_product_subdirs=use_product_subdirs,
        )

    def start_asf_download_snapshot(
        self,
        output_dir: str = "",
        scenes_snapshot: list[dict[str, Any]] | None = None,
        scene_ids: list[str] | None = None,
        credential_source: str = "auto",
        max_concurrent: int = 1,
        use_product_subdirs: bool = False,
    ) -> dict:
        """Start ASF downloading from a frozen UI task snapshot.

        This keeps queued download tasks independent from later ASF searches that
        replace the current workbench results.
        """
        try:
            scenes = [_scene_from_row(row) for row in (scenes_snapshot or []) if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"任务快照解析失败：{exc}", "ASF001")
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
        return self._start_asf_download_for_scenes(
            scenes,
            label=f"任务快照（选中 {len(scenes)} 景）",
            output_dir=output_dir,
            credential_source=credential_source,
            max_concurrent=max_concurrent,
            use_product_subdirs=use_product_subdirs,
        )

    def _start_asf_download_for_scenes(
        self,
        scenes: list[Any],
        *,
        label: str,
        output_dir: str = "",
        credential_source: str = "auto",
        max_concurrent: int = 1,
        use_product_subdirs: bool = False,
    ) -> dict:
        if not scenes:
            return _error_msg("请先选择要下载的 SAR 影像", "ASF001")
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定输出根目录", "GUI003")
        try:
            from insar_prep.providers.asf.credentials import CredentialSource, resolve_credentials

            src = CredentialSource((credential_source or "auto").strip().lower())
        except Exception:  # noqa: BLE001
            return _error_msg(f"未知凭据来源：{credential_source}", "GUI003")
        try:
            resolved = resolve_credentials(src)
        except InsarPrepError:
            return _error_msg(
                "开始 Sentinel-1 下载前，请先在设置中保存 Earthdata Token 或账号密码。",
                "DL004",
            )
        except Exception as exc:  # noqa: BLE001
            return _error_msg(
                f"Earthdata 凭据检查失败：{exc}",
                "DL004",
            )
        workers = max(1, min(int(max_concurrent or 1), 8))
        proxy_url = ""
        trust_env = False
        asf_ssl_verify = bool(self._network_settings.get("asf_ssl_verify", True))
        try:
            from insar_prep.providers.asf.downloader import (
                RealAsfDownloader,
                download_requests_from_scenes,
            )

            use_subdirs = _coerce_bool(use_product_subdirs, False)
            requests = download_requests_from_scenes(
                scenes,
                slc_dir=Path(out),
                use_product_subdirs=use_subdirs,
                product_subdir_base=Path(out) if use_subdirs else None,
            )
            if not requests:
                return _error_msg("当前影像没有 ASF 下载 URL，请先重新检索或导入 ASF 官方文件。", "ASF003")
            chosen_network: dict[str, Any] | None = None
            preflight_notes: list[str] = []
            code = "DL005"
            for network_mode in _asf_network_candidates(self._network_settings):
                preflight = RealAsfDownloader(
                    resolved=resolved,
                    proxy_url=network_mode["proxy_url"],
                    ssl_verify=network_mode["ssl_verify"],
                    trust_env=network_mode["trust_env"],
                    verify_bytes=64 * 1024,
                    timeout=45.0,
                ).verify(requests[0])
                if preflight.outcome.value == "verified":
                    chosen_network = network_mode
                    break
                detail = preflight.message or "网络预检未通过"
                code = preflight.error_code or code
                preflight_notes.append(f"{network_mode['label']}：{detail}")
                if code == "DL004":
                    break
            if chosen_network is None:
                detail = "；".join(preflight_notes[:6]) or "网络预检未通过"
                self._act(f"ASF 下载预检失败：{detail}", kind="warning")
                return _error_msg(f"ASF 下载预检失败：{detail}", code)
            proxy_url = str(chosen_network["proxy_url"])
            asf_ssl_verify = bool(chosen_network["ssl_verify"])
            trust_env = bool(chosen_network["trust_env"])
            if chosen_network["label"] != "当前网络设置":
                self._act(
                    f"已自动改用 ASF 可用网络方案：{chosen_network['label']}",
                    kind="settings",
                )
            if getattr(resolved, "username", None) or getattr(resolved, "use_netrc", False):
                self._act("已使用保存的 Earthdata 账号自动刷新下载 token", kind="settings")
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001 - preflight should be explicit
            return _error_msg(f"ASF 下载预检失败：{exc}", "DL005")
        self._act(
            f"开始 Sentinel-1 下载：{label}（{len(scenes)} 景，并发 {workers}）",
            kind="download",
        )
        self._forget_deleted_archive_key("asf", out, use_product_subdirs=use_subdirs)
        result = self._asf_download.start(
            scenes,
            out,
            credential_source=src,
            max_concurrent=workers,
            proxy_url=proxy_url,
            ssl_verify=asf_ssl_verify,
            trust_env=trust_env,
            use_product_subdirs=use_subdirs,
            activity=self._activity,
        )
        get_status = getattr(self._asf_download, "get_status", None)
        if callable(get_status):
            self._archive_asf_status(get_status())
        return result

    def append_asf_download(
        self,
        output_dir: str = "",
        max_extra_workers: int = 0,
        scene_ids: list[str] | None = None,
        task_id: str = "",
    ) -> dict:
        """Append selected ASF scenes to the currently running/paused download."""
        scenes, _, label = self._active_scene_context()
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
            label = f"{label}（追加 {len(scenes)} 景）"
        if not scenes:
            return _error_msg("请先勾选要追加下载的 SAR 影像", "ASF001")
        status = self._asf_download.get_status()
        out = output_dir.strip() or str(status.get("output_dir") or "") or self._default_output()
        result = self._asf_download.append(
            scenes,
            out,
            max_extra_workers=max(0, min(int(max_extra_workers or 0), 8)),
            task_id=str(task_id or "").strip(),
        )
        if result.get("ok"):
            self._act(
                f"追加 Sentinel-1 下载：{label}（新增 {result.get('appended', 0)} 景）",
                kind="download",
            )
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def pause_asf_scenes(self, scene_ids: list[str] | None = None, task_id: str = "") -> dict:
        """Pause only selected ASF scenes without pausing the whole task."""
        result = self._asf_download.pause_scenes(scene_ids or [], task_id=str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def append_asf_download_snapshot(
        self,
        output_dir: str = "",
        scenes_snapshot: list[dict[str, Any]] | None = None,
        scene_ids: list[str] | None = None,
        max_extra_workers: int = 0,
        task_id: str = "",
    ) -> dict:
        """Append scenes from a frozen UI task snapshot to a specific ASF task."""
        try:
            scenes = [_scene_from_row(row) for row in (scenes_snapshot or []) if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            return _error_msg(f"任务快照解析失败：{exc}", "ASF001")
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if selected_ids:
            scenes = [scene for scene in scenes if str(getattr(scene, "scene_id", "")) in selected_ids]
        if not scenes:
            return _error_msg("请先勾选要追加下载的 SAR 影像", "ASF001")
        out = output_dir.strip()
        result = self._asf_download.append(
            scenes,
            out or None,
            max_extra_workers=max(0, min(int(max_extra_workers or 0), 8)),
            task_id=str(task_id or "").strip(),
        )
        if result.get("ok"):
            self._act(
                f"追加 Sentinel-1 任务快照下载：新增 {result.get('appended', 0)} 景",
                kind="download",
            )
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def resume_asf_scenes(self, scene_ids: list[str] | None = None, task_id: str = "") -> dict:
        """Resume selected scene-level pauses."""
        result = self._asf_download.resume_scenes(scene_ids or [], task_id=str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def pause_asf_download(self, task_id: str = "") -> dict:
        """Pause between scenes (current scene finishes first)."""
        result = self._asf_download.pause(str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def resume_asf_download(self, task_id: str = "") -> dict:
        """Resume a paused download."""
        result = self._asf_download.resume(str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def stop_asf_download(self, task_id: str = "") -> dict:
        """Cancel the in-progress download."""
        result = self._asf_download.stop(str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def retry_asf_download(self, task_id: str = "") -> dict:
        """Retry only failed/interrupted scenes from the previous ASF download."""
        result = self._asf_download.retry_failed(activity=self._activity, task_id=str(task_id or "").strip())
        self._archive_asf_status(self._asf_download.get_status())
        return result

    def get_download_status(self) -> dict:
        """Poll ASF download progress (state, counts, recent log lines)."""
        status = self._asf_download.get_status()
        self._archive_asf_status(status)
        return status

    def plan_dem_download(self, output_dir: str = "", dataset: str = "COP30") -> dict:
        """Build + validate (dry-run) the DEM request plan for the region AOI."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        return self._plan_dem_request(
            region_id=region.region_id,
            region_safe_name=region.region_safe_name,
            processing_aoi=region.aoi,
            output_dir=output_dir,
            dataset=dataset,
            activity_label=f"DEM 下载规划：{region.region_name}",
        )

    def plan_dem_download_bbox(
        self,
        west: float,
        east: float,
        south: float,
        north: float,
        output_dir: str = "",
        dataset: str = "COP30",
    ) -> dict:
        """Build + validate a standalone DEM request plan from a bbox."""
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM bbox 规划", exc)
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("独立 DEM 任务需要先指定输出根目录", "GUI003")
        try:
            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "AOI001")
        return self._plan_dem_request(
            region_id="standalone_dem",
            region_safe_name="standalone_dem",
            processing_aoi=aoi,
            output_dir=out,
            dataset=dataset,
            activity_label="独立 DEM 下载规划",
        )

    def plan_dem_conversion_bbox(
        self,
        west: float,
        east: float,
        south: float,
        north: float,
        output_dir: str = "",
        dataset: str = "COP30",
    ) -> dict:
        """Build + validate a standalone DEM conversion plan from a bbox."""
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM bbox 规划", exc)
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("独立 DEM 转换任务需要先指定输出根目录", "GUI003")
        try:
            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
            request_plan, _ = self._create_dem_request_plan(
                region_id="standalone_dem",
                region_safe_name="standalone_dem",
                processing_aoi=aoi,
                output_dir=out,
                dataset=dataset,
            )
            from insar_prep.providers.dem.conversion_planner import (
                create_dem_conversion_plan,
                validate_dem_conversion_plan,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        try:
            conv_plan = create_dem_conversion_plan(request_plan)
            report = validate_dem_conversion_plan(conv_plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM004")
        self._act(f"独立 DEM 转换规划：{conv_plan.dataset}", kind="download")
        return {
            "ok": True,
            "dataset": self._dem_dataset,
            "auto": _conversion_summary(conv_plan),
            "plan": _dump(conv_plan),
            "report": _dump(report),
        }

    def run_dem_download(
        self,
        output_dir: str = "",
        dataset: str = "COP30",
        key_source: str = "auto",
        convert: bool = True,
    ) -> dict:
        """Download the current region's DEM via OpenTopography."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域，或使用独立 bbox 下载 DEM", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        dataset = _normalise_downloadable_dem_dataset(dataset, fallback="")
        if not dataset:
            return _error_msg(
                "当前选择的是本地 DEM 来源，不能执行在线下载；请选择一个 OpenTopography 数据集，"
                "或在“本地 DEM 转换”中选择已有 DEM 文件。",
                "DEM001",
            )
        try:
            plan, _ = self._create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_dir=output_dir,
                dataset=dataset,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        if not bool(convert):
            return self._run_dem_download_plan(plan, output_dir, key_source)
        return self._run_dem_download_and_conversion_plan(plan, output_dir, key_source)

    def run_dem_download_bbox(
        self,
        west: float,
        east: float,
        south: float,
        north: float,
        output_dir: str = "",
        dataset: str = "COP30",
        key_source: str = "auto",
        convert: bool = True,
    ) -> dict:
        """Download a standalone DEM from a bbox via OpenTopography."""
        dataset = _normalise_downloadable_dem_dataset(dataset, fallback="")
        if not dataset:
            return _error_msg(
                "当前选择的是本地 DEM 来源，不能执行在线下载；请选择一个 OpenTopography 数据集，"
                "或在“本地 DEM 转换”中选择已有 DEM 文件。",
                "DEM001",
            )
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox

            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
            plan, _ = self._create_dem_request_plan(
                region_id="standalone_dem",
                region_safe_name="standalone_dem",
                processing_aoi=aoi,
                output_dir=output_dir,
                dataset=dataset,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        if not bool(convert):
            return self._run_dem_download_plan(plan, output_dir, key_source)
        return self._run_dem_download_and_conversion_plan(plan, output_dir, key_source)

    def start_dem_download(
        self,
        output_dir: str = "",
        dataset: str = "COP30",
        key_source: str = "auto",
        convert: bool = True,
    ) -> dict:
        """Start the current region's DEM download in a cancellable background job."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域，或使用独立 bbox 下载 DEM", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        dataset = _normalise_downloadable_dem_dataset(dataset, fallback="")
        if not dataset:
            return _error_msg(
                "当前选择的是本地 DEM 来源，不能执行在线下载；请选择一个 OpenTopography 数据集，"
                "或在“本地 DEM 转换”中选择已有 DEM 文件。",
                "DEM001",
            )
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定 DEM 下载输出根目录", "GUI003")
        try:
            plan, _ = self._create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_dir=out,
                dataset=dataset,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        self._act(f"开始 DEM 下载：{dataset}", kind="download")
        return self._dem_download.start(
            plan,
            out,
            key_source=key_source,
            convert=bool(convert),
            activity=self._activity,
        )

    def start_dem_download_bbox(
        self,
        west: float,
        east: float,
        south: float,
        north: float,
        output_dir: str = "",
        dataset: str = "COP30",
        key_source: str = "auto",
        convert: bool = True,
    ) -> dict:
        """Start a standalone bbox DEM download in a cancellable background job."""
        dataset = _normalise_downloadable_dem_dataset(dataset, fallback="")
        if not dataset:
            return _error_msg(
                "当前选择的是本地 DEM 来源，不能执行在线下载；请选择一个 OpenTopography 数据集，"
                "或在“本地 DEM 转换”中选择已有 DEM 文件。",
                "DEM001",
            )
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定 DEM 下载输出根目录", "GUI003")
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox

            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
            plan, _ = self._create_dem_request_plan(
                region_id="standalone_dem",
                region_safe_name="standalone_dem",
                processing_aoi=aoi,
                output_dir=out,
                dataset=dataset,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        self._act(f"开始独立 DEM 下载：{dataset}", kind="download")
        return self._dem_download.start(
            plan,
            out,
            key_source=key_source,
            convert=bool(convert),
            activity=self._activity,
        )

    def stop_dem_download(self) -> dict:
        """Request cancellation for the active DEM download."""
        return self._dem_download.stop()

    def get_dem_download_status(self) -> dict:
        """Return current background DEM download status."""
        return self._dem_download.get_status()

    def run_dem_conversion(self, output_dir: str = "") -> dict:
        """Run DEM vertical-datum conversion for the current region."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域，或使用独立 bbox 转换 DEM", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        try:
            plan, _ = self._create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_dir=output_dir,
                dataset=self._dem_dataset,
            )
            from insar_prep.providers.dem.conversion_planner import create_dem_conversion_plan

            conv_plan = create_dem_conversion_plan(plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        return self._run_dem_conversion_plan(conv_plan, output_dir)

    def run_dem_conversion_bbox(
        self,
        west: float,
        east: float,
        south: float,
        north: float,
        output_dir: str = "",
        dataset: str = "COP30",
    ) -> dict:
        """Run DEM vertical-datum conversion for a standalone bbox."""
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox
            from insar_prep.providers.dem.conversion_planner import create_dem_conversion_plan

            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
            plan, _ = self._create_dem_request_plan(
                region_id="standalone_dem",
                region_safe_name="standalone_dem",
                processing_aoi=aoi,
                output_dir=output_dir,
                dataset=dataset,
            )
            conv_plan = create_dem_conversion_plan(plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        return self._run_dem_conversion_plan(conv_plan, output_dir)

    def plan_local_dem_conversion(
        self,
        input_path: str,
        output_dir: str = "",
        source_vertical_datum: str = "auto",
    ) -> dict:
        """Inspect a user-provided DEM and build a conversion plan for it."""
        try:
            conv_plan, report, detected = self._create_local_dem_conversion_plan(
                input_path=input_path,
                output_dir=output_dir,
                source_vertical_datum=source_vertical_datum,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except ImportError as exc:
            return _missing_dep("本地 DEM 识别", exc)
        except Exception as exc:  # noqa: BLE001
            if _is_dem_component_environment_error(exc):
                return _dem_component_error("本地 DEM 识别", exc)
            return _error_msg(str(exc), "DEM004")
        self._act(f"本地 DEM 转换规划：{Path(input_path).name}", kind="download")
        return {
            "ok": True,
            "dataset": "USER_LOCAL",
            "auto": _conversion_summary(conv_plan),
            "plan": _dump(conv_plan),
            "report": _dump(report),
            "detected": detected,
        }

    def run_local_dem_conversion(
        self,
        input_path: str,
        output_dir: str = "",
        source_vertical_datum: str = "auto",
        output_mode: str = "sarscape",
    ) -> dict:
        """Convert/copy a user-provided DEM into SARscape-ready outputs."""
        try:
            conv_plan, _, _ = self._create_local_dem_conversion_plan(
                input_path=input_path,
                output_dir=output_dir,
                source_vertical_datum=source_vertical_datum,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except ImportError as exc:
            return _missing_dep("本地 DEM 转换", exc)
        except Exception as exc:  # noqa: BLE001
            if _is_dem_component_environment_error(exc):
                return _dem_component_error("本地 DEM 转换", exc)
            return _error_msg(str(exc), "DEM004")
        out = (output_dir or "").strip() or self._default_output() or str(Path(input_path).parent)
        mode = (output_mode or "sarscape").strip().lower()
        if mode not in {"ellipsoid", "sarscape"}:
            mode = "sarscape"
        return self._run_dem_conversion_plan(conv_plan, out, output_mode=mode)

    def plan_gacos_request(self, output_dir: str = "") -> dict:
        """Build + validate (dry-run) the GACOS request plan for the region."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        if not region.scenes:
            return _error_msg("GACOS 需要场景日期，请先导入影像", "GAC001")
        try:
            from insar_prep.providers.gacos.planner import (
                create_gacos_request_plan,
                validate_gacos_request_plan,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("GACOS 规划", exc)
        out = output_dir.strip() or self._default_output()
        try:
            plan = create_gacos_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                scenes=region.scenes,
                output_root=out,
            )
            report = validate_gacos_request_plan(plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC001")
        dates = len(getattr(plan, "unique_dates", []) or [])
        self._act(f"GACOS 请求规划：{dates} 个日期", kind="download")
        return {"ok": True, "plan": _dump(plan), "report": _dump(report)}

    def get_credential_status(self) -> dict:
        """Return privacy-safe credential status for ASF / OpenTopo / GACOS."""

        def _safe(loader) -> str:
            try:
                fn = loader()
            except Exception:  # noqa: BLE001
                return "unavailable"
            try:
                return fn()
            except Exception:  # noqa: BLE001 - keyring missing or backend error
                return "unavailable"

        def _asf():
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                EARTHDATA_TOKEN_ENV,
                resolve_credentials,
                stored_credential_status,
            )

            def status() -> str:
                try:
                    stored = stored_credential_status()
                except Exception:  # noqa: BLE001
                    stored = "unavailable"
                if stored not in {"none", "unavailable"}:
                    return stored
                if os.environ.get(EARTHDATA_TOKEN_ENV):
                    return "env-token"
                try:
                    resolved = resolve_credentials(CredentialSource.NETRC)
                except Exception:  # noqa: BLE001
                    return "unavailable" if stored == "unavailable" else "none"
                return "netrc" if resolved.use_netrc else resolved.source.value

            return status

        def _dem():
            from insar_prep.providers.dem.credentials import stored_api_key_status

            return stored_api_key_status

        def _gacos():
            from insar_prep.providers.gacos.credentials import stored_gacos_email_status

            return stored_gacos_email_status

        return {
            "ok": True,
            "earthdata": _safe(_asf),
            "opentopography": _safe(_dem),
            "gacos": _safe(_gacos),
        }

    def _cached_earthdata_auth_failure(self) -> dict | None:
        now = time.monotonic()
        if not self._earthdata_auth_failure_cache or now >= self._earthdata_auth_failure_until:
            self._earthdata_auth_failure_cache = None
            self._earthdata_auth_failure_until = 0.0
            return None
        remaining_minutes = max(1, int((self._earthdata_auth_failure_until - now + 59) // 60))
        cached = dict(self._earthdata_auth_failure_cache)
        message = str(cached.get("message") or "Earthdata/ASF 凭据未通过检测。")
        cached["message"] = f"{message} 为保护账号，{remaining_minutes} 分钟内不会重复请求登录接口。"
        return cached

    def _cached_earthdata_auth_success(self) -> dict | None:
        now = time.monotonic()
        if not self._earthdata_auth_success_cache or now >= self._earthdata_auth_success_until:
            self._earthdata_auth_success_cache = None
            self._earthdata_auth_success_until = 0.0
            return None
        cached = dict(self._earthdata_auth_success_cache)
        cached["message"] = "Earthdata/ASF 凭据最近已通过检测，当前会话内直接复用该状态。"
        return cached

    def _remember_earthdata_auth_failure(self, result: dict) -> dict:
        self._earthdata_auth_failure_cache = dict(result)
        self._earthdata_auth_failure_until = time.monotonic() + _EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS
        self._earthdata_auth_success_cache = None
        self._earthdata_auth_success_until = 0.0
        return result

    def _remember_earthdata_auth_success(self, result: dict) -> dict:
        self._earthdata_auth_success_cache = dict(result)
        self._earthdata_auth_success_until = time.monotonic() + _EARTHDATA_AUTH_SUCCESS_CACHE_SECONDS
        self._earthdata_auth_failure_cache = None
        self._earthdata_auth_failure_until = 0.0
        return result

    def _clear_earthdata_auth_failure(self) -> None:
        self._earthdata_auth_failure_cache = None
        self._earthdata_auth_failure_until = 0.0
        self._earthdata_auth_success_cache = None
        self._earthdata_auth_success_until = 0.0

    @staticmethod
    def _earthdata_candidate_key(resolved: object) -> str:
        token = str(getattr(resolved, "token", "") or "")
        username = str(getattr(resolved, "username", "") or "")
        password = str(getattr(resolved, "password", "") or "")
        use_netrc = str(bool(getattr(resolved, "use_netrc", False)))
        source = str(getattr(getattr(resolved, "source", ""), "value", getattr(resolved, "source", "")))
        raw = "\0".join([source, token, username, password, use_netrc])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cached_earthdata_candidate_failure(self, key: str) -> dict | None:
        until = self._earthdata_candidate_failure_until.get(key, 0.0)
        now = time.monotonic()
        if until <= now:
            self._earthdata_candidate_failure_until.pop(key, None)
            self._earthdata_candidate_failure_message.pop(key, None)
            return None
        remaining_minutes = max(1, int((until - now + 59) // 60))
        message = self._earthdata_candidate_failure_message.get(
            key,
            "这组 Earthdata/ASF 凭据刚刚校验失败。",
        )
        return _error_msg(
            f"{message} 为保护账号，{remaining_minutes} 分钟内不会对同一组账号/token 重复请求登录接口；"
            "请确认输入后修改凭据再保存。",
            "DL004",
        )

    def _remember_earthdata_candidate_failure(self, key: str, message: str) -> None:
        self._earthdata_candidate_failure_until[key] = (
            time.monotonic() + _EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS
        )
        self._earthdata_candidate_failure_message[key] = message

    def _earthdata_network_options(self) -> dict[str, Any]:
        proxy_enabled = bool(self._network_settings.get("proxy_enabled"))
        proxy_url = (
            _normalise_proxy_url(self._network_settings.get("proxy_url"))
            if proxy_enabled
            else ""
        )
        if proxy_enabled and not proxy_url:
            proxy_url = _detect_system_proxy()
        return {
            "proxy_url": proxy_url,
            "ssl_verify": bool(self._network_settings.get("asf_ssl_verify", True)),
            "trust_env": proxy_enabled,
        }

    def _probe_earthdata_resolved(self, resolved: object) -> dict:
        from insar_prep.providers.asf.downloader import probe_earthdata_auth

        network = self._earthdata_network_options()
        ok, message = probe_earthdata_auth(
            resolved,  # type: ignore[arg-type]
            proxy_url=network["proxy_url"],
            ssl_verify=network["ssl_verify"],
            trust_env=network["trust_env"],
            timeout=20.0,
        )
        if ok:
            return {
                "ok": True,
                "configured": True,
                "status": "valid",
                "message": "Earthdata/ASF 凭据正常。",
            }
        status = "expired" if "401" in message or "403" in message or "rejected" in message else "unknown"
        return {
            "ok": True,
            "configured": True,
            "status": status,
            "message": message,
        }

    def _validate_earthdata_candidate(self, resolved: object) -> dict:
        key = self._earthdata_candidate_key(resolved)
        cached = self._cached_earthdata_candidate_failure(key)
        if cached is not None:
            return cached
        try:
            auth = self._probe_earthdata_resolved(resolved)
        except Exception as exc:  # noqa: BLE001
            message = f"Earthdata/ASF 凭据校验不可用，未保存：{mask_text(str(exc))}"
            self._remember_earthdata_candidate_failure(key, message)
            return _error_msg(message, "DL004")
        if auth.get("status") == "valid":
            self._earthdata_candidate_failure_until.pop(key, None)
            self._earthdata_candidate_failure_message.pop(key, None)
            return auth
        message = (
            "Earthdata/ASF 凭据校验失败，未保存；原有凭据保持不变。"
            f"{auth.get('message') or ''}"
        )
        self._remember_earthdata_candidate_failure(key, message)
        return _error_msg(message, "DL004")

    def _validate_opentopography_key(self, api_key: str) -> dict:
        api_key = str(api_key or "").strip()
        if not api_key:
            return _error_msg("OpenTopography API Key 不能为空，未保存。", "DEM005")
        try:
            from insar_prep.core.models import BBox
            from insar_prep.providers.dem.credentials import DemKeySource, ResolvedDemKey
            from insar_prep.providers.dem.downloader import (
                DemDownloadOutcome,
                DemDownloadRequest,
                RealDemDownloader,
            )

            resolved = ResolvedDemKey(source=DemKeySource.KEYRING, api_key=api_key)
            request = DemDownloadRequest(
                region_safe_name="credential_probe",
                dataset="COP30",
                demtype="COP30",
                bbox=BBox(west=110.0, east=110.02, south=30.0, north=30.02),
                destination=self._default_cache_dir() / "_credential_probe" / "opentopo_probe.tif",
            )
            result = RealDemDownloader(
                resolved=resolved,
                max_retries=1,
                timeout=20.0,
            ).verify(request)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(
                f"OpenTopography API Key 联网校验不可用，未保存：{mask_text(str(exc))}",
                "DEM005",
            )
        if result.outcome == DemDownloadOutcome.VERIFIED:
            return {
                "ok": True,
                "message": "OpenTopography API Key 校验通过。",
            }
        code = result.error_code or "DEM005"
        prefix = "OpenTopography API Key 校验失败，未保存"
        if code != "DEM005":
            prefix = "OpenTopography API Key 无法完成联网校验，未保存"
        return _error_msg(f"{prefix}：{mask_text(result.message)}", code)

    def check_earthdata_auth(self, force: bool = False) -> dict:
        """Probe saved Earthdata credentials and report only user-actionable states."""
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                resolve_credentials,
                stored_credential_status,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": True,
                "configured": False,
                "status": "unavailable",
                "message": f"Earthdata 凭据检查不可用：{exc}",
            }

        cached_failure = self._cached_earthdata_auth_failure()
        if cached_failure is not None:
            return cached_failure
        if not bool(force):
            cached_success = self._cached_earthdata_auth_success()
            if cached_success is not None:
                return cached_success

        try:
            stored = stored_credential_status()
        except Exception:  # noqa: BLE001
            stored = "unavailable"
        try:
            resolved = resolve_credentials(CredentialSource.AUTO)
        except Exception as exc:  # noqa: BLE001
            if stored in {"none", "unavailable"}:
                return {
                    "ok": True,
                    "configured": False,
                    "status": "missing",
                    "message": "未保存 Earthdata/ASF 凭据。",
                }
            return self._remember_earthdata_auth_failure({
                "ok": True,
                "configured": True,
                "status": "invalid",
                "message": f"Earthdata 凭据无法读取：{exc}",
            })

        try:
            result = self._probe_earthdata_resolved(resolved)
        except Exception as exc:  # noqa: BLE001
            result = {
                "ok": True,
                "configured": True,
                "status": "unknown",
                "message": f"Earthdata/ASF 凭据联网检测失败：{mask_text(str(exc))}",
            }
        if result.get("status") == "valid":
            return self._remember_earthdata_auth_success(result)
        return self._remember_earthdata_auth_failure(result)

    def save_earthdata_token(self, token: str) -> dict:
        """Store a NASA Earthdata bearer token in the OS keyring."""
        token = str(token or "").strip()
        if not token:
            return _error_msg("Earthdata Token 不能为空，未保存。", "DL004")
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                ResolvedCredential,
                store_token,
            )

            auth = self._validate_earthdata_candidate(
                ResolvedCredential(source=CredentialSource.KEYRING, token=token)
            )
            if not auth.get("ok"):
                return auth
            store_token(token)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._clear_earthdata_auth_failure()
        self._remember_earthdata_auth_success(auth)
        self._act("Earthdata Token 校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "auth": auth}

    def save_earthdata_login(self, username: str, password: str) -> dict:
        """Store NASA Earthdata username/password in the OS keyring."""
        username = str(username or "").strip()
        password = str(password or "")
        if not username or not password:
            return _error_msg("Earthdata 用户名和密码都不能为空，未保存。", "DL004")
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                ResolvedCredential,
                store_login,
            )

            auth = self._validate_earthdata_candidate(
                ResolvedCredential(
                    source=CredentialSource.KEYRING,
                    username=username,
                    password=password,
                )
            )
            if not auth.get("ok"):
                return auth
            store_login(username, password)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._clear_earthdata_auth_failure()
        self._remember_earthdata_auth_success(auth)
        self._act("Earthdata 登录凭据校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "auth": auth}

    def clear_earthdata_credentials(self) -> dict:
        """Remove stored NASA Earthdata credentials from the OS keyring."""
        try:
            from insar_prep.providers.asf.credentials import clear_stored_credentials

            removed = clear_stored_credentials()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._clear_earthdata_auth_failure()
        self._act("已清除 Earthdata 凭据", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}

    def save_opentopography_key(self, api_key: str) -> dict:
        """Store an OpenTopography API key in the OS keyring."""
        api_key = str(api_key or "").strip()
        check = self._validate_opentopography_key(api_key)
        if not check.get("ok"):
            return check
        try:
            from insar_prep.providers.dem.credentials import store_api_key

            store_api_key(api_key)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM005")
        self._act("OpenTopography API Key 校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "check": check}

    def clear_opentopography_key(self) -> dict:
        """Remove the stored OpenTopography API key from the OS keyring."""
        try:
            from insar_prep.providers.dem.credentials import clear_stored_api_key

            removed = clear_stored_api_key()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM005")
        self._act("已清除 OpenTopography API Key", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}

    def save_gacos_email(self, email: str) -> dict:
        """Store a GACOS delivery email in the OS keyring."""
        try:
            from insar_prep.providers.gacos.credentials import store_gacos_email

            store_gacos_email(email)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC003")
        self._act("已保存 GACOS 接收邮箱", kind="settings")
        return {"ok": True, "status": self.get_credential_status()}

    def clear_gacos_email(self) -> dict:
        """Remove the stored GACOS delivery email from the OS keyring."""
        try:
            from insar_prep.providers.gacos.credentials import clear_stored_gacos_email

            removed = clear_stored_gacos_email()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC003")
        self._act("已清除 GACOS 接收邮箱", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}

    # ------------------------------------------------------- 4. DEM CONVERT
    def plan_dem_conversion(self, output_dir: str = "") -> dict:
        """Auto-detect + validate (dry-run) the vertical-datum conversion.

        The method (whether to convert at all, and which geoid model) is derived
        from the session's DEM dataset; the user never picks it. Some datasets are
        already ellipsoidal, in which case no conversion is needed.
        """
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        try:
            from insar_prep.providers.dem.conversion_planner import (
                create_dem_conversion_plan,
                validate_dem_conversion_plan,
            )
            from insar_prep.providers.dem.planner import create_dem_request_plan
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 转换规划", exc)
        out = output_dir.strip() or self._default_output()
        try:
            request_plan = create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_root=out,
                dataset=self._dem_dataset,
                **self._dem_source_kwargs(),
            )
            conv_plan = create_dem_conversion_plan(request_plan)
            report = validate_dem_conversion_plan(conv_plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM004")
        return {
            "ok": True,
            "dataset": self._dem_dataset,
            "auto": _conversion_summary(conv_plan),
            "plan": _dump(conv_plan),
            "report": _dump(report),
        }

    # ----------------------------------------------------------- 5. REPORT
    def generate_report(self, output_dir: str = "") -> dict:
        """Generate the five-file data-preparation report set for the region."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请提供报告输出目录", "GUI003")
        try:
            from insar_prep.reporting.generator import (
                build_data_preparation_report,
                save_report,
            )
            from insar_prep.reporting.html import (
                html_report_path_for,
                save_report_html,
            )
            from insar_prep.reporting.manifest import (
                build_manifest_rows,
                manifest_path_for,
                write_manifest_csv,
            )
            from insar_prep.reporting.warnings import (
                build_warning_rows,
                warnings_path_for,
                write_warnings_csv,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("报告生成", exc)

        gathered = self._gather_reports(region, out)
        ws = self._state.workspace
        try:
            Path(out).mkdir(parents=True, exist_ok=True)
            report = build_data_preparation_report(
                workspace_id=ws.workspace_id if ws is not None else None,
                project_id=self._state.current_project_id,
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
            )
            output = save_report(report, out)
            reports_dir = output.json_path.parent

            html_path = html_report_path_for(reports_dir, region.region_safe_name)
            save_report_html(report, html_path)

            manifest_path = manifest_path_for(reports_dir, region.region_safe_name)
            manifest_rows = build_manifest_rows(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                report=report,
                scenes=region.scenes,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
                json_report_path=output.json_path,
                markdown_report_path=output.markdown_path,
                manifest_csv_path=manifest_path,
            )
            write_manifest_csv(manifest_path, manifest_rows)

            warnings_path = warnings_path_for(reports_dir, region.region_safe_name)
            warning_rows = build_warning_rows(
                region_safe_name=region.region_safe_name,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
            )
            write_warnings_csv(warnings_path, warning_rows)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "REP001")

        self._act(
            f"生成数据准备报告：{region.region_name} → {html_path.name}",
            kind="report",
        )
        return {
            "ok": True,
            "report": _dump(report),
            "reports_dir": str(reports_dir),
            "included": [k for k, v in gathered.items() if v is not None],
            "paths": {
                "json": str(output.json_path),
                "markdown": str(output.markdown_path),
                "html": str(html_path),
                "manifest": str(manifest_path),
                "warnings": str(warnings_path),
            },
        }

    # --------------------------------------------------------------- helpers
    def _active_scene_context(self) -> tuple[list[Any], str, str]:
        """Return scenes plus a safe output label for region or standalone use."""
        region = self._state.current_region()
        if region is not None:
            return region.scenes, region.region_safe_name, region.region_name
        return self._standalone_scenes, "standalone_download", "独立下载任务"

    def _orbit_scene_context(self, scene_ids: list[str] | None = None) -> tuple[list[Any], str]:
        """Return orbit candidates without disturbing the Sentinel-1 download list."""
        selected_ids = {str(item).strip() for item in (scene_ids or []) if str(item).strip()}
        if self._orbit_candidate_scenes:
            scenes = self._orbit_candidate_scenes
            if selected_ids:
                matched = [
                    scene
                    for scene in scenes
                    if str(getattr(scene, "scene_id", "")) in selected_ids
                ]
                if matched:
                    return matched, f"精密轨道候选 (selected {len(matched)} scenes)"
            elif scenes:
                return scenes, "精密轨道候选"
        scenes, _, label = self._active_scene_context()
        if selected_ids:
            scenes = [
                scene
                for scene in scenes
                if str(getattr(scene, "scene_id", "")) in selected_ids
            ]
            label = f"{label} (selected {len(scenes)} scenes)"
        return scenes, label

    @staticmethod
    def _idle_metadata_status() -> dict[str, Any]:
        return {
            "state": "idle",
            "done": 0,
            "total": 0,
            "percent": 0,
            "message": "",
        }

    def _set_metadata_status(self, state: str, done: int, total: int, message: str) -> None:
        total = max(0, int(total or 0))
        done = max(0, min(int(done or 0), total if total else int(done or 0)))
        percent = int(round((done / total) * 100)) if total else (100 if state == "finished" else 0)
        self._metadata_status = {
            "state": state,
            "done": done,
            "total": total,
            "percent": percent,
            "message": message,
        }

    def _store_imported_scenes(self, scenes: list[Any]) -> tuple[list[Any], str]:
        """Attach imported scenes to the current region, or keep them standalone."""
        scenes = _sort_scenes_by_acquisition_date(scenes)
        region = self._state.current_region()
        if region is None:
            self._standalone_scenes = scenes
            return self._standalone_scenes, "独立下载任务"
        region = self._state.set_current_region_scenes(scenes)
        self._save_state()
        return region.scenes, region.region_name

    def _create_dem_request_plan(
        self,
        *,
        region_id: str,
        region_safe_name: str,
        processing_aoi: Any,
        output_dir: str,
        dataset: str,
    ) -> tuple[Any, Any]:
        """Create and validate a DEM request plan object."""
        from insar_prep.providers.dem.planner import (
            create_dem_request_plan,
            validate_dem_request_plan,
        )

        if dataset.strip():
            self._dem_dataset = _normalise_downloadable_dem_dataset(dataset)
        out = output_dir.strip() or self._default_output()
        if not out:
            raise ValueError("请指定输出根目录")
        plan = create_dem_request_plan(
            region_id=region_id,
            region_safe_name=region_safe_name,
            processing_aoi=processing_aoi,
            output_root=out,
            dataset=self._dem_dataset,
            **self._dem_source_kwargs(),
        )
        report = validate_dem_request_plan(plan)
        return plan, report

    def _plan_dem_request(
        self,
        *,
        region_id: str,
        region_safe_name: str,
        processing_aoi: Any,
        output_dir: str,
        dataset: str,
        activity_label: str,
    ) -> dict:
        """Return a JSON-friendly DEM request planning envelope."""
        try:
            plan, report = self._create_dem_request_plan(
                region_id=region_id,
                region_safe_name=region_safe_name,
                processing_aoi=processing_aoi,
                output_dir=output_dir,
                dataset=dataset,
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_format_validation(exc), "DEM004")
        self._act(f"{activity_label}：{plan.dataset}", kind="download")
        return {"ok": True, "plan": _dump(plan), "report": _dump(report)}

    def _run_dem_download_plan(
        self, plan: Any, output_dir: str, key_source: str = "auto"
    ) -> dict:
        """Run one DEM download plan and return a JSON-safe summary."""
        try:
            from insar_prep.providers.dem.credentials import DemKeySource
            from insar_prep.providers.dem.downloader import opentopo_demtype
            from insar_prep.providers.dem.download_runner import run_dem_download

            source = DemKeySource((key_source or "auto").strip().lower())
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 下载执行", exc)
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定 DEM 下载输出根目录", "GUI003")
        dataset = str(getattr(plan, "dataset", "") or "").strip().upper()
        if not dataset or opentopo_demtype(dataset) is None:
            return _error_msg(
                f"{dataset or '当前 DEM 来源'} 不能通过 OpenTopography 在线下载；"
                "如需处理已有 DEM，请使用“本地 DEM 转换”选择本机 tif/img/vrt 文件。",
                "DEM001",
            )
        try:
            logs = [_ui_log(f"开始 DEM 下载：{getattr(plan, 'dataset', '')} → {out}")]
            summary = run_dem_download([plan], out, key_source=source)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM001")
        logs.extend(_dem_result_logs(list(summary.results), prefix="DEM 下载"))
        logs.append(_ui_log(f"DEM 下载完成：{summary.summary_line()}"))
        self._act(f"DEM 下载完成：{summary.summary_line()}", kind="download")
        return {
            "ok": True,
            "summary_line": summary.summary_line(),
            "total": summary.total,
            "succeeded": summary.succeeded,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "interrupted": summary.interrupted,
            "has_failures": summary.has_failures,
            "results_path": str(summary.results_path) if summary.results_path else "",
            "output_dir": out,
            "results": [_dump(result) for result in summary.results],
            "logs": logs,
            "raw_dem_path": str(getattr(plan, "raw_dem_path", "")),
            "ellipsoid_dem_path": "",
            "sarscape_ready_dem_path": "",
        }

    def _run_dem_download_and_conversion_plan(
        self, plan: Any, output_dir: str, key_source: str = "auto"
    ) -> dict:
        """Download a raw DEM, then convert/copy it to SARscape-ready outputs."""
        out = output_dir.strip() or self._default_output()
        download = self._run_dem_download_plan(plan, out, key_source)
        if not download.get("ok"):
            return download

        try:
            from insar_prep.providers.dem.conversion_planner import create_dem_conversion_plan
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 自动转换", exc)

        conversion_plan: Any | None = None
        conversion: dict | None = None
        if not bool(download.get("has_failures")):
            try:
                conversion_plan = create_dem_conversion_plan(plan)
                conversion = self._run_dem_conversion_plan(conversion_plan, out)
            except Exception as exc:  # noqa: BLE001
                conversion = _error_msg(str(exc), "DEM003")

        conversion_failed = bool(conversion and not conversion.get("ok"))
        conversion_has_failures = bool(conversion and conversion.get("has_failures"))
        logs = list(download.get("logs") or [])
        if conversion is None:
            summary_line = f"下载：{download.get('summary_line')}；转换：因下载失败或中断未执行"
            logs.append(_ui_log("DEM 转换未执行：下载失败或中断。"))
        elif conversion.get("ok"):
            summary_line = (
                f"下载：{download.get('summary_line')}；"
                f"转换：{conversion.get('summary_line')}"
            )
            logs.extend(str(item) for item in conversion.get("logs", []) if item)
        else:
            summary_line = f"下载：{download.get('summary_line')}；转换失败：{conversion.get('error')}"
            logs.append(_ui_log(f"DEM 转换失败：{conversion.get('error')}"))

        return {
            **download,
            "summary_line": summary_line,
            "has_failures": bool(download.get("has_failures"))
            or conversion_failed
            or conversion_has_failures,
            "download": download,
            "conversion": conversion,
            "logs": logs[-180:],
            "conversion_results_path": str(conversion.get("results_path", ""))
            if conversion and conversion.get("ok")
            else "",
            "raw_dem_path": str(getattr(plan, "raw_dem_path", "")),
            "ellipsoid_dem_path": str(
                getattr(conversion_plan or plan, "ellipsoid_dem_path", "")
            ),
            "sarscape_ready_dem_path": str(
                getattr(conversion_plan or plan, "sarscape_ready_dem_path", "")
            ),
        }

    def _run_dem_conversion_plan(
        self, conv_plan: Any, output_dir: str, *, output_mode: str = "sarscape"
    ) -> dict:
        """Run one DEM conversion plan and return a JSON-safe summary."""
        try:
            from insar_prep.providers.dem.convert_runner import run_dem_conversion
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 转换执行", exc)
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请指定 DEM 转换输出根目录", "GUI003")
        try:
            source = str(getattr(conv_plan, "source_vertical_datum", ""))
            target = str(getattr(conv_plan, "target_vertical_datum", ""))
            logs = [
                _ui_log(
                    f"开始 DEM 转换：{source} → {target}，输出模式 "
                    f"{'椭球高 GeoTIFF' if output_mode == 'ellipsoid' else 'SARscape _dem'}"
                )
            ]
            summary = run_dem_conversion([conv_plan], out, output_mode=output_mode)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            if _is_dem_component_environment_error(exc):
                return _dem_component_error("DEM 转换执行", exc)
            return _error_msg(str(exc), "DEM003")
        logs.extend(_dem_result_logs(list(summary.results), prefix="DEM 转换"))
        logs.append(_ui_log(f"DEM 转换完成：{summary.summary_line()}"))
        self._act(f"DEM 转换完成：{summary.summary_line()}", kind="download")
        return {
            "ok": True,
            "summary_line": summary.summary_line(),
            "total": summary.total,
            "succeeded": summary.succeeded,
            "copied": summary.copied,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "has_failures": summary.has_failures,
            "results_path": str(summary.results_path) if summary.results_path else "",
            "output_dir": out,
            "results": [_dump(result) for result in summary.results],
            "logs": logs,
            "raw_dem_path": str(getattr(conv_plan, "raw_dem_path", "")),
            "ellipsoid_dem_path": str(getattr(conv_plan, "ellipsoid_dem_path", "")),
            "sarscape_ready_dem_path": (
                "" if output_mode == "ellipsoid" else str(getattr(conv_plan, "sarscape_ready_dem_path", ""))
            ),
        }

    def _create_local_dem_conversion_plan(
        self,
        *,
        input_path: str,
        output_dir: str,
        source_vertical_datum: str,
    ) -> tuple[Any, Any, dict]:
        """Create a conversion plan from a user-selected GeoTIFF DEM."""
        raw_path = Path((input_path or "").strip())
        if not raw_path.exists() or not raw_path.is_file():
            raise ValueError(f"DEM 文件不存在：{raw_path}")
        try:
            from insar_prep.core.component_manager import activate_component  # noqa: PLC0415

            activate_component()
            import rasterio  # noqa: PLC0415
            from rasterio.warp import transform_bounds  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise ImportError(str(exc)) from exc

        from insar_prep.core.enums import VerticalDatum
        from insar_prep.core.models import BBox
        from insar_prep.core.naming import sarscape_safe_name
        from insar_prep.providers.dem.conversion_planner import (
            create_dem_conversion_plan,
            validate_dem_conversion_plan,
        )
        from insar_prep.providers.dem.types import DemRequestPlan

        with rasterio.open(raw_path) as src:
            bounds = src.bounds
            crs = src.crs
            if crs is not None and crs.to_string().upper() not in {"EPSG:4326", "OGC:CRS84"}:
                west, south, east, north = transform_bounds(crs, "EPSG:4326", *bounds)
            else:
                west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top
            tags: dict[str, str] = {}
            for ns in (None, "IMAGE_STRUCTURE"):
                try:
                    tags.update(src.tags(ns=ns))
                except Exception:  # noqa: BLE001
                    pass
            raster_info = {
                "path": str(raw_path),
                "crs": crs.to_string() if crs is not None else "",
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "tags": tags,
            }

        bbox = BBox(
            west=max(-180.0, min(float(west), float(east))),
            east=min(180.0, max(float(west), float(east))),
            south=max(-90.0, min(float(south), float(north))),
            north=min(90.0, max(float(south), float(north))),
            crs="EPSG:4326",
        )
        detected = self._detect_local_dem_vertical_datum(raw_path, raster_info)
        source = self._coerce_vertical_datum(source_vertical_datum, detected)
        target = VerticalDatum.WGS84_ELLIPSOID

        region = self._state.current_region()
        if region is not None:
            region_id = region.region_id
            safe = region.region_safe_name
        else:
            region_id = "local_dem"
            try:
                safe = sarscape_safe_name(raw_path.stem)
            except ValueError:
                safe = "local_dem"

        out = Path((output_dir or "").strip() or self._default_output() or raw_path.parent)
        dem_root = out
        output_stem = self._local_dem_output_stem(raw_path, safe)
        ellipsoid_path = _unique_local_dem_path(dem_root / f"{output_stem}_ellipsoid.tif")
        sarscape_path = _unique_local_dem_path(dem_root / f"{output_stem}_dem")
        request_plan = DemRequestPlan(
            region_id=region_id,
            region_safe_name=safe,
            provider="LOCAL",
            dataset="USER_LOCAL",
            request_bbox=bbox,
            processing_bbox=bbox,
            buffer_degrees=0.0,
            source_vertical_datum=source,
            target_vertical_datum=target,
            raw_dem_path=raw_path,
            ellipsoid_dem_path=ellipsoid_path,
            sarscape_ready_dem_path=sarscape_path,
            notes="user-provided local DEM",
        )
        conv_plan = create_dem_conversion_plan(request_plan)
        report = validate_dem_conversion_plan(conv_plan)
        detected.update(
            {
                "selected_source_vertical_datum": source.value,
                "target_vertical_datum": target.value,
                "output_root": str(out),
            }
        )
        return conv_plan, report, detected

    @staticmethod
    def _local_dem_output_stem(raw_path: Path, fallback: str) -> str:
        from insar_prep.core.naming import sarscape_safe_name

        stem = re.sub(r"[^A-Za-z0-9_]+", "_", raw_path.stem).strip("_")
        if not stem:
            try:
                stem = sarscape_safe_name(raw_path.stem)
            except ValueError:
                stem = fallback or "local_dem"
        if not stem:
            stem = fallback or "local_dem"
        lower = stem.lower()
        for suffix in ("_ellipsoid", "_dem"):
            if lower.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem or fallback or "local_dem"

    @staticmethod
    def _detect_local_dem_vertical_datum(path: Path, raster_info: dict) -> dict:
        """Best-effort vertical datum detection from tags and filename."""
        from insar_prep.core.enums import VerticalDatum

        tag_text = " ".join(str(v) for v in raster_info.get("tags", {}).values())
        text = f"{path.name} {tag_text}".upper()
        if (
            "WGS84_ELLIPSOID" in text
            or "ELLIPSOID" in text
            or "ELLIPSOIDAL" in text
            or "SRTMGL1_E" in text
            or "AW3D30_E" in text
            or "AW3D30M" in text
        ):
            datum = VerticalDatum.WGS84_ELLIPSOID
            confidence = "medium"
        elif "EGM2008" in text or "EGM08" in text or "COP30" in text or "COP90" in text:
            datum = VerticalDatum.EGM2008
            confidence = "medium"
        elif "EGM96" in text or "SRTM" in text or "NASADEM" in text:
            datum = VerticalDatum.EGM96
            confidence = "medium"
        elif "ORTHOMETRIC" in text or "GEOID" in text:
            datum = VerticalDatum.ORTHOMETRIC
            confidence = "low"
        else:
            datum = VerticalDatum.UNKNOWN
            confidence = "unknown"
        return {
            **{k: v for k, v in raster_info.items() if k != "tags"},
            "detected_source_vertical_datum": datum.value,
            "detection_confidence": confidence,
        }

    @staticmethod
    def _coerce_vertical_datum(value: str, detected: dict) -> Any:
        from insar_prep.core.enums import VerticalDatum

        raw = (value or "auto").strip().upper()
        aliases = {
            "AUTO": detected.get("detected_source_vertical_datum", VerticalDatum.UNKNOWN.value),
            "WGS84": VerticalDatum.WGS84_ELLIPSOID.value,
            "ELLIPSOID": VerticalDatum.WGS84_ELLIPSOID.value,
            "ELLIPSOIDAL": VerticalDatum.WGS84_ELLIPSOID.value,
            "WGS84_ELLIPSOID": VerticalDatum.WGS84_ELLIPSOID.value,
            "EGM96": VerticalDatum.EGM96.value,
            "EGM2008": VerticalDatum.EGM2008.value,
            "ORTHOMETRIC": VerticalDatum.ORTHOMETRIC.value,
            "UNKNOWN": VerticalDatum.UNKNOWN.value,
        }
        return VerticalDatum(aliases.get(raw, raw))

    def _default_output(self) -> str:
        region = self._state.current_region()
        if region is not None:
            return str(region.region_root)
        project = self._state.current_project()
        if project is not None:
            return str(project.project_root)
        ws = self._state.workspace
        return str(ws.workspace_root) if ws is not None else ""

    def _gather_reports(self, region: Any, out: str) -> dict:
        """Auto-collect every sub-report the current state allows (best-effort).

        Beginner-friendly: the report consolidates scene-check, DEM planning, DEM
        conversion and GACOS planning automatically; the user does not wire each
        one. Any stage that is not yet possible (no AOI / no scenes / missing dep)
        is simply omitted rather than failing the whole report.
        """
        gathered: dict = {
            "scene_check": None,
            "dem_planning": None,
            "dem_conversion": None,
            "gacos_planning": None,
        }
        if region.scenes:
            try:
                from insar_prep.quality.scene_checks import check_scene_collection

                gathered["scene_check"] = check_scene_collection(region.scenes)
            except Exception:  # noqa: BLE001
                pass
        if region.aoi is not None and region.aoi.bbox is not None:
            try:
                from insar_prep.providers.dem.conversion_planner import (
                    create_dem_conversion_plan,
                    validate_dem_conversion_plan,
                )
                from insar_prep.providers.dem.planner import (
                    create_dem_request_plan,
                    validate_dem_request_plan,
                )

                plan = create_dem_request_plan(
                    region_id=region.region_id,
                    region_safe_name=region.region_safe_name,
                    processing_aoi=region.aoi,
                    output_root=out,
                    dataset=self._dem_dataset,
                    **self._dem_source_kwargs(),
                )
                gathered["dem_planning"] = validate_dem_request_plan(plan)
                gathered["dem_conversion"] = validate_dem_conversion_plan(
                    create_dem_conversion_plan(plan)
                )
            except Exception:  # noqa: BLE001
                pass
            if region.scenes:
                try:
                    from insar_prep.providers.gacos.planner import (
                        create_gacos_request_plan,
                        validate_gacos_request_plan,
                    )

                    gplan = create_gacos_request_plan(
                        region_id=region.region_id,
                        region_safe_name=region.region_safe_name,
                        processing_aoi=region.aoi,
                        scenes=region.scenes,
                        output_root=out,
                    )
                    gathered["gacos_planning"] = validate_gacos_request_plan(gplan)
                except Exception:  # noqa: BLE001
                    pass
        return gathered

    def _dem_source_kwargs(self) -> dict:
        """Auto-derive the dataset's native vertical datum for the planner.

        This is what makes already-ellipsoidal datasets (SRTMGL1_E / AW3D30_E)
        skip conversion instead of being wrongly converted from EGM2008.
        """
        try:
            from insar_prep.core.enums import VerticalDatum
            from insar_prep.providers.dem.converter import (
                dataset_source_vertical_datum,
            )
        except Exception:  # noqa: BLE001
            return {}
        src = dataset_source_vertical_datum(self._dem_dataset)
        if src == VerticalDatum.UNKNOWN:
            return {}
        return {"source_vertical_datum": src}


def _format_validation(exc: Exception) -> str:
    """Turn a pydantic ValidationError (or any error) into a short message."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            msgs = [str(e.get("msg", "")).strip() for e in errors()]
            msgs = [m for m in msgs if m]
            if msgs:
                return "；".join(dict.fromkeys(msgs))
        except Exception:  # noqa: BLE001
            pass
    return str(exc) or "无效的坐标范围"


def _conversion_summary(conv_plan: Any) -> dict:
    """Beginner-friendly, auto-derived description of the conversion decision."""
    source = str(getattr(conv_plan, "source_vertical_datum", ""))
    target = str(getattr(conv_plan, "target_vertical_datum", ""))
    requires = bool(getattr(conv_plan, "requires_conversion", False))
    requires_geoid = bool(getattr(conv_plan, "requires_geoid", False))
    geoid = None
    for step in getattr(conv_plan, "steps", []) or []:
        if getattr(step, "geoid_model", None):
            geoid = str(step.geoid_model)
            break
    if not requires:
        message = (
            f"该 DEM 高程基准已为 {source}（椭球高），无需垂直基准转换，将导出 SARscape ENVI _dem + .hdr + .sml。"
        )
    elif requires_geoid and geoid:
        message = (
            f"检测到高程基准为 {source}（正高），将自动转换为 {target}，"
            f"采用大地水准面模型 {geoid}（系统自动选择）。"
        )
    else:
        message = f"将自动把高程基准从 {source} 转换为 {target}。"
    return {
        "requires_conversion": requires,
        "requires_geoid": requires_geoid,
        "source": source,
        "target": target,
        "geoid_model": geoid,
        "message": message,
    }


def _enrich_scenes_best_effort(
    scenes: list[Any],
    *,
    activity: ActivityLog | None = None,
    progress: Any | None = None,
) -> list[Any]:
    """Try public ASF metadata enrichment without blocking local import."""
    try:
        from insar_prep.providers.asf.metadata import enrich_scenes_from_asf_search

        enriched = enrich_scenes_from_asf_search(scenes, progress=progress)
    except Exception as exc:  # noqa: BLE001 - metadata is helpful, not required
        if activity is not None:
            activity.add(f"ASF 元数据补全未完成：{exc}", kind="warning")
        return scenes
    count = sum(
        1
        for scene in enriched
        if getattr(scene, "path", None)
        or getattr(scene, "frame", None)
        or getattr(scene, "footprint_bbox", None)
    )
    if activity is not None and count:
        activity.add(f"ASF 元数据已补全：{count} 景", kind="scenes")
    return enriched


def _scene_coverage_bbox(scenes: list[Any]) -> Any | None:
    """Union all available scene footprint bboxes into one BBox model."""
    boxes = [getattr(scene, "footprint_bbox", None) for scene in scenes]
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        return None
    try:
        from insar_prep.core.models import BBox

        return BBox(
            west=min(float(box.west) for box in boxes),
            east=max(float(box.east) for box in boxes),
            south=min(float(box.south) for box in boxes),
            north=max(float(box.north) for box in boxes),
            crs="EPSG:4326",
        )
    except Exception:  # noqa: BLE001
        return None


def _aoi_geojson(region: Any) -> dict | None:
    """Return a persisted AOI GeoJSON geometry when the current AOI has one."""
    aoi = getattr(region, "aoi", None)
    path = getattr(aoi, "geometry_path", None)
    if path is None:
        return None
    try:
        geojson_path = Path(path)
        if not geojson_path.is_file() or geojson_path.suffix.lower() not in {".json", ".geojson"}:
            return None
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a stale path should not break context
        return None
    return _extract_geojson_geometry(data)


def _extract_geojson_geometry(data: Any) -> dict | None:
    if not isinstance(data, dict):
        return None
    obj_type = data.get("type")
    if obj_type == "Feature":
        geometry = data.get("geometry")
        return geometry if isinstance(geometry, dict) else None
    if obj_type in {"Polygon", "MultiPolygon", "FeatureCollection"}:
        return data
    return None


def _write_region_aoi_geojson(region: Any, geojson: dict) -> Path | None:
    """Persist drawn/admin AOI geometry beside the selected region."""
    try:
        root = Path(region.region_root) / "AOI"
        root.mkdir(parents=True, exist_ok=True)
        target = root / "current_aoi.geojson"
        feature = _geojson_feature_for_storage(geojson)
        target.write_text(json.dumps(feature, ensure_ascii=False, indent=2), encoding="utf-8")
        return target
    except Exception:  # noqa: BLE001 - AOI bbox remains usable even if preview save fails
        return None


def _geojson_feature_for_storage(geojson: dict) -> dict:
    obj_type = geojson.get("type")
    if obj_type in {"Feature", "FeatureCollection"}:
        return geojson
    return {
        "type": "Feature",
        "properties": {},
        "geometry": geojson,
    }


_LOCAL_BOUNDARY_CACHE: dict[str, list[dict]] = {}


def _geojson_from_aoi_file(path: str | Path) -> dict | None:
    """Return displayable GeoJSON for supported local AOI files."""
    source = Path(path)
    suffix = source.suffix.lower()
    try:
        if suffix in {".geojson", ".json"}:
            data = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            from shapely.geometry import mapping

            from insar_prep.processing.aoi_import import _geometry_from_geojson

            geometry = _geometry_from_geojson(data)
            return dict(mapping(geometry))
        geometry = None
        if suffix == ".shp":
            from insar_prep.processing.aoi_vector import (
                _check_shapefile_prj,
                _geometry_from_shapefile_bytes,
            )

            _check_shapefile_prj(source)
            geometry = _geometry_from_shapefile_bytes(source.read_bytes(), source)
        elif suffix == ".kml":
            from insar_prep.processing.aoi_vector import _geometry_from_kml_bytes

            geometry = _geometry_from_kml_bytes(source.read_bytes(), str(source))
        elif suffix == ".kmz":
            import zipfile

            from insar_prep.processing.aoi_vector import _first_kml_name, _geometry_from_kml_bytes

            with zipfile.ZipFile(source) as archive:
                kml_name = _first_kml_name(archive.namelist())
                if kml_name is None:
                    return None
                geometry = _geometry_from_kml_bytes(archive.read(kml_name), f"{source}!{kml_name}")
        if geometry is None:
            return None
        from shapely.geometry import mapping

        return dict(mapping(geometry))
    except Exception:  # noqa: BLE001 - display preview is helpful but not required to bind AOI
        return None


def _geojson_feature_count_from_file(path: str | Path) -> int | None:
    source = Path(path)
    if source.suffix.lower() not in {".geojson", ".json"}:
        return None
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    if data.get("type") == "FeatureCollection":
        features = data.get("features")
        return len(features) if isinstance(features, list) else None
    if data.get("type") == "Feature":
        return 1
    return 1 if data.get("type") else None


def _read_aoi_vector_features(path: str | Path) -> list[dict[str, Any]]:
    """Read per-feature AOI geometry/properties from supported local vector files."""
    source = Path(path)
    suffix = source.suffix.lower()
    if not source.is_file():
        raise FileNotFoundError(f"边界文件不存在：{source}")
    if suffix in {".geojson", ".json"}:
        return _read_geojson_aoi_features(source)
    if suffix == ".shp":
        return _read_shapefile_aoi_features(source)
    if suffix == ".kml":
        return _read_kml_aoi_features(source.read_bytes(), str(source))
    if suffix == ".kmz":
        import zipfile

        from insar_prep.processing.aoi_vector import _first_kml_name

        with zipfile.ZipFile(source) as archive:
            kml_name = _first_kml_name(archive.namelist())
            if kml_name is None:
                raise ValueError(f"KMZ 文件内没有 .kml：{source}")
            return _read_kml_aoi_features(archive.read(kml_name), f"{source}!{kml_name}")
    raise ValueError("暂不支持该边界格式；请使用 .shp、.kml、.kmz、.geojson 或 .json。")


def _read_aoi_vector_features_from_text(file_name: str, text: str) -> list[dict[str, Any]]:
    """Read AOI features from browser-dragged text content."""
    source = Path(str(file_name or "boundary"))
    suffix = source.suffix.lower()
    raw = str(text or "")
    if suffix not in {".geojson", ".json", ".kml"}:
        if suffix in {".shp", ".kmz"}:
            raise ValueError("该格式需要按二进制读取；请重新拖入文件，或点击“上传本地边界”选择文件。")
        raise ValueError("仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。")
    if not raw.strip():
        raise ValueError("边界文件内容为空。")
    if suffix in {".geojson", ".json"}:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"GeoJSON/JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列附近格式不正确。") from exc
        return _read_geojson_aoi_features_from_data(data)
    return _read_kml_aoi_features(raw.encode("utf-8"), source.name)


def _read_aoi_vector_features_from_bytes(file_name: str, raw: bytes) -> list[dict[str, Any]]:
    """Read AOI features from browser-dragged binary content."""
    source = Path(str(file_name or "boundary"))
    suffix = source.suffix.lower()
    if not raw:
        raise ValueError("边界文件内容为空。")
    if suffix == ".shp":
        raise ValueError(
            "拖拽单个 .shp 文件缺少配套 .dbf/.shx/.prj，无法可靠识别属性和坐标系；"
            "请点击“上传本地边界”选择 .shp 文件。"
        )
    if suffix == ".kmz":
        import zipfile

        from insar_prep.processing.aoi_vector import _first_kml_name

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                kml_name = _first_kml_name(archive.namelist())
                if kml_name is None:
                    raise ValueError("KMZ 文件内没有 .kml 文件。")
                return _read_kml_aoi_features(archive.read(kml_name), f"{source.name}!{kml_name}")
        except zipfile.BadZipFile as exc:
            raise ValueError("KMZ 文件不是有效压缩包。") from exc
    if suffix in {".geojson", ".json", ".kml"}:
        return _read_aoi_vector_features_from_text(source.name, raw.decode("utf-8", errors="replace"))
    raise ValueError("仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。")


def _read_geojson_aoi_features(source: Path) -> list[dict[str, Any]]:
    data = json.loads(source.read_text(encoding="utf-8"))
    return _read_geojson_aoi_features_from_data(data)


def _read_geojson_aoi_features_from_data(data: Any) -> list[dict[str, Any]]:
    from shapely.geometry import mapping, shape

    from insar_prep.processing.aoi_import import _coerce_to_areal_geometry, _reject_non_wgs84_crs

    if not isinstance(data, dict):
        raise ValueError("GeoJSON 顶层必须是对象。")
    _reject_non_wgs84_crs(data)
    obj_type = data.get("type")
    if obj_type == "FeatureCollection":
        raw_features = [feature for feature in data.get("features", []) if isinstance(feature, dict)]
    elif obj_type == "Feature":
        raw_features = [data]
    elif obj_type in {"Polygon", "MultiPolygon", "LineString", "MultiLineString", "GeometryCollection"}:
        raw_features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        raise ValueError(f"不支持的 GeoJSON 类型：{obj_type}")
    out: list[dict[str, Any]] = []
    for index, feature in enumerate(raw_features):
        geometry_data = feature.get("geometry")
        if not isinstance(geometry_data, dict):
            continue
        try:
            geometry = _coerce_to_areal_geometry(shape(geometry_data))
        except Exception:
            continue
        if geometry.is_empty:
            continue
        props = feature.get("properties")
        out.append(
            {
                "properties": _clean_aoi_properties(props if isinstance(props, dict) else {}),
                "geometry": dict(mapping(geometry)),
                "_source_index": index,
            }
        )
    if not out:
        raise ValueError("边界文件内没有可用面要素。")
    return out


def _feature_collection_from_aoi_features(features: list[dict[str, Any]], source: str = "") -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "properties": {"source_file": source},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **dict(feature.get("properties") or {}),
                    "_insar_feature_index": index,
                    "_insar_feature_name": _aoi_feature_name(feature),
                },
                "geometry": feature["geometry"],
            }
            for index, feature in enumerate(features)
            if isinstance(feature.get("geometry"), dict)
        ],
    }


def _selected_geojson_from_feature_collection(
    geojson: dict,
    feature_ids: list[Any] | None = None,
    name_field: str = "",
    download_mode: str = "merge",
) -> dict[str, Any]:
    if not isinstance(geojson, dict):
        raise ValueError("边界数据必须是 GeoJSON 对象。")
    features = _read_geojson_aoi_features_from_data(geojson)
    selected_indices = _normalise_feature_indices(feature_ids, len(features))
    if not selected_indices:
        raise ValueError("请至少选择一个边界要素。")
    field = str(name_field or "").strip()
    selected = [features[index] for index in selected_indices]
    collection_props = geojson.get("properties") if isinstance(geojson.get("properties"), dict) else {}
    selected_geojson = {
        "type": "FeatureCollection",
        "properties": {
            "source_file": str(collection_props.get("source_file") or "dragged-boundary"),
            "selected_feature_count": len(selected),
            "total_feature_count": len(features),
            "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **dict(feature.get("properties") or {}),
                    "_insar_feature_index": selected_indices[i],
                    "_insar_feature_name": _aoi_feature_name(feature, field),
                },
                "geometry": feature["geometry"],
            }
            for i, feature in enumerate(selected)
        ],
    }
    return selected_geojson


def _friendly_aoi_error(exc: Exception, source: str | Path = "") -> str:
    source_name = Path(str(source or "边界文件")).name
    text = str(exc or "").strip()
    if isinstance(exc, FileNotFoundError) or "不存在" in text or "not found" in text.lower():
        return "没有读取到文件的真实本机路径。请重新拖入文件；如果仍失败，请点击“上传本地边界”选择文件。"
    if "unsupported" in text.lower() or "暂不支持" in text or "仅支持" in text:
        return "仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。"
    if "GeoJSON" in text or "JSON" in text:
        return text
    if "KML" in text or "KMZ" in text:
        return text
    if "缺少配套" in text or ".dbf" in text or ".shx" in text:
        return text
    if "Shapefile" in text or "shapefile" in text:
        return "Shapefile 读取失败；请确认它是面边界，且坐标为 WGS84 经纬度。"
    if "边界文件内容为空" in text or "没有可用面要素" in text or "请至少选择" in text:
        return text
    return f"{source_name} 不是可识别的边界文件，请检查文件格式和坐标系。"


def _read_kml_aoi_features(raw: bytes, source: str) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    from shapely.geometry import mapping
    from shapely.ops import unary_union

    from insar_prep.processing.aoi_vector import _iter_local, _kml_outer_ring, _local_name, _polygon_from_ring

    try:
        root = ET.fromstring(raw)  # noqa: S314 - local vector file only.
    except ET.ParseError as exc:
        raise ValueError(f"KML 解析失败：{source}: {exc}") from exc
    out: list[dict[str, Any]] = []
    placemarks = [elem for elem in root.iter() if _local_name(elem.tag) == "Placemark"]
    for index, placemark in enumerate(placemarks):
        name_elem = next((child for child in placemark if _local_name(child.tag) == "name"), None)
        name = (name_elem.text or "").strip() if name_elem is not None else ""
        polygons = []
        for polygon_elem in _iter_local(placemark, "Polygon"):
            ring = _kml_outer_ring(polygon_elem)
            polygon = _polygon_from_ring(ring) if ring else None
            if polygon is not None and not polygon.is_empty:
                polygons.append(polygon)
        if not polygons:
            continue
        out.append(
            {
                "properties": _clean_aoi_properties({"name": name or f"Placemark {index + 1}"}),
                "geometry": dict(mapping(unary_union(polygons))),
                "_source_index": index,
            }
        )
    if out:
        return out
    polygons = []
    for polygon_elem in _iter_local(root, "Polygon"):
        ring = _kml_outer_ring(polygon_elem)
        polygon = _polygon_from_ring(ring) if ring else None
        if polygon is not None and not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        raise ValueError(f"KML 内没有可用面要素：{source}")
    return [
        {
            "properties": _clean_aoi_properties({"name": Path(source).stem or "KML 边界"}),
            "geometry": dict(mapping(unary_union(polygons))),
            "_source_index": 0,
        }
    ]


def _read_shapefile_aoi_features(source: Path) -> list[dict[str, Any]]:
    from insar_prep.processing.aoi_vector import (
        _check_shapefile_prj,
    )

    _check_shapefile_prj(source)
    return _read_shapefile_aoi_features_from_bytes(
        source.read_bytes(),
        str(source),
        dbf_rows=_read_dbf_records(source.with_suffix(".dbf")),
    )


def _read_shapefile_aoi_features_from_bytes(
    data: bytes,
    source: str,
    *,
    dbf_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    import struct

    from shapely.geometry import mapping
    from shapely.ops import unary_union

    from insar_prep.processing.aoi_vector import (
        _SHP_HEADER_SIZE,
        _SHP_NULL_TYPE,
        _SHP_POLYGON_TYPES,
        _polygons_from_shapefile_record,
    )

    if len(data) < _SHP_HEADER_SIZE or struct.unpack(">i", data[0:4])[0] != 9994:
        raise ValueError(f"不是有效 Shapefile：{source}")
    file_type = struct.unpack("<i", data[32:36])[0]
    if file_type != _SHP_NULL_TYPE and file_type not in _SHP_POLYGON_TYPES:
        raise ValueError("Shapefile 不是面要素，不能作为 AOI。")
    rows = dbf_rows or []
    out: list[dict[str, Any]] = []
    offset = _SHP_HEADER_SIZE
    size = len(data)
    while offset + 8 <= size:
        record_number, content_len_words = struct.unpack(">ii", data[offset : offset + 8])
        content_start = offset + 8
        content_end = content_start + content_len_words * 2
        if content_end > size:
            break
        content = data[content_start:content_end]
        offset = content_end
        if len(content) < 4:
            continue
        shape_type = struct.unpack("<i", content[0:4])[0]
        if shape_type == _SHP_NULL_TYPE:
            continue
        if shape_type not in _SHP_POLYGON_TYPES:
            raise ValueError(f"Shapefile 记录 {record_number} 不是面要素。")
        polygons = _polygons_from_shapefile_record(content)
        if not polygons:
            continue
        row_index = max(0, int(record_number) - 1)
        out.append(
            {
                "properties": _clean_aoi_properties(rows[row_index] if row_index < len(rows) else {}),
                "geometry": dict(mapping(unary_union(polygons))),
                "_source_index": row_index,
            }
        )
    if not out:
        raise ValueError("Shapefile 内没有可用面要素。")
    return out


def _read_dbf_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = path.read_bytes()
    if len(data) < 33:
        return []
    try:
        record_count = int.from_bytes(data[4:8], "little")
        header_len = int.from_bytes(data[8:10], "little")
        record_len = int.from_bytes(data[10:12], "little")
    except Exception:
        return []
    fields: list[tuple[str, str, int, int]] = []
    offset = 32
    while offset + 32 <= len(data) and data[offset] != 0x0D:
        raw_name = data[offset : offset + 11].split(b"\x00", 1)[0]
        name = _decode_dbf_text(raw_name).strip() or f"field_{len(fields) + 1}"
        field_type = chr(data[offset + 11]) if data[offset + 11] else "C"
        field_len = int(data[offset + 16])
        decimals = int(data[offset + 17])
        fields.append((name, field_type, field_len, decimals))
        offset += 32
    rows: list[dict[str, Any]] = []
    start = header_len
    for row_index in range(record_count):
        row_start = start + row_index * record_len
        row = data[row_start : row_start + record_len]
        if len(row) < record_len or row[:1] == b"*":
            continue
        cursor = 1
        props: dict[str, Any] = {}
        for name, field_type, field_len, decimals in fields:
            raw = row[cursor : cursor + field_len]
            cursor += field_len
            text = _decode_dbf_text(raw).strip()
            if not text:
                props[name] = ""
            elif field_type in {"N", "F"}:
                try:
                    props[name] = int(text) if decimals == 0 and "." not in text else float(text)
                except ValueError:
                    props[name] = text
            elif field_type == "L":
                props[name] = text.upper() in {"Y", "T", "1"}
            else:
                props[name] = text
        rows.append(props)
    return rows


def _decode_dbf_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "cp936", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace")


def _clean_aoi_properties(props: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            cleaned[key.strip()] = value
        else:
            try:
                cleaned[key.strip()] = json.dumps(value, ensure_ascii=False)
            except TypeError:
                cleaned[key.strip()] = str(value)
    return cleaned


def _aoi_feature_fields(features: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for feature in features:
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        for key in props:
            if key not in fields:
                fields.append(str(key))
            if len(fields) >= 80:
                return fields
    return fields


def _suggest_aoi_name_field(fields: list[str]) -> str:
    preferred = ["name", "NAME", "Name", "名称", "NAME_CHN", "fullname", "FULLNAME", "县", "市", "省"]
    for field in preferred:
        if field in fields:
            return field
    for field in fields:
        if "name" in field.lower() or "名" in field:
            return field
    return fields[0] if fields else ""


def _aoi_feature_name(feature: dict[str, Any], field: str = "") -> str:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    if field and field in props and str(props.get(field) or "").strip():
        return str(props.get(field)).strip()
    fallback_field = _suggest_aoi_name_field(list(props.keys()))
    if fallback_field and str(props.get(fallback_field) or "").strip():
        return str(props.get(fallback_field)).strip()
    index = int(feature.get("_source_index") or 0) + 1
    return f"要素 {index}"


def _aoi_feature_preview_row(index: int, feature: dict[str, Any], field: str) -> dict[str, Any]:
    from shapely.geometry import shape

    geometry = shape(feature["geometry"])
    minx, miny, maxx, maxy = geometry.bounds
    return {
        "id": str(index),
        "index": index + 1,
        "source_index": int(feature.get("_source_index") or index) + 1,
        "name": _aoi_feature_name(feature, field),
        "area_km2": round(_rough_geometry_area_km2(geometry), 2),
        "bbox": {"west": minx, "east": maxx, "south": miny, "north": maxy, "crs": "EPSG:4326"},
        "properties": dict(feature.get("properties") or {}),
    }


def _rough_geometry_area_km2(geometry: Any) -> float:
    import math

    try:
        _, miny, _, maxy = geometry.bounds
        lat = (float(miny) + float(maxy)) / 2
        return abs(float(geometry.area)) * 111.32 * 111.32 * max(0.12, abs(math.cos(math.radians(lat))))
    except Exception:  # noqa: BLE001
        return 0.0


def _normalise_feature_indices(feature_ids: list[Any] | None, total: int) -> list[int]:
    if not feature_ids:
        return list(range(total))
    out: list[int] = []
    for value in feature_ids:
        try:
            index = int(str(value).strip())
        except ValueError:
            continue
        if 0 <= index < total and index not in out:
            out.append(index)
    return out


def _local_boundary_dir() -> Path | None:
    candidates: list[Path] = []
    env_path = os.environ.get("INSAR_BOUNDARY_DIR")
    if env_path:
        candidates.append(Path(env_path))
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "insar_prep" / "desktop" / "boundaries")
        candidates.append(Path(frozen_root) / "边界")
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "InSAR Assistant" / "boundaries")
        candidates.append(Path(local_appdata) / "InSAR Assistant" / "边界")
    candidates.extend(
        [
            Path(__file__).resolve().parent / "boundaries",
            Path.cwd() / "boundaries",
            Path.cwd() / "边界",
            Path(sys.executable).resolve().parent / "boundaries",
            Path(sys.executable).resolve().parent / "边界",
            Path(sys.executable).resolve().parent.parent / "boundaries",
            Path(sys.executable).resolve().parent.parent / "边界",
            Path(__file__).resolve().parents[3] / "边界",
            Path("C:/InSAR") / "边界",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _load_local_boundary_layer(level: str) -> list[dict]:
    cached = _LOCAL_BOUNDARY_CACHE.get(level)
    if cached is not None:
        return cached
    root = _local_boundary_dir()
    if root is None:
        return []
    filenames = {
        "province": ("china_province.geojson", "中国_省.geojson"),
        "city": ("china_city.geojson", "中国_市.geojson"),
        "county": ("china_county.geojson", "中国_县.geojson"),
    }[level]
    path = next((root / filename for filename in filenames if (root / filename).is_file()), None)
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features") if isinstance(data, dict) else None
    clean = [feature for feature in (features or []) if isinstance(feature, dict) and _local_feature_name(feature)]
    _LOCAL_BOUNDARY_CACHE[level] = clean
    return clean


def _local_feature_name(feature: dict) -> str:
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        return ""
    name = str(props.get("name") or "").strip()
    return "" if name == "境界线" else name


def _local_feature_gb(feature: dict) -> str:
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        return ""
    return str(props.get("gb") or "").strip()


def _admin_value(value: str) -> str:
    text = str(value or "").strip()
    return "" if text in {"全部", "不限", "全国", "中国"} else text


def _is_national_admin_request(*, province: str, city: str, district: str, query: str) -> bool:
    province_text = str(province or "").strip()
    query_text = str(query or "").strip()
    city_text = _admin_value(city)
    district_text = _admin_value(district)
    return not city_text and not district_text and (
        province_text in {"全部", "全国", "中国"} or query_text in {"全部", "全国", "中国"}
    )


def _builtin_china_boundary() -> dict:
    provinces = _load_local_boundary_layer("province")
    province_features = []
    for feature in provinces:
        geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
        if geometry is None:
            continue
        province_features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": _local_feature_name(feature),
                    "gb": _local_feature_gb(feature),
                },
                "geometry": geometry,
            }
        )
    geojson = (
        {
            "type": "FeatureCollection",
            "features": province_features,
        }
        if province_features
        else None
    )
    return {
        "label": "全国",
        "bbox": {
            "west": 73.5,
            "east": 135.1,
            "south": 18.0,
            "north": 53.6,
            "crs": "EPSG:4326",
        },
        "geojson": geojson,
        "source": "内置全国边界" if geojson else "内置全国范围",
        "class": "boundary",
        "type": "administrative",
        "osm_type": None,
        "osm_id": "CN",
        "city_code": "CN",
        "admin_type": "country",
    }


def _name_matches(name: str, query: str) -> bool:
    if not query:
        return True
    return name == query or query in name or name in query


def _feature_to_boundary(feature: dict, label_parts: list[str]) -> dict | None:
    bbox = _boundary_bbox(feature)
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
    if bbox is None or geometry is None:
        return None
    name = _local_feature_name(feature)
    gb = _local_feature_gb(feature)
    label = " / ".join(dict.fromkeys([part for part in [*label_parts, name] if part]))
    return {
        "label": label or name,
        "bbox": bbox,
        "geojson": geometry,
        "source": "本地天地图行政边界",
        "class": "boundary",
        "type": "administrative",
        "osm_type": None,
        "osm_id": gb or None,
        "city_code": gb or None,
        "admin_type": None,
    }


def _find_feature(features: list[dict], name: str, prefix: str = "") -> dict | None:
    if not name:
        return None
    matches = [
        feature
        for feature in features
        if _name_matches(_local_feature_name(feature), name)
        and (not prefix or _local_feature_gb(feature).startswith(prefix))
    ]
    exact = [feature for feature in matches if _local_feature_name(feature) == name]
    return (exact or matches or [None])[0]


def _append_unique_boundary(results: list[dict], feature: dict, label_parts: list[str], limit: int) -> None:
    if len(results) >= limit:
        return
    item = _feature_to_boundary(feature, label_parts)
    if item is None:
        return
    key = (item.get("osm_id"), item.get("label"))
    existing = {(current.get("osm_id"), current.get("label")) for current in results}
    if key not in existing:
        results.append(item)


def _search_local_admin_boundaries(
    *,
    province: str,
    city: str,
    district: str,
    query: str,
    limit: int = 8,
) -> tuple[list[dict], str | None]:
    if _is_national_admin_request(province=province, city=city, district=district, query=query):
        return [_builtin_china_boundary()], None
    if _local_boundary_dir() is None:
        return [], "未找到本地边界目录。"
    try:
        provinces = _load_local_boundary_layer("province")
        cities = _load_local_boundary_layer("city")
        counties = _load_local_boundary_layer("county")
    except Exception as exc:  # noqa: BLE001
        return [], f"本地边界读取失败：{exc}"
    if not provinces or not cities or not counties:
        return [], "本地边界文件不完整。"

    max_items = max(1, min(int(limit or 8), 50))
    province_name = _admin_value(province)
    city_name = _admin_value(city)
    county_name = _admin_value(district)
    query_name = _admin_value(query)
    province_feature = _find_feature(provinces, province_name) if province_name else None
    province_prefix = _local_feature_gb(province_feature)[:5] if province_feature else ""
    city_feature = _find_feature(cities, city_name, province_prefix) if city_name else None
    city_prefix = _local_feature_gb(city_feature)[:7] if city_feature else ""
    results: list[dict] = []

    if county_name:
        for feature in counties:
            gb = _local_feature_gb(feature)
            if province_prefix and not gb.startswith(province_prefix):
                continue
            if city_prefix and not gb.startswith(city_prefix):
                continue
            if _name_matches(_local_feature_name(feature), county_name):
                _append_unique_boundary(results, feature, [province_name, city_name], max_items)
        return results, None

    if city_name:
        if city_feature is not None:
            _append_unique_boundary(results, city_feature, [province_name], max_items)
        for feature in counties:
            gb = _local_feature_gb(feature)
            if city_prefix and not gb.startswith(city_prefix):
                continue
            if not city_prefix and province_prefix and not gb.startswith(province_prefix):
                continue
            _append_unique_boundary(results, feature, [province_name, city_name], max_items)
        return results, None

    if province_name:
        if province_feature is not None:
            _append_unique_boundary(results, province_feature, [], max_items)
        for feature in cities:
            gb = _local_feature_gb(feature)
            if province_prefix and not gb.startswith(province_prefix):
                continue
            _append_unique_boundary(results, feature, [province_name], max_items)
        return results, None

    if query_name:
        for layer, label_parts in ((provinces, []), (cities, []), (counties, [])):
            for feature in layer:
                if _name_matches(_local_feature_name(feature), query_name):
                    _append_unique_boundary(results, feature, label_parts, max_items)
                    if len(results) >= max_items:
                        return results, None
    return results, None


def _local_admin_options(*, province: str = "", city: str = "") -> dict[str, list[str]]:
    provinces = _load_local_boundary_layer("province")
    cities = _load_local_boundary_layer("city")
    counties = _load_local_boundary_layer("county")
    province_names = sorted({_local_feature_name(feature) for feature in provinces if _local_feature_name(feature)})
    province_name = _admin_value(province)
    city_name = _admin_value(city)
    province_feature = _find_feature(provinces, province_name) if province_name else None
    province_prefix = _local_feature_gb(province_feature)[:5] if province_feature else ""
    city_features = [
        feature
        for feature in cities
        if _local_feature_name(feature) and (not province_prefix or _local_feature_gb(feature).startswith(province_prefix))
    ]
    city_names = sorted({_local_feature_name(feature) for feature in city_features})
    city_feature = _find_feature(cities, city_name, province_prefix) if city_name else None
    city_prefix = _local_feature_gb(city_feature)[:7] if city_feature else ""
    county_features = [
        feature
        for feature in counties
        if _local_feature_name(feature)
        and (
            (city_prefix and _local_feature_gb(feature).startswith(city_prefix))
            or (not city_prefix and province_prefix and _local_feature_gb(feature).startswith(province_prefix))
        )
    ]
    county_names = sorted({_local_feature_name(feature) for feature in county_features})
    return {
        "provinces": ["全部", *province_names],
        "cities": ["全部", *city_names],
        "districts": ["全部", *county_names],
    }


def _search_tianditu_admin_boundaries(
    *,
    token: str,
    candidates: list[str],
    limit: int = 8,
) -> tuple[list[dict], str | None]:
    """Query Tianditu administrative boundaries and normalize the response."""
    clean_candidates = [
        item.strip()
        for item in dict.fromkeys(candidates)
        if item and item.strip() and item.strip() not in {"全部", "不限", "中国"}
    ]
    if not clean_candidates:
        return [], "缺少查询关键字"
    try:
        import requests  # noqa: PLC0415 - optional download extra
    except ImportError as exc:
        return [], f"缺少 requests：{exc}"

    results: list[dict] = []
    last_error: str | None = None
    max_items = max(1, min(int(limit or 8), 20))
    for keyword in clean_candidates:
        payload = {
            "searchWord": keyword,
            "searchType": "1",
            "needSubInfo": "true",
            "needAll": "true",
            "needPolygon": "true",
            "needPre": "true",
        }
        try:
            response = requests.get(
                "https://api.tianditu.gov.cn/administrative",
                params={"postStr": json.dumps(payload, ensure_ascii=False), "tk": token},
                headers={"User-Agent": "InSAR-Assistant/0.1 local desktop AOI search"},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - fallback source can still be used
            last_error = str(exc)
            continue

        remote_msg = _tianditu_response_message(data)
        items = _tianditu_admin_items(data)
        if remote_msg and not items:
            last_error = remote_msg
        for item in items:
            result = _tianditu_item_to_boundary(item, keyword)
            if result is None:
                continue
            key = (
                result.get("label"),
                round(float(result["bbox"]["west"]), 6),
                round(float(result["bbox"]["south"]), 6),
                round(float(result["bbox"]["east"]), 6),
                round(float(result["bbox"]["north"]), 6),
            )
            duplicate = False
            for current in results:
                current_key = (
                    current.get("label"),
                    round(float(current["bbox"]["west"]), 6),
                    round(float(current["bbox"]["south"]), 6),
                    round(float(current["bbox"]["east"]), 6),
                    round(float(current["bbox"]["north"]), 6),
                )
                if key == current_key:
                    duplicate = True
                    break
            if duplicate:
                continue
            results.append(result)
            if len(results) >= max_items:
                return results, None
        if results:
            return results, None
    return results, last_error or "未返回边界数据"


def _tianditu_response_message(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("msg", "message", "infocode", "status"):
        raw = value.get(key)
        if raw not in (None, "", 0, "0", "ok", "OK", "success", "SUCCESS"):
            return str(raw)
    return None


def _tianditu_admin_items(value: Any) -> list[dict]:
    items: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            has_name = any(k in node for k in ("name", "gb", "cityCode", "english", "nameabbrevation"))
            has_geometry = any(k in node for k in ("bound", "points", "region", "coordinates", "geometry"))
            if has_name and has_geometry:
                items.append(node)
            for key in (
                "data",
                "result",
                "results",
                "districts",
                "children",
                "sub",
                "subs",
                "subInfo",
                "administrative",
            ):
                child = node.get(key)
                if child is not None:
                    walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return items


def _tianditu_item_to_boundary(item: dict, fallback_label: str) -> dict | None:
    bbox = _tianditu_bbox(item)
    if bbox is None:
        return None
    geojson = _tianditu_geojson(item)
    parents = item.get("parents")
    parent_names: list[str] = []
    if isinstance(parents, list):
        for parent in parents:
            if isinstance(parent, dict) and parent.get("name"):
                parent_names.append(str(parent.get("name")))
    name = str(item.get("name") or item.get("gb") or fallback_label)
    label_parts = [*parent_names, name]
    label = " / ".join(dict.fromkeys([part for part in label_parts if part]))
    return {
        "label": label,
        "bbox": bbox,
        "geojson": geojson,
        "source": "天地图行政区划服务",
        "class": "boundary",
        "type": "administrative",
        "osm_type": None,
        "osm_id": item.get("cityCode"),
        "city_code": item.get("cityCode"),
        "admin_type": item.get("adminType"),
    }


def _tianditu_bbox(item: dict) -> dict | None:
    raw_bound = item.get("bound")
    if isinstance(raw_bound, str):
        nums = _numbers_from_text(raw_bound)
        if len(nums) >= 4:
            west, south, east, north = nums[:4]
            if west > east:
                west, east = east, west
            if south > north:
                south, north = north, south
            if _valid_lonlat_bbox(west, east, south, north):
                return {
                    "west": west,
                    "east": east,
                    "south": south,
                    "north": north,
                    "crs": "EPSG:4326",
                }
    positions: list[tuple[float, float]] = []
    for key in ("points", "region", "coordinates", "geometry"):
        _walk_tianditu_positions(item.get(key), positions)
    if not positions:
        return None
    lngs = [item[0] for item in positions]
    lats = [item[1] for item in positions]
    west, east, south, north = min(lngs), max(lngs), min(lats), max(lats)
    if not _valid_lonlat_bbox(west, east, south, north):
        return None
    return {"west": west, "east": east, "south": south, "north": north, "crs": "EPSG:4326"}


def _tianditu_geojson(item: dict) -> dict | None:
    positions: list[tuple[float, float]] = []
    for key in ("points", "region", "coordinates", "geometry"):
        _walk_tianditu_positions(item.get(key), positions)
    if len(positions) < 3:
        return None
    ring = [[lng, lat] for lng, lat in positions]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _walk_tianditu_positions(value: Any, out: list[tuple[float, float]]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ("points", "region", "coordinates", "geometry", "children"):
            _walk_tianditu_positions(value.get(key), out)
        return
    if isinstance(value, list):
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            lng, lat = float(value[0]), float(value[1])
            if -180 <= lng <= 180 and -90 <= lat <= 90:
                out.append((lng, lat))
            return
        for item in value:
            _walk_tianditu_positions(item, out)
        return
    if isinstance(value, str):
        nums = _numbers_from_text(value)
        for idx in range(0, len(nums) - 1, 2):
            lng, lat = nums[idx], nums[idx + 1]
            if -180 <= lng <= 180 and -90 <= lat <= 90:
                out.append((lng, lat))


def _numbers_from_text(value: str) -> list[float]:
    import re

    return [float(match) for match in re.findall(r"-?\d+(?:\.\d+)?", value)]


def _valid_lonlat_bbox(west: float, east: float, south: float, north: float) -> bool:
    return -180 <= west < east <= 180 and -90 <= south < north <= 90


def _walk_boundary_positions(value: Any, out: list[tuple[float, float]]) -> None:
    if not isinstance(value, list):
        return
    if (
        len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        out.append((float(value[0]), float(value[1])))
        return
    for item in value:
        _walk_boundary_positions(item, out)


def _boundary_bbox(feature: dict) -> dict | None:
    raw_bbox = feature.get("bbox")
    if isinstance(raw_bbox, list) and len(raw_bbox) >= 4:
        try:
            west, south, east, north = [float(v) for v in raw_bbox[:4]]
            if west < east and south < north:
                return {
                    "west": west,
                    "east": east,
                    "south": south,
                    "north": north,
                    "crs": "EPSG:4326",
                }
        except (TypeError, ValueError):
            pass
    props = feature.get("properties") or {}
    if isinstance(props, dict):
        raw = props.get("boundingbox")
        if isinstance(raw, list) and len(raw) >= 4:
            try:
                south, north, west, east = [float(v) for v in raw[:4]]
                if west < east and south < north:
                    return {
                        "west": west,
                        "east": east,
                        "south": south,
                        "north": north,
                        "crs": "EPSG:4326",
                    }
            except (TypeError, ValueError):
                pass
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None
    positions: list[tuple[float, float]] = []
    _walk_boundary_positions(geometry.get("coordinates"), positions)
    if not positions:
        return None
    lngs = [item[0] for item in positions]
    lats = [item[1] for item in positions]
    west, east, south, north = min(lngs), max(lngs), min(lats), max(lats)
    if west >= east or south >= north:
        return None
    return {"west": west, "east": east, "south": south, "north": north, "crs": "EPSG:4326"}


def _scene_row(scene: Any) -> dict:
    """Pick the table-relevant, JSON-safe fields from a Scene."""
    d = scene.model_dump(mode="json")
    return {
        "scene_id": d.get("scene_id"),
        "platform": d.get("platform"),
        "product_type": d.get("product_type"),
        "beam_mode": d.get("beam_mode"),
        "polarization": d.get("polarization"),
        "acquisition_datetime": d.get("acquisition_datetime"),
        "absolute_orbit": d.get("absolute_orbit"),
        "relative_orbit": d.get("relative_orbit"),
        "path": d.get("path") or d.get("relative_orbit"),
        "frame": d.get("frame"),
        "orbit_direction": d.get("orbit_direction"),
        "file_size_remote": d.get("file_size_remote"),
        "footprint_bbox": d.get("footprint_bbox"),
        "footprint_geojson": d.get("footprint_geojson"),
        "has_url": bool(d.get("url")),
        "download_url": d.get("url") or "",
    }


def _scene_from_row(row: dict[str, Any]) -> Any:
    """Rebuild a Scene from a frozen UI task snapshot row."""
    from insar_prep.core.models import Scene

    allowed = set(Scene.model_fields)
    data = {key: value for key, value in row.items() if key in allowed}
    if row.get("download_url") and not data.get("url"):
        data["url"] = row.get("download_url")
    if row.get("path") is not None and data.get("relative_orbit") is None:
        data["relative_orbit"] = row.get("path")
    return Scene.model_validate(data)


def _sort_scenes_by_acquisition_date(scenes: list[Any]) -> list[Any]:
    """Return scenes in chronological order, with undated rows kept last."""
    return sorted(
        scenes,
        key=lambda scene: (
            getattr(scene, "acquisition_datetime", None) is None,
            str(getattr(scene, "acquisition_datetime", "") or ""),
            str(getattr(scene, "scene_id", "") or ""),
        ),
    )
