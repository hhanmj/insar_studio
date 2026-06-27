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
    # --- left navigation (sidebar pages) ---
    "nav.project": {"en": "Project", "zh": "项目"},
    "nav.scenes": {"en": "Scenes", "zh": "影像"},
    "nav.planning": {"en": "Planning", "zh": "规划"},
    "nav.downloads": {"en": "Downloads", "zh": "下载中心"},
    "nav.reports": {"en": "Reports", "zh": "报告"},
    "nav.settings": {"en": "Settings", "zh": "设置"},
    "page.project.subtitle": {
        "en": "Create a workspace / project / region and set its area of interest.",
        "zh": "新建工作区、项目与研究区，并圈定研究范围（AOI）。",
    },
    "page.scenes.subtitle": {
        "en": "Import a local ASF cart and check scene consistency.",
        "zh": "导入本地 ASF 数据篮，检查影像是否一致。",
    },
    "page.planning.subtitle": {
        "en": "Plan orbit matching, DEM, and GACOS (offline, planning only).",
        "zh": "规划轨道匹配、DEM 与 GACOS（离线，仅生成计划）。",
    },
    "page.downloads.subtitle": {
        "en": "Real ASF / DEM / GACOS downloads and the task log.",
        "zh": "真实下载 ASF / DEM / GACOS，并查看任务日志。",
    },
    "page.reports.subtitle": {
        "en": "Generate the data-preparation report set.",
        "zh": "一键生成数据准备报告。",
    },
    # --- settings page ---
    "settings.title": {"en": "Settings", "zh": "设置"},
    "settings.language": {"en": "Language", "zh": "语言"},
    "settings.appearance": {"en": "Appearance", "zh": "外观"},
    "settings.theme": {"en": "Theme", "zh": "主题"},
    "theme.light": {"en": "Light", "zh": "浅色"},
    "theme.dark": {"en": "Dark", "zh": "深色"},
    "settings.credentials.title": {"en": "Accounts & keys", "zh": "账户与密钥"},
    "settings.credentials.subtitle": {
        "en": "Credentials are stored only in your OS keyring, never in a project file.",
        "zh": "凭据仅保存在系统密钥环中，绝不写入项目文件。",
    },
    "settings.earthdata": {"en": "Earthdata Login\u2026", "zh": "Earthdata 登录\u2026"},
    "settings.opentopo": {
        "en": "OpenTopography API Key\u2026",
        "zh": "OpenTopography API 密钥\u2026",
    },
    "settings.gacos": {"en": "GACOS Email\u2026", "zh": "GACOS 邮箱\u2026"},
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
    "aoi.title": {"en": "Area of interest (AOI)", "zh": "研究范围（AOI）"},
    "aoi.apply": {"en": "Set AOI for current region", "zh": "设为当前研究区范围"},
    # --- ASF cart panel ---
    "asf.title": {"en": "ASF cart import", "zh": "导入 ASF 数据篮"},
    "asf.import": {"en": "Import cart", "zh": "导入"},
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
    "scenecheck.run": {"en": "Run scene check", "zh": "开始检查"},
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
    # --- shared dialog button / field labels ---
    "common.save": {"en": "Save", "zh": "保存"},
    "common.close": {"en": "Close", "zh": "关闭"},
    "common.clear_stored": {"en": "Clear stored", "zh": "清除已保存"},
    "common.name": {"en": "Name:", "zh": "名称："},
    "common.root_path": {"en": "Root path:", "zh": "根目录："},
    # --- New Workspace / Project / Region dialogs ---
    "dlg.workspace.title": {"en": "New Workspace", "zh": "新建工作区"},
    "dlg.project.title": {"en": "New Project", "zh": "新建项目"},
    "dlg.region.title": {"en": "New Region", "zh": "新建研究区"},
    # --- Earthdata login dialog ---
    "dlg.earthdata.title": {"en": "Earthdata Login", "zh": "Earthdata 登录"},
    "dlg.earthdata.help": {
        "en": (
            "Sign in to NASA Earthdata to download Sentinel-1 SLCs. Paste a personal "
            "token (recommended) — click 'Open Earthdata token page' to generate one, "
            "then copy it here — or enter your username and password. Credentials are "
            "stored only in your operating system's secret store (never in a project file)."
        ),
        "zh": (
            "登录 NASA Earthdata 以下载 Sentinel-1 SLC。推荐使用个人令牌：点击"
            "「打开 Earthdata 令牌页面」生成后粘贴到这里；也可以填写用户名和密码。"
            "凭据只会保存在系统的安全存储中，不会写入任何项目文件。"
        ),
    },
    "dlg.earthdata.token": {"en": "Token:", "zh": "令牌："},
    "dlg.earthdata.username": {"en": "or Username:", "zh": "或用户名："},
    "dlg.earthdata.password": {"en": "Password:", "zh": "密码："},
    "dlg.earthdata.token_ph": {
        "en": "Paste your Earthdata bearer token (recommended)",
        "zh": "粘贴你的 Earthdata 令牌（推荐）",
    },
    "dlg.earthdata.open_page": {"en": "Open Earthdata token page", "zh": "打开 Earthdata 令牌页面"},
    "dlg.earthdata.test": {"en": "Test connection", "zh": "测试连接"},
    "dlg.earthdata.status": {
        "en": "Stored Earthdata credential: {status}",
        "zh": "已保存的 Earthdata 凭据：{status}",
    },
    "dlg.earthdata.saved_token": {
        "en": "Saved Earthdata token to the OS keyring.",
        "zh": "Earthdata 令牌已保存到系统密钥环。",
    },
    "dlg.earthdata.saved_login": {
        "en": "Saved Earthdata login to the OS keyring.",
        "zh": "Earthdata 账号已保存到系统密钥环。",
    },
    "dlg.earthdata.need_input": {
        "en": "Enter a token, or both a username and password.",
        "zh": "请填写令牌，或同时填写用户名和密码。",
    },
    "dlg.earthdata.cleared": {
        "en": "Cleared stored Earthdata credentials.",
        "zh": "已清除保存的 Earthdata 凭据。",
    },
    "dlg.earthdata.none_to_clear": {
        "en": "No stored Earthdata credentials to clear.",
        "zh": "没有可清除的 Earthdata 凭据。",
    },
    "dlg.earthdata.need_extra": {
        "en": "Install the 'download' extra (requests) to test the connection.",
        "zh": "测试连接需要安装 download 附加组件（requests）。",
    },
    "dlg.earthdata.test_ok": {"en": "Connection test OK ({msg})", "zh": "连接测试通过（{msg}）"},
    "dlg.earthdata.test_fail": {
        "en": "Connection test FAILED ({msg})",
        "zh": "连接测试失败（{msg}）",
    },
    # --- OpenTopography key dialog ---
    "dlg.opentopo.title": {"en": "OpenTopography API Key", "zh": "OpenTopography API 密钥"},
    "dlg.opentopo.intro": {
        "en": (
            "Enter your personal OpenTopography API key to download DEMs. Each user "
            "supplies their own free key (no key is bundled, so heavy use never shares a "
            "rate limit). The key is stored only in your operating system's secret store "
            "(never in a project file)."
        ),
        "zh": (
            "填写你个人的 OpenTopography API 密钥以下载 DEM。每位用户使用自己的免费密钥"
            "（软件不内置密钥，避免共用导致触发限额）。密钥只会保存在系统的安全存储中，"
            "不会写入任何项目文件。"
        ),
    },
    "dlg.opentopo.key_label": {"en": "API key:", "zh": "API 密钥："},
    "dlg.opentopo.key_ph": {
        "en": "Paste your OpenTopography API key",
        "zh": "粘贴你的 OpenTopography API 密钥",
    },
    "dlg.opentopo.open_register": {"en": "Open registration page", "zh": "打开注册页面"},
    "dlg.opentopo.open_key": {"en": "Open API key page", "zh": "打开密钥申请页面"},
    "dlg.opentopo.status": {
        "en": "Stored OpenTopography API key: {status}",
        "zh": "已保存的 OpenTopography 密钥：{status}",
    },
    "dlg.opentopo.need_key": {
        "en": "Enter your OpenTopography API key first.",
        "zh": "请先填写 OpenTopography API 密钥。",
    },
    "dlg.opentopo.saved": {
        "en": "Saved OpenTopography API key to the OS keyring.",
        "zh": "OpenTopography 密钥已保存到系统密钥环。",
    },
    "dlg.opentopo.cleared": {
        "en": "Cleared the stored OpenTopography API key.",
        "zh": "已清除保存的 OpenTopography 密钥。",
    },
    "dlg.opentopo.none_to_clear": {
        "en": "No stored OpenTopography API key to clear.",
        "zh": "没有可清除的 OpenTopography 密钥。",
    },
    # --- GACOS email dialog ---
    "dlg.gacos.title": {"en": "GACOS Email", "zh": "GACOS 邮箱"},
    "dlg.gacos.intro": {
        "en": (
            "Enter the email address GACOS should deliver result links to. GACOS has no "
            "API key: a request is a web-form submission, and the products are emailed to "
            "this address. It is stored only in your operating system's secret store "
            "(never in a project file)."
        ),
        "zh": (
            "填写 GACOS 用于投递结果链接的邮箱。GACOS 没有 API 密钥：请求通过网页表单提交，"
            "产品会发送到这个邮箱。该邮箱只会保存在系统的安全存储中，不会写入任何项目文件。"
        ),
    },
    "dlg.gacos.email_label": {"en": "Email:", "zh": "邮箱："},
    "dlg.gacos.open_portal": {"en": "Open GACOS website", "zh": "打开 GACOS 网站"},
    "dlg.gacos.status": {
        "en": "Stored GACOS email: {status}",
        "zh": "已保存的 GACOS 邮箱：{status}",
    },
    "dlg.gacos.need_email": {
        "en": "Enter your GACOS email first.",
        "zh": "请先填写 GACOS 邮箱。",
    },
    "dlg.gacos.saved": {
        "en": "Saved GACOS email to the OS keyring.",
        "zh": "GACOS 邮箱已保存到系统密钥环。",
    },
    "dlg.gacos.cleared": {
        "en": "Cleared the stored GACOS email.",
        "zh": "已清除保存的 GACOS 邮箱。",
    },
    "dlg.gacos.none_to_clear": {
        "en": "No stored GACOS email to clear.",
        "zh": "没有可清除的 GACOS 邮箱。",
    },
    # --- AOI map ---
    "aoi.pick_on_map": {"en": "Pick on map\u2026", "zh": "在地图上选取\u2026"},
    "aoi.mode.map": {"en": "Map selection", "zh": "地图选取"},
    "aoi.map.hint": {
        "en": "Draw a rectangle on the map to fill the bounding box.",
        "zh": "在地图上拉框即可自动填入边界范围。",
    },
    "aoi.map.use": {"en": "Use drawn box as AOI", "zh": "使用框选范围作为 AOI"},
    "aoi.map.unavailable": {
        "en": "The interactive map needs the QtWebEngine component (PySide6-Addons).",
        "zh": "交互式地图需要 QtWebEngine 组件（PySide6-Addons）。",
    },
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
    _save_setting("language", code, path=path)


def load_saved_theme(*, path: Path | None = None, default: str = "light") -> str:
    """Load the persisted GUI theme name (default ``light``)."""
    settings = _load_settings(path or settings_file())
    value = settings.get("theme", default)
    return value if isinstance(value, str) and value else default


def save_theme(name: str, *, path: Path | None = None) -> None:
    """Persist ``name`` as the GUI theme (best-effort; never raises)."""
    _save_setting("theme", name, path=path)


def _save_setting(key: str, value: str, *, path: Path | None = None) -> None:
    target = path or settings_file()
    try:
        existing = _load_settings(target)
        existing[key] = value
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - best-effort persistence
        logger.debug("could not save setting %s: %s", key, exc)
