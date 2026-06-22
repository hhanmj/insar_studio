"""Tests for the GUI AOI input panel (Task 039).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. The panel only calls existing core AOI
interfaces; no network, no disk persistence, no coordinate transforms.
"""

from __future__ import annotations

import importlib.util

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def _make_panel(mode):
    from insar_prep.gui.widgets.aoi_panel import AoiPanel

    panel = AoiPanel()
    panel.set_mode(mode)
    return panel


def test_bbox_input_builds_aoi(qt_app: object) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    panel = _make_panel(AoiInputMode.BBOX)
    panel.west_edit.setText("110.0")
    panel.south_edit.setText("30.0")
    panel.east_edit.setText("111.0")
    panel.north_edit.setText("31.0")

    aoi = panel.build_aoi()
    assert aoi.bbox is not None
    assert aoi.bbox.west == 110.0
    assert aoi.bbox.north == 31.0


def test_wkt_input_builds_aoi(qt_app: object) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    panel = _make_panel(AoiInputMode.WKT)
    panel.wkt_edit.setPlainText("POLYGON ((110 30, 111 30, 111 31, 110 31, 110 30))")

    aoi = panel.build_aoi()
    assert aoi.bbox is not None
    assert aoi.bbox.east == 111.0


def test_geojson_input_builds_aoi(qt_app: object, tmp_path) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    geojson = tmp_path / "aoi.geojson"
    geojson.write_text(
        '{"type": "Polygon", "coordinates": '
        "[[[110, 30], [111, 30], [111, 31], [110, 31], [110, 30]]]}",
        encoding="utf-8",
    )
    panel = _make_panel(AoiInputMode.GEOJSON)
    panel.geojson_edit.setText(str(geojson))

    aoi = panel.build_aoi()
    assert aoi.bbox is not None
    assert aoi.bbox.south == 30.0


def test_invalid_bbox_raises_coded_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    panel = _make_panel(AoiInputMode.BBOX)
    panel.west_edit.setText("not-a-number")
    panel.south_edit.setText("30.0")
    panel.east_edit.setText("111.0")
    panel.north_edit.setText("31.0")

    with pytest.raises(InsarPrepError) as excinfo:
        panel.build_aoi()
    assert excinfo.value.code == ErrorCode.AOI001


def test_reversed_bbox_raises_coded_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    panel = _make_panel(AoiInputMode.BBOX)
    panel.west_edit.setText("111.0")
    panel.south_edit.setText("30.0")
    panel.east_edit.setText("110.0")  # east < west is rejected by BBox
    panel.north_edit.setText("31.0")

    with pytest.raises(InsarPrepError) as excinfo:
        panel.build_aoi()
    assert excinfo.value.code == ErrorCode.AOI001


def test_invalid_wkt_raises_coded_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    panel = _make_panel(AoiInputMode.WKT)
    panel.wkt_edit.setPlainText("not valid wkt")

    with pytest.raises(InsarPrepError) as excinfo:
        panel.build_aoi()
    assert excinfo.value.code == ErrorCode.AOI001


def test_main_window_sets_aoi_on_current_region(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    window = MainWindow()
    window.apply_new_workspace("C:/work", "My Area")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")

    window.aoi_panel.set_mode(AoiInputMode.BBOX)
    window.aoi_panel.west_edit.setText("110.0")
    window.aoi_panel.south_edit.setText("30.0")
    window.aoi_panel.east_edit.setText("111.0")
    window.aoi_panel.north_edit.setText("31.0")
    window.aoi_panel.apply_button.click()

    region = window.state.current_region()
    assert region is not None
    assert region.aoi.bbox is not None
    workspace_item = window.project_tree.topLevelItem(0)
    assert "[AOI set]" in workspace_item.child(0).child(0).text(0)


def test_main_window_set_aoi_without_region_reports_error(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")

    window.aoi_panel.set_mode(AoiInputMode.BBOX)
    window.aoi_panel.west_edit.setText("110.0")
    window.aoi_panel.south_edit.setText("30.0")
    window.aoi_panel.east_edit.setText("111.0")
    window.aoi_panel.north_edit.setText("31.0")
    window.aoi_panel.apply_button.click()

    assert "GUI002" in window.status_bar_widget.status_text()


def test_panel_invalid_input_reports_error_via_status_bar(qt_app: object) -> None:
    from insar_prep.gui.main_window import MainWindow
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")

    window.aoi_panel.set_mode(AoiInputMode.WKT)
    window.aoi_panel.wkt_edit.setPlainText("")  # empty WKT is invalid
    window.aoi_panel.apply_button.click()

    assert "AOI001" in window.status_bar_widget.status_text()
