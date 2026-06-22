"""End-to-end GUI beta workflow smoke test (Task 043).

Drives the offline GUI closed loop -- create Workspace -> Project -> Region,
set an AOI, import an ASF cart, run the scene check, build the orbit / DEM /
GACOS plans, and generate the five-file report set -- entirely through the
``MainWindow`` widget/state API on the offscreen Qt platform. It asserts the
report set is produced with no network access, no real DEM ``.tif`` files, and
no ``.zip`` / ``.SAFE`` data of any kind.

Requires PySide6 (the ``gui`` extra); skipped otherwise.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_S1A = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
_S1B = "S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064DEF_5678"
_MATCHING_ORBITS = (
    "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T000000.EOF",
    "S1B_OPER_AUX_POEORB_OPOD_20240114T120000_V20240113T000000_20240114T000000.EOF",
)
_AOI_WKT = "POLYGON ((110.1 30.8, 110.6 30.8, 110.6 31.2, 110.1 31.2, 110.1 30.8))"


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def _write_cart(tmp_path: Path) -> Path:
    cart = tmp_path / "cart.txt"
    cart.write_text(
        "https://datapool.asf.alaska.edu/SLC/SA/" + _S1A + ".zip\n"
        "https://datapool.asf.alaska.edu/SLC/SB/" + _S1B + ".zip\n",
        encoding="utf-8",
    )
    return cart


def _write_orbit_dir(tmp_path: Path) -> Path:
    orbit_dir = tmp_path / "orbits"
    orbit_dir.mkdir()
    for name in _MATCHING_ORBITS:
        (orbit_dir / name).write_text("", encoding="utf-8")
    return orbit_dir


def _assert_no_data_files(root: Path) -> None:
    assert list(root.rglob("*.tif")) == []
    assert list(root.rglob("*.zip")) == []
    assert list(root.rglob("*.SAFE")) == []


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def test_gui_beta_offline_workflow_via_widgets(
    qt_app: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from insar_prep.gui.main_window import MainWindow
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    window = MainWindow()
    _ban_network(monkeypatch)

    # Workspace -> Project -> Region.
    assert window.apply_new_workspace(str(tmp_path / "ws"), "Demo") is True
    assert window.apply_new_project("Demo Project") is True
    assert window.apply_new_region("Region One") is True

    # AOI via the bbox panel.
    window.aoi_panel.set_mode(AoiInputMode.BBOX)
    window.aoi_panel.west_edit.setText("110.1")
    window.aoi_panel.south_edit.setText("30.8")
    window.aoi_panel.east_edit.setText("110.6")
    window.aoi_panel.north_edit.setText("31.2")
    window.aoi_panel.apply_button.click()
    assert window.state.current_region().aoi.bbox is not None

    # ASF cart import.
    window.asf_cart_panel.cart_edit.setText(str(_write_cart(tmp_path)))
    window.asf_cart_panel.import_button.click()
    assert len(window.state.current_region().scenes) == 2
    assert window.scene_table.rowCount() == 2

    # Scene consistency check.
    window.scene_check_panel.run_button.click()
    assert window.last_scene_report is not None

    # Offline planning: orbit / DEM / GACOS.
    window.planning_panel.orbit_dir_edit.setText(str(_write_orbit_dir(tmp_path)))
    window.planning_panel.orbit_button.click()
    assert window.last_orbit_report is not None
    assert window.last_orbit_report.matched_scenes == 2
    window.planning_panel.dem_button.click()
    assert window.last_dem_planning_report is not None
    window.planning_panel.gacos_button.click()
    assert window.last_gacos_planning_report is not None

    # Report generation (five-file set).
    output_root = tmp_path / "out"
    window.report_panel.output_root_edit.setText(str(output_root))
    window.report_panel.generate_button.click()

    reports_dir = output_root / "region_one" / "07_reports"
    expected = [
        reports_dir / "region_one_data_preparation_report.json",
        reports_dir / "region_one_data_preparation_report.md",
        reports_dir / "region_one_data_preparation_report.html",
        reports_dir / "region_one_manifest.csv",
        reports_dir / "region_one_warnings.csv",
    ]
    for path in expected:
        assert path.is_file(), f"missing report file: {path}"
    assert "Reports generated" in window.status_bar_widget.status_text()

    # No real data was downloaded or created anywhere under the temp tree.
    _assert_no_data_files(tmp_path)


def test_gui_beta_offline_workflow_state_level(
    qt_app: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Core closed loop driven via the apply_* API (no button clicks)."""
    from insar_prep.gui.main_window import MainWindow
    from insar_prep.gui.widgets.aoi_panel import AoiInputMode

    window = MainWindow()
    _ban_network(monkeypatch)

    window.apply_new_workspace(str(tmp_path / "ws"))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")

    # AOI via WKT this time.
    window.aoi_panel.set_mode(AoiInputMode.WKT)
    window.aoi_panel.wkt_edit.setPlainText(_AOI_WKT)
    assert window.apply_set_region_aoi(window.aoi_panel.build_aoi()) is True

    window.asf_cart_panel.cart_edit.setText(str(_write_cart(tmp_path)))
    assert window.apply_import_scenes(window.asf_cart_panel.parse_cart()) is True

    assert window.apply_run_scene_check() is not None
    window.planning_panel.orbit_dir_edit.setText(str(_write_orbit_dir(tmp_path)))
    assert window.apply_run_orbit_match() is not None
    assert window.apply_run_dem_plan() is not None
    assert window.apply_run_gacos_plan() is not None

    window.report_panel.output_root_edit.setText(str(tmp_path / "out"))
    result = window.apply_generate_reports()
    assert result is not None
    report, paths = result
    assert len(paths) == 5
    assert all(path.is_file() for path in paths)

    section_titles = {section.title for section in report.sections}
    assert {"Scene consistency", "Orbit matching", "DEM planning", "GACOS request planning"} <= (
        section_titles
    )
    _assert_no_data_files(tmp_path)
