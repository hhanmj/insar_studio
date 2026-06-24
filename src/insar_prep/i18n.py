"""Lightweight runtime internationalization (i18n) for the GUI (Task 055).

A small, dependency-free translation layer so the desktop GUI can switch between
English and Simplified Chinese at runtime. It is deliberately minimal (a nested
dict catalog + a ``tr`` lookup) rather than Qt's ``.ts``/``.qm`` toolchain, so no
compile step or extra build dependency is needed and the catalog is unit-testable
without PySide6.

Usage::

    from insar_prep import i18n
    i18n.set_language("zh")
    label.setText(i18n.tr("aoi.title"))

Widgets keep their English literal as the natural fallback and expose a
``retranslate_ui()`` that re-applies ``tr(...)`` so a language change updates the
live UI. The chosen language is persisted to a per-user settings file so it is
remembered across runs; tests construct widgets directly and get the default
``en`` unless they call :func:`set_language`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from insar_prep.core.logging import get_logger

logger = get_logger("i18n")

DEFAULT_LANGUAGE = "en"

# Supported language codes mapped to their (native) display names.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "中文",
}

# The active language for the process. Defaults to English so non-GUI code and
# tests are deterministic; the GUI loads the persisted choice at launch.
_current_language: str = DEFAULT_LANGUAGE


# Translation catalog: key -> {language_code: text}. English values mirror the
# literal strings used in the widgets so English behaviour is unchanged and an
# untranslated key falls back to English, then to the key itself.
_CATALOG: dict[str, dict[str, str]] = {
    # --- application chrome ---
    "app.title": {"en": "INSAR Prep Assistant", "zh": "INSAR 数据准备助手"},
    "menu.language": {"en": "&Language", "zh": "语言(&L)"},
    "menu.help": {"en": "&Help", "zh": "帮助(&H)"},
    "menu.about": {"en": "About", "zh": "关于"},
    "about.text": {
        "en": "INSAR Prep Assistant — SARscape-oriented InSAR data preparation.",
        "zh": "INSAR 数据准备助手 —— 面向 SARscape 的 InSAR 数据准备工具。",
    },
    "status.ready": {"en": "Ready", "zh": "就绪"},
    "tree.workspace": {"en": "Workspace", "zh": "工作区"},
    # --- toolbar ---
    "toolbar.new_workspace": {"en": "New Workspace", "zh": "新建工作区"},
    "toolbar.new_project": {"en": "New Project", "zh": "新建项目"},
    "toolbar.new_region": {"en": "New Region", "zh": "新建区域"},
    "toolbar.earthdata_login": {"en": "Earthdata Login", "zh": "Earthdata 登录"},
    "toolbar.gacos_email": {"en": "GACOS Email", "zh": "GACOS 邮箱"},
    # --- shared button labels ---
    "common.browse": {"en": "Browse\u2026", "zh": "浏览\u2026"},
    "common.run": {"en": "Run", "zh": "运行"},
    "common.cancel": {"en": "Cancel", "zh": "取消"},
    # --- workflow steps / queue ---
    "workflow.title": {"en": "Workflow steps", "zh": "工作流步骤"},
    "queue.tasks": {"en": "Task queue", "zh": "任务队列"},
    "queue.log": {"en": "Log", "zh": "日志"},
    # --- AOI panel ---
    "aoi.title": {"en": "Area of interest (AOI)", "zh": "感兴趣区 (AOI)"},
    "aoi.apply": {"en": "Set AOI for current region", "zh": "为当前区域设置 AOI"},
    # --- ASF cart panel ---
    "asf.title": {"en": "ASF cart import", "zh": "ASF 购物车导入"},
    "asf.import": {"en": "Import cart", "zh": "导入购物车"},
    # --- scene table headers ---
    "scene.col.id": {"en": "Scene ID", "zh": "影像 ID"},
    "scene.col.platform": {"en": "Platform", "zh": "卫星平台"},
    "scene.col.acquisition": {"en": "Acquisition", "zh": "获取时间"},
    "scene.col.product": {"en": "Product", "zh": "产品类型"},
    "scene.col.beam": {"en": "Beam", "zh": "波束模式"},
    "scene.col.polarization": {"en": "Polarization", "zh": "极化方式"},
    "scene.col.url": {"en": "URL", "zh": "下载链接"},
    # --- scene consistency check panel ---
    "scenecheck.title": {"en": "Scene consistency check", "zh": "影像一致性检查"},
    "scenecheck.run": {"en": "Run scene check", "zh": "运行影像检查"},
    # --- offline planning panel ---
    "planning.title": {
        "en": "Offline planning (orbit / DEM / GACOS)",
        "zh": "离线规划（轨道 / DEM / GACOS）",
    },
    "planning.orbit.title": {"en": "Orbit matching", "zh": "轨道匹配"},
    "planning.orbit.button": {"en": "Scan and match orbits", "zh": "扫描并匹配轨道"},
    "planning.dem.title": {"en": "DEM request + conversion plan", "zh": "DEM 请求 + 转换计划"},
    "planning.dem.button": {"en": "Build DEM plan", "zh": "生成 DEM 计划"},
    "planning.gacos.title": {
        "en": "GACOS request plan + import check",
        "zh": "GACOS 请求计划 + 导入检查",
    },
    "planning.gacos.button": {"en": "Build GACOS plan", "zh": "生成 GACOS 计划"},
    # --- reports panel ---
    "report.title": {"en": "Reports", "zh": "报告"},
    "report.generate": {"en": "Generate reports", "zh": "生成报告"},
    # --- ASF SLC download panel ---
    "download.title": {"en": "ASF SLC Download", "zh": "ASF SLC 下载"},
    "download.login": {"en": "Earthdata Login\u2026", "zh": "Earthdata 登录\u2026"},
    # --- DEM download panel ---
    "dem.title": {"en": "DEM Download (OpenTopography)", "zh": "DEM 下载 (OpenTopography)"},
    "dem.key_button": {"en": "OpenTopography API Key\u2026", "zh": "OpenTopography API 密钥\u2026"},
    # --- GACOS download panel ---
    "gacos.title": {"en": "GACOS Download", "zh": "GACOS 下载"},
    "gacos.email_button": {"en": "GACOS Email\u2026", "zh": "GACOS 邮箱\u2026"},
    "gacos.submit": {"en": "Submit request", "zh": "提交请求"},
    "gacos.fetch": {"en": "Download result", "zh": "下载结果"},
    "gacos.dates_label": {
        "en": "Dates (one YYYYMMDD per line):",
        "zh": "日期（每行一个 YYYYMMDD）：",
    },
    "gacos.url_label": {"en": "Result link(s) (one per line):", "zh": "结果链接（每行一个）："},
}


def available_languages() -> list[tuple[str, str]]:
    """Return ``[(code, display_name), ...]`` for the supported languages."""
    return [(code, name) for code, name in _LANGUAGE_NAMES.items()]


def is_supported(code: str) -> bool:
    """Return True if ``code`` is a supported language code."""
    return code in _LANGUAGE_NAMES


def get_language() -> str:
    """Return the active language code (e.g. ``"en"``)."""
    return _current_language


def language_name(code: str | None = None) -> str:
    """Return the display name for ``code`` (or the active language)."""
    return _LANGUAGE_NAMES.get(code or _current_language, code or _current_language)


def set_language(code: str) -> None:
    """Set the active language. Unknown codes fall back to the default."""
    global _current_language
    if code not in _LANGUAGE_NAMES:
        logger.warning("unsupported language %r; keeping %s", code, _current_language)
        return
    _current_language = code


def tr(key: str, /, **kwargs: object) -> str:
    """Translate ``key`` into the active language.

    Falls back to English, then to the raw key. Any ``kwargs`` are applied with
    :meth:`str.format`, so catalog entries may contain ``{name}`` placeholders.
    """
    entry = _CATALOG.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(_current_language) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# --- persistence -----------------------------------------------------------


def config_dir() -> Path:
    """Return the per-user configuration directory (cross-platform)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "insar-prep"


def settings_file() -> Path:
    """Return the path of the GUI settings file."""
    return config_dir() / "settings.json"


def _load_settings(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_saved_language(*, path: Path | None = None) -> str:
    """Load and apply the persisted language (default ``en``); return the code."""
    settings = _load_settings(path or settings_file())
    code = settings.get("language", DEFAULT_LANGUAGE)
    if not is_supported(code):
        code = DEFAULT_LANGUAGE
    set_language(code)
    return code


def save_language(code: str, *, path: Path | None = None) -> None:
    """Persist ``code`` as the GUI language (best-effort; never raises)."""
    target = path or settings_file()
    try:
        existing = _load_settings(target)
        existing["language"] = code
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - best-effort persistence
        logger.debug("could not save language setting: %s", exc)
