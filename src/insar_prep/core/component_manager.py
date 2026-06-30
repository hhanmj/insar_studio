"""Optional online component management for the desktop app.

Large runtime pieces such as GDAL/rasterio can be shipped outside the main
desktop executable.  This module keeps that state under the user's local app
data directory and uses only the Python standard library so the base app can
check/install components even before optional scientific libraries are present.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insar_prep import __version__
from insar_prep.core.logging import get_logger

logger = get_logger("core.component_manager")

DEFAULT_COMPONENT_MANIFEST_URL = (
    "https://github.com/hhanmj/insar_studio/releases/latest/download/components-manifest.json"
)
COMPONENT_MANIFEST_ENV = "INSAR_COMPONENT_MANIFEST_URL"
DEM_GDAL_COMPONENT_ID = "dem-gdal"
EGM2008_GEOID_CANDIDATES = (
    "geoids/egm2008_5.npz",
    "geoids/egm2008-5.npz",
    "egm2008_5.npz",
    "egm2008-5.npz",
    "egm2008_1.npz",
    "egm2008-1.npz",
    "egm2008.npz",
)


class ComponentError(RuntimeError):
    """A user-visible optional component operation failed."""


@dataclass(frozen=True)
class ComponentSpec:
    """One optional component entry from a component manifest."""

    id: str
    name: str
    version: str
    size_mb: float | None = None
    url: str = ""
    sha256: str = ""
    entry: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentSpec | None:
        component_id = str(data.get("id") or "").strip()
        if not component_id:
            return None
        size_raw = data.get("size_mb")
        try:
            size_mb = float(size_raw) if size_raw not in (None, "") else None
        except (TypeError, ValueError):
            size_mb = None
        return cls(
            id=component_id,
            name=str(data.get("name") or component_id),
            version=str(data.get("version") or "0.0.0"),
            size_mb=size_mb,
            url=str(data.get("url") or "").strip(),
            sha256=str(data.get("sha256") or "").strip().lower(),
            entry=str(data.get("entry") or "").strip(),
            description=str(data.get("description") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "size_mb": self.size_mb,
            "url": self.url,
            "sha256": self.sha256,
            "entry": self.entry,
            "description": self.description,
        }


def app_data_dir() -> Path:
    """Return the per-user application data root."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "InSAR Assistant"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "InSAR Assistant"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "insar-assistant"


def component_root() -> Path:
    """Return the directory containing installed optional components."""
    return app_data_dir() / "components"


def default_manifest_url() -> str:
    """Return the component manifest URL, allowing local test override."""
    return os.environ.get(COMPONENT_MANIFEST_ENV, DEFAULT_COMPONENT_MANIFEST_URL).strip()


def _state_file(root: Path | None = None) -> Path:
    return (component_root() if root is None else root) / "components.json"


def _manifest_cache_file(root: Path | None = None) -> Path:
    return (component_root() if root is None else root) / "manifest.cache.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _builtin_manifest() -> dict[str, Any]:
    """A local fallback manifest so the UI can explain the component model."""
    return {
        "version": 1,
        "generated_by": f"insar-prep/{__version__}",
        "components": [
            {
                "id": DEM_GDAL_COMPONENT_ID,
                "name": "DEM 高级转换组件",
                "version": __version__,
                "size_mb": None,
                "url": "",
                "sha256": "",
                "entry": "site-packages",
                "description": (
                    "GDAL/rasterio/numpy 运行库与 EGM2008 大地水准面网格；"
                    "用于 DEM 椭球高转换和 SARscape DEM 适配输出。"
                ),
            }
        ],
    }


