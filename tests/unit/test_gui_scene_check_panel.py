"""Tests for the GUI scene consistency check panel (Task 041).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. The panel only calls the existing core
``check_scene_collection``; no network, no downloads.
"""

from __future__ import annotations

import importlib.util

import pytest

from insar_prep.core.enums import Platform, Polarization
from insar_prep.core.models import Scene

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")


def _scene(
    scene_id: str,
    *,
    platform: Platform = Platform.S1A,
    polarization: Polarization = Polarization.VV,
    url: str | None = "https://datapool.asf.alaska.edu/SLC/x.zip",
) -> Scene:
    return Scene(scene_id=scene_id, platform=platform, polarization=polarization, url=url)


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def test_run_check_reports_totals(qt_app: object) -> None:
    from insar_prep.gui.widgets.scene_check_panel import SceneCheckPanel

    panel = SceneCheckPanel()
    report = panel.run_check([_scene("a"), _scene("b")])
    assert report.total_scenes == 2
    assert panel.total_label.text() == "Total scenes: 2"


def test_run_check_empty_is_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.scene_check_panel import SceneCheckPanel

    panel = SceneCheckPanel()
    report = panel.run_check([])
    assert report.has_errors is True
    assert panel.errors_label.text() == "Errors: 1"
    assert panel.issues_list.count() == 1


def test_platform_mix_is_warning(qt_app: object) -> None:
    from insar_prep.gui.widgets.scene_check_panel import SceneCheckPanel

    panel = SceneCheckPanel()
    report = panel.run_check(
        [_scene("a", platform=Platform.S1A), _scene("b", platform=Platform.S1B)]
    )
    assert report.has_warnings is True
    assert report.has_errors is False
    assert "Warnings: 1" in panel.warnings_label.text()


def test_expected_polarization_mismatch_is_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.scene_check_panel import SceneCheckPanel

    panel = SceneCheckPanel()
    # Select an expected polarization the VV scenes do not match.
    index = panel.polarization_combo.findData(Polarization.HH.value)
    panel.polarization_combo.setCurrentIndex(index)
    assert panel.expected_polarization() is Polarization.HH

    report = panel.run_check([_scene("a"), _scene("b")])
    assert report.has_errors is True


def test_main_window_scene_check_without_region_reports_gui002(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")

    assert window.apply_run_scene_check() is None
    assert "GUI002" in window.status_bar_widget.status_text()


def test_main_window_scene_check_warning_updates_status(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    window.state.set_current_region_scenes(
        [_scene("a", platform=Platform.S1A), _scene("b", platform=Platform.S1B)]
    )

    report = window.apply_run_scene_check()
    assert report is not None and report.has_warnings
    assert "warning(s)" in window.status_bar_widget.status_text()


def test_main_window_scene_check_ready_when_clean(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    window.state.set_current_region_scenes([_scene("a")])

    report = window.apply_run_scene_check()
    assert report is not None
    assert report.has_errors is False and report.has_warnings is False
    assert window.status_bar_widget.status_text() == "Ready"


def test_main_window_scene_check_error_updates_status(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    # Region selected but no scenes imported -> SCENE_EMPTY error report.
    report = window.apply_run_scene_check()
    assert report is not None and report.has_errors
    assert "error(s)" in window.status_bar_widget.status_text()
