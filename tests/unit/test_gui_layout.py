"""Offscreen GUI tests for the redesigned sidebar + stacked-page layout (Task 056).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Verifies the navigation
switches pages, the settings page drives language/theme, and the theme builds.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep import i18n
from insar_prep.gui import theme as theme_module

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_GACOS_PANEL = "insar_prep.gui.widgets.gacos_download_panel"
_DEM_PANEL = "insar_prep.gui.widgets.dem_download_panel"
_ASF_PANEL = "insar_prep.gui.widgets.download_panel"


@pytest.fixture(autouse=True)
def _offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(f"{_GACOS_PANEL}.stored_gacos_email_status", lambda: "none")
    monkeypatch.setattr(f"{_DEM_PANEL}.stored_api_key_status", lambda: "none")
    monkeypatch.setattr(f"{_ASF_PANEL}.stored_credential_status", lambda: "none")
    monkeypatch.setattr(i18n, "save_language", lambda code, **kw: None)
    monkeypatch.setattr(i18n, "save_theme", lambda name, **kw: None)
    i18n.set_language("en")
    from insar_prep.gui.app import create_application

    create_application([])
    yield
    i18n.set_language("en")


def _window():
    from insar_prep.gui.main_window import MainWindow

    return MainWindow()


def test_nav_has_six_pages_and_switches(tmp_path: Path) -> None:
    window = _window()
    assert window.nav_list.count() == 6
    assert window.pages.count() == 6
    window.nav_list.setCurrentRow(3)  # Downloads
    assert window.pages.currentIndex() == 3
    window.nav_list.setCurrentRow(5)  # Settings
    assert window.pages.currentIndex() == 5


def test_settings_language_switch_retranslates() -> None:
    window = _window()
    assert window.nav_list.item(0).text() == "Project"
    index = window.settings_panel.language_combo.findData("zh")
    window.settings_panel.language_combo.setCurrentIndex(index)
    assert i18n.get_language() == "zh"
    assert window.nav_list.item(0).text() == "项目"


def test_settings_theme_combo_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window()
    applied: list[str] = []
    monkeypatch.setattr(theme_module, "apply_theme", lambda app, name: applied.append(name))
    index = window.settings_panel.theme_combo.findData("dark")
    window.settings_panel.theme_combo.setCurrentIndex(index)
    assert applied == ["dark"]


def test_theme_stylesheet_builds() -> None:
    light = theme_module.build_stylesheet("light")
    dark = theme_module.build_stylesheet("dark")
    assert "QListWidget#nav_sidebar" in light
    assert light != dark
    assert "QGroupBox" in light