def _http_get_bytes(url: str, timeout: float = 10.0) -> bytes:
    if Path(url).exists():
        return Path(url).read_bytes()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return Path(urllib.request.url2pathname(parsed.path)).read_bytes()
    request = urllib.request.Request(  # noqa: S310 - caller controls component URL.
        url,
        headers={
            "Accept": "application/json, application/octet-stream;q=0.9, */*;q=0.8",
            "User-Agent": f"insar-prep/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def load_manifest(*, refresh: bool = False, url: str | None = None) -> dict[str, Any]:
    """Load the component manifest.

    The function first tries the network when requested, then falls back to the
    cached manifest, then to a built-in placeholder.  It never raises for simple
    offline/missing-manifest conditions because settings screens should remain
    usable without a network.
    """
    root = component_root()
    manifest_url = (url or default_manifest_url()).strip()
    cache_path = _manifest_cache_file(root)
    if refresh and manifest_url:
        try:
            raw = _http_get_bytes(manifest_url, timeout=10)
            data = json.loads(raw.decode("utf-8-sig"))
            if isinstance(data, dict):
                data["_source_url"] = manifest_url
                data["_checked_at"] = int(time.time())
                _write_json(cache_path, data)
                return data
        except Exception as exc:  # noqa: BLE001 - optional manifest is best-effort
            logger.debug("component manifest refresh failed: %s", exc)
    cached = _load_json(cache_path)
    if cached:
        return cached
    data = _builtin_manifest()
    data["_source_url"] = manifest_url
    return data


def _manifest_components(manifest: dict[str, Any]) -> list[ComponentSpec]:
    values = manifest.get("components")
    items = [
        item
        for item in (list(values) if isinstance(values, list) else [])
        if not (isinstance(item, dict) and str(item.get("id") or "").strip() == "geoid-egm2008")
    ]
    seen_ids = {str(item.get("id") or "").strip() for item in items if isinstance(item, dict)}
    for fallback in _builtin_manifest().get("components", []):
        if isinstance(fallback, dict) and str(fallback.get("id") or "").strip() not in seen_ids:
            items.append(fallback)
    specs: list[ComponentSpec] = []
    for item in items:
        if isinstance(item, dict):
            spec = ComponentSpec.from_dict(item)
            if spec is not None:
                specs.append(spec)
    return specs


def _find_component(manifest: dict[str, Any], component_id: str) -> ComponentSpec:
    for spec in _manifest_components(manifest):
        if spec.id == component_id:
            return spec
    raise ComponentError(f"组件清单中没有找到：{component_id}")


def _load_state(root: Path | None = None) -> dict[str, Any]:
    data = _load_json(_state_file(root))
    if not isinstance(data.get("installed"), dict):
        data["installed"] = {}
    return data


def _save_state(data: dict[str, Any], root: Path | None = None) -> None:
    _write_json(_state_file(root), data)


def _safe_component_dir(root: Path, component_id: str, version: str) -> Path:
    target = (root / component_id / version).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ComponentError("组件路径越界，已拒绝安装。") from exc
    return target


def _safe_extract_zip(archive: Path, target: Path) -> None:
    target_resolved = target.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            destination = (target / member.filename).resolve()
            try:
                destination.relative_to(target_resolved)
            except ValueError as exc:
                raise ComponentError("组件压缩包包含不安全路径，已拒绝安装。") from exc
        zf.extractall(target)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(url: str, dest: Path, *, timeout: float = 30.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(url).exists():
        shutil.copy2(Path(url), dest)
        return
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        shutil.copy2(Path(urllib.request.url2pathname(parsed.path)), dest)
        return
    request = urllib.request.Request(  # noqa: S310 - component URL comes from signed manifest.
        url,
        headers={"User-Agent": f"insar-prep/{__version__}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        with dest.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)


def _component_entry_path(root: Path, installed: dict[str, Any]) -> Path | None:
    path = str(installed.get("path") or "").strip()
    if not path:
        return None
    component_dir = Path(path)
    entry = str(installed.get("entry") or "").strip()
    entry_path = (component_dir / entry).resolve() if entry else component_dir.resolve()
    root_resolved = root.resolve()
    try:
        entry_path.relative_to(root_resolved)
    except ValueError:
        return None
    return entry_path if entry_path.exists() else None


def _component_base_path(root: Path, installed: dict[str, Any]) -> Path | None:
    path = str(installed.get("path") or "").strip()
    if not path:
        return None
    component_dir = Path(path).resolve()
    try:
        component_dir.relative_to(root.resolve())
    except ValueError:
        return None
    return component_dir if component_dir.exists() else None


def component_entry_path(component_id: str) -> Path | None:
    """Return an installed component entry path, if available."""
    root = component_root()
    installed = _load_state(root).get("installed", {}).get(component_id)
    if not isinstance(installed, dict):
        return None
    return _component_entry_path(root, installed)


def find_component_file(component_id: str, candidates: tuple[str, ...]) -> Path | None:
    """Return a file inside an installed component by trying common names."""
    root = component_root()
    installed = _load_state(root).get("installed", {}).get(component_id)
    if not isinstance(installed, dict):
        return None
    roots = [
        path
        for path in (
            _component_entry_path(root, installed),
            _component_base_path(root, installed),
        )
        if path is not None
    ]
    for name in candidates:
        for base in roots:
            direct = base / name
            if direct.is_file():
                return direct
    lowered = {name.lower() for name in candidates}
    for base in roots:
        if base.is_file():
            if base.name.lower() in lowered or base.stem.lower().startswith("egm2008"):
                return base
            continue
        for path in base.rglob("*.npz"):
            relative = path.relative_to(base).as_posix().lower()
            if path.name.lower() in lowered or relative in lowered or path.stem.lower().startswith("egm2008"):
                return path
    return None


_DLL_HANDLES: list[Any] = []


def activate_component(component_id: str = DEM_GDAL_COMPONENT_ID) -> bool:
    """Add an installed component's runtime paths to the current process."""
    root = component_root()
    installed = _load_state(root).get("installed", {}).get(component_id)
    if not isinstance(installed, dict):
        return False
    entry = _component_entry_path(root, installed)
    if entry is None:
        return False
    if not entry.is_dir():
        return True
    entry_text = str(entry)
    if entry_text not in sys.path:
        sys.path.insert(0, entry_text)
    rasterio_dir = entry / "rasterio"
    gdal_data = rasterio_dir / "gdal_data"
    proj_data = rasterio_dir / "proj_data"
    if gdal_data.exists():
        os.environ["GDAL_DATA"] = str(gdal_data)
    if proj_data.exists():
        os.environ["PROJ_LIB"] = str(proj_data)
        os.environ["PROJ_DATA"] = str(proj_data)
    for candidate in (entry / "bin", entry.parent / "bin"):
        if not candidate.exists():
            continue
        path_text = str(candidate)
        os.environ["PATH"] = path_text + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                _DLL_HANDLES.append(os.add_dll_directory(path_text))  # type: ignore[attr-defined]
            except OSError:
                pass
    return True


def _dem_runtime_available() -> bool:
    activate_component(DEM_GDAL_COMPONENT_ID)
    return importlib.util.find_spec("rasterio") is not None


def _egm2008_grid_available() -> bool:
    return find_component_file(DEM_GDAL_COMPONENT_ID, EGM2008_GEOID_CANDIDATES) is not None


def get_component_status(*, refresh: bool = False) -> dict[str, Any]:
    """Return a JSON-safe optional component status snapshot."""
    root = component_root()
    manifest = load_manifest(refresh=refresh)
    state = _load_state(root)
    installed_map = state.get("installed", {})
    runtime = _dem_runtime_available()
    egm2008_grid = _egm2008_grid_available()
    components: list[dict[str, Any]] = []
    for spec in _manifest_components(manifest):
        installed = installed_map.get(spec.id) if isinstance(installed_map, dict) else None
        installed_path = ""
        installed_version = ""
        entry_path = None
        if isinstance(installed, dict):
            installed_version = str(installed.get("version") or "")
            installed_path = str(installed.get("path") or "")
            entry_path = _component_entry_path(root, installed)
        is_installed = entry_path is not None
        runtime_available = runtime and egm2008_grid if spec.id == DEM_GDAL_COMPONENT_ID else is_installed
        if spec.id == DEM_GDAL_COMPONENT_ID and runtime and not egm2008_grid:
            state_label = "partial"
        elif spec.id == DEM_GDAL_COMPONENT_ID and is_installed and not runtime:
            state_label = "broken"
        elif is_installed:
            state_label = "installed"
        elif runtime_available:
            state_label = "bundled"
        elif spec.url:
            state_label = "available"
        else:
            state_label = "not_configured"
        components.append(
            {
                **spec.to_dict(),
                "installed": is_installed,
                "installed_version": installed_version,
                "installed_path": installed_path,
                "runtime_available": runtime_available,
                "partial_runtime_available": bool(spec.id == DEM_GDAL_COMPONENT_ID and runtime and not egm2008_grid),
                "egm2008_grid_available": bool(egm2008_grid) if spec.id == DEM_GDAL_COMPONENT_ID else None,
                "state": state_label,
                "can_install": bool(spec.url),
            }
        )
    return {
        "ok": True,
        "root": str(root),
        "manifest_url": str(manifest.get("_source_url") or default_manifest_url()),
        "manifest_checked_at": manifest.get("_checked_at"),
        "components": components,
    }


def install_component(component_id: str, *, refresh_manifest: bool = True) -> dict[str, Any]:
    """Download, verify, and install one optional component archive."""
    root = component_root()
    manifest = load_manifest(refresh=refresh_manifest)
    spec = _find_component(manifest, component_id)
    if not spec.url:
        raise ComponentError("该组件还没有发布在线安装包；当前版本仅完成按需组件机制接入。")

    downloads = root / "_downloads"
    suffix = Path(urllib.parse.urlparse(spec.url).path).suffix or ".zip"
    archive = downloads / f"{spec.id}-{spec.version}{suffix}"
    part = archive.with_suffix(archive.suffix + ".part")
    if part.exists():
        part.unlink()
    _download_file(spec.url, part)
    if spec.sha256:
        actual = _sha256_file(part)
        if actual.lower() != spec.sha256.lower():
            try:
                part.unlink()
            except OSError:
                pass
            raise ComponentError("组件校验失败：SHA256 不一致，已删除下载文件。")
    part.replace(archive)

    target = _safe_component_dir(root, spec.id, spec.version)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        _safe_extract_zip(archive, target)
    else:
        shutil.copy2(archive, target / archive.name)

    state = _load_state(root)
    installed = state.setdefault("installed", {})
    installed[spec.id] = {
        "id": spec.id,
        "name": spec.name,
        "version": spec.version,
        "path": str(target),
        "entry": spec.entry,
        "sha256": spec.sha256,
        "installed_at": int(time.time()),
    }
    _save_state(state, root)
    activate_component(spec.id)
    return get_component_status(refresh=False)


def remove_component(component_id: str) -> dict[str, Any]:
    """Remove an installed optional component from local app data."""
    root = component_root()
    state = _load_state(root)
    installed = state.get("installed", {})
    item = installed.get(component_id) if isinstance(installed, dict) else None
    if isinstance(item, dict):
        path = Path(str(item.get("path") or ""))
        try:
            target = path.resolve()
            target.relative_to(root.resolve())
            if target.exists():
                shutil.rmtree(target)
        except (OSError, ValueError):
            logger.debug("component removal skipped unsafe/missing path: %s", path)
        installed.pop(component_id, None)
        _save_state(state, root)
    return get_component_status(refresh=False)
