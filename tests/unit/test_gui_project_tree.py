"""Tests for the GUI project tree and main-window actions (Task 038).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. No network, no disk persistence.
"""

from __future__ import annotations

import importlib.util

import pytest

from insar_prep.gui.state import GuiState

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def test_tree_shows_placeholder_when_empty(qt_app: object) -> None:
    from insar_prep.gui.widgets.project_tree import ProjectTreeWidget

    tree = ProjectTreeWidget()
    tree.refresh_from_state(GuiState())
    assert tree.topLevelItemCount() == 1
    assert tree.topLevelItem(0).text(0) == "Workspace"


def test_tree_reflects_state(qt_app: object) -> None:
    from insar_prep.gui.widgets.project_tree import ProjectTreeWidget

    state = GuiState()
    state.create_workspace("C:/work", name="My Area")
    state.add_project("Demo Project")
    state.add_region("Region One")

    tree = ProjectTreeWidget()
    tree.refresh_from_state(state)

    assert tree.topLevelItemCount() == 1
    workspace_item = tree.topLevelItem(0)
    assert workspace_item.text(0) == "My Area"
    assert workspace_item.childCount() == 1
    project_item = workspace_item.child(0)
    assert project_item.text(0) == "Demo Project"
    assert project_item.childCount() == 1
    assert project_item.child(0).text(0) == "Region One"


def test_main_window_apply_methods(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    assert window.apply_new_workspace("C:/work", "My Area") is True
    assert window.apply_new_project("Demo Project") is True
    assert window.apply_new_region("Region One") is True
    assert window.project_tree.topLevelItem(0).text(0) == "My Area"
    assert "Created region" in window.status_bar_widget.status_text()


def test_main_window_reports_precondition_error(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    # No workspace yet: creating a project must fail and surface GUI002.
    assert window.apply_new_project("Demo") is False
    assert "GUI002" in window.status_bar_widget.status_text()
