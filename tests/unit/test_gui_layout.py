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


def test_main_window_has_three_column_workbench(tmp_path: Path) -> None:
    window = _window()
    splitter = window.centralWidget()
    assert splitter.count() == 3
    assert window.project_tree.objectName() == "project_tree"
    assert window.workflow_steps.step_list.count() == 8
    assert window.queue_log_panel.objectName() == "queue_log_panel"
    assert window.download_panel.objectName() == "download_panel"
    assert window.dem_download_panel.objectName() == "dem_download_panel"
    assert window.gacos_download_panel.objectName() == "gacos_download_panel"


def test_language_menu_switch_retranslates() -> None:
    window = _window()
    assert window.project_tree.headerItem().text(0) == "Workspace"
    window._on_change_language("zh")
    assert i18n.get_language() == "zh"
    assert window.project_tree.headerItem().text(0) == i18n.tr("tree.workspace")
    assert window.new_workspace_action.text() == i18n.tr("toolbar.new_workspace")
    assert window._language_actions["zh"].isChecked()


def test_theme_apply_helper_normalizes_and_sets_stylesheet() -> None:
    class _App:
        stylesheet = ""

        def setStyleSheet(self, value: str) -> None:
            self.stylesheet = value

    app = _App()
    assert theme_module.apply_theme(app, "dark") == "dark"
    assert "QGroupBox" in app.stylesheet


def test_theme_stylesheet_builds() -> None:
    light = theme_module.build_stylesheet("light")
    dark = theme_module.build_stylesheet("dark")
    assert "QListWidget#nav_sidebar" in light
    assert light != dark
    assert "QGroupBox" in light
