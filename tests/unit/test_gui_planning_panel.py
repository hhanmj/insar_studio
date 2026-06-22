"""Tests for the GUI offline planning panel (orbit / DEM / GACOS, Task 042).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. The panel only calls existing core
planners/matchers/import-checkers: nothing is downloaded, no DEM ``.tif`` is
created, no real vertical-datum conversion is performed, and there is no network.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from insar_prep.core.enums import Platform
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_ORBIT_EOF = "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T000000.EOF"


def _scene(scene_id: str = "scene_a", *, platform: Platform = Platform.S1A) -> Scene:
    return Scene(
        scene_id=scene_id,
        platform=platform,
        acquisition_datetime=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
        url="https://datapool.asf.alaska.edu/SLC/x.zip",
    )


def _write_orbit_dir(tmp_path: Path) -> Path:
    orbit_dir = tmp_path / "orbits"
    orbit_dir.mkdir()
    (orbit_dir / _ORBIT_EOF).write_text("", encoding="utf-8")
    return orbit_dir


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def _ready_window(tmp_path: Path, *, with_aoi: bool = True, with_scenes: bool = True):
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    if with_aoi:
        window.state.set_current_region_aoi(make_processing_aoi_from_bbox(110.0, 111.0, 30.0, 31.0))
    if with_scenes:
        window.state.set_current_region_scenes([_scene()])
    return window


def test_orbit_match_with_local_fixture(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.planning_panel.orbit_dir_edit.setText(str(_write_orbit_dir(tmp_path)))

    report = window.apply_run_orbit_match()
    assert report is not None
    assert report.matched_scenes == 1
    assert report.total_scenes == 1
    assert "1/1" in window.status_bar_widget.status_text()


def test_orbit_match_without_scenes_errors(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path, with_scenes=False)
    window.planning_panel.orbit_dir_edit.setText(str(_write_orbit_dir(tmp_path)))

    assert window.apply_run_orbit_match() is None
    assert "GUI002" in window.status_bar_widget.status_text()


def test_orbit_match_without_dir_errors(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    # No orbit directory entered.
    assert window.apply_run_orbit_match() is None
    assert "ORB001" in window.status_bar_widget.status_text()


def test_dem_plan_builds_paths_without_creating_tif(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)

    reports = window.apply_run_dem_plan()
    assert reports is not None
    planning_report, conversion_report = reports
    assert planning_report.plan is not None
    # Planned only: the SARscape-ready path is computed but never created.
    assert str(planning_report.plan.sarscape_ready_dem_path).endswith("_dem.tif")
    assert list(tmp_path.rglob("*.tif")) == []
    assert "PLANNED ONLY" in window.planning_panel.dem_result_label.text()
    assert "planned only" in window.status_bar_widget.status_text()


def test_dem_plan_without_aoi_errors(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path, with_aoi=False)
    assert window.apply_run_dem_plan() is None
    assert "AOI001" in window.status_bar_widget.status_text()


def test_gacos_plan_generates_dates(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)

    reports = window.apply_run_gacos_plan()
    assert reports is not None
    planning_report, import_report = reports
    assert planning_report.plan is not None
    assert len(planning_report.plan.unique_dates) == 1
    assert import_report is None
    assert "planned only" in window.status_bar_widget.status_text()


def test_gacos_plan_without_scenes_errors(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path, with_scenes=False)
    assert window.apply_run_gacos_plan() is None
    assert "GAC001" in window.status_bar_widget.status_text()


def test_gacos_import_check_uses_local_dir(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    product_dir = tmp_path / "gacos_products"
    product_dir.mkdir()
    window.planning_panel.gacos_import_dir_edit.setText(str(product_dir))

    reports = window.apply_run_gacos_plan()
    assert reports is not None
    _planning_report, import_report = reports
    assert import_report is not None
    # The empty directory has none of the expected dates.
    assert len(import_report.missing_dates) == 1


def test_planning_without_region_reports_gui002(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")

    assert window.apply_run_dem_plan() is None
    assert window.apply_run_gacos_plan() is None
    assert window.apply_run_orbit_match() is None
    assert ErrorCode.GUI002.value in window.status_bar_widget.status_text()
