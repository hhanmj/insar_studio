"""Tests for the GUI report generation panel (Task 043).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. The panel only calls the existing core
reporting backend; no SLC/DEM/GACOS data is downloaded or created, and there is
no network access.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import Scene

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")


def _scene(scene_id: str = "scene_a") -> Scene:
    return Scene(scene_id=scene_id, url="https://datapool.asf.alaska.edu/SLC/x.zip")


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def _ready_window(tmp_path: Path):
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    window.state.set_current_region_scenes([_scene()])
    return window


def test_generate_writes_five_file_report_set(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    output_root = tmp_path / "out"
    window.report_panel.output_root_edit.setText(str(output_root))

    result = window.apply_generate_reports()
    assert result is not None
    report, paths = result
    assert len(paths) == 5
    suffixes = sorted(p.name.split("region_one")[-1] for p in paths)
    assert suffixes == sorted(
        [
            "_data_preparation_report.json",
            "_data_preparation_report.md",
            "_data_preparation_report.html",
            "_manifest.csv",
            "_warnings.csv",
        ]
    )
    for path in paths:
        assert path.is_file()
    # Planned/offline only: no data files of any kind were created.
    assert list(output_root.rglob("*.tif")) == []
    assert list(output_root.rglob("*.zip")) == []
    assert list(output_root.rglob("*.SAFE")) == []


def test_generate_updates_status_and_paths_view(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.report_panel.output_root_edit.setText(str(tmp_path / "out"))

    window.report_panel.generate_button.click()

    assert "Reports generated" in window.status_bar_widget.status_text()
    assert "07_reports" in window.report_panel.paths_view.toPlainText()
    assert "files" in window.report_panel.result_label.text()


def test_generate_without_region_reports_gui002(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.report_panel.output_root_edit.setText(str(tmp_path / "out"))

    assert window.apply_generate_reports() is None
    assert ErrorCode.GUI002.value in window.status_bar_widget.status_text()


def test_generate_without_output_root_reports_gui003(qt_app: object, tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    # No output root entered.
    assert window.apply_generate_reports() is None
    assert ErrorCode.GUI003.value in window.status_bar_widget.status_text()


def test_generate_includes_planning_reports_when_present(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.processing.aoi import make_processing_aoi_from_bbox

    window = _ready_window(tmp_path)
    window.state.set_current_region_aoi(make_processing_aoi_from_bbox(110.0, 111.0, 30.0, 31.0))
    # Run scene check + DEM plan so they are consolidated into the report.
    window.apply_run_scene_check()
    window.apply_run_dem_plan()

    window.report_panel.output_root_edit.setText(str(tmp_path / "out"))
    result = window.apply_generate_reports()
    assert result is not None
    report, _paths = result
    section_titles = {section.title for section in report.sections}
    assert "Scene consistency" in section_titles
    assert "DEM planning" in section_titles
