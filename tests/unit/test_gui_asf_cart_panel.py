"""Tests for the GUI ASF cart import panel and scene table (Task 040).

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform so no real display is needed. The panel only calls the existing core
ASF cart parser; no network, no downloads, no SLC files are created.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_S1A = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
_S1B = "S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064DEF_5678"


def _write_cart(tmp_path: Path) -> Path:
    cart = tmp_path / "cart.txt"
    cart.write_text(
        "https://datapool.asf.alaska.edu/SLC/SA/" + _S1A + ".zip\n"
        "https://datapool.asf.alaska.edu/SLC/SB/" + _S1B + ".zip\n",
        encoding="utf-8",
    )
    return cart


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    return create_application([])


def test_parse_cart_returns_scenes(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.widgets.asf_cart_panel import AsfCartPanel

    panel = AsfCartPanel()
    panel.cart_edit.setText(str(_write_cart(tmp_path)))
    scenes = panel.parse_cart()
    assert {scene.scene_id for scene in scenes} == {_S1A, _S1B}


def test_empty_cart_path_raises_coded_error(qt_app: object) -> None:
    from insar_prep.gui.widgets.asf_cart_panel import AsfCartPanel

    panel = AsfCartPanel()
    with pytest.raises(InsarPrepError) as excinfo:
        panel.parse_cart()
    assert excinfo.value.code == ErrorCode.ASF001


def test_invalid_cart_raises_coded_error(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.widgets.asf_cart_panel import AsfCartPanel

    bad = tmp_path / "bad.txt"
    bad.write_text("https://example.com/not-a-granule\n", encoding="utf-8")
    panel = AsfCartPanel()
    panel.cart_edit.setText(str(bad))
    with pytest.raises(InsarPrepError) as excinfo:
        panel.parse_cart()
    assert excinfo.value.code == ErrorCode.ASF001


def test_scene_table_reflects_scenes(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.widgets.asf_cart_panel import AsfCartPanel
    from insar_prep.gui.widgets.scene_table import SCENE_TABLE_COLUMNS, SceneTableWidget

    panel = AsfCartPanel()
    panel.cart_edit.setText(str(_write_cart(tmp_path)))
    scenes = panel.parse_cart()

    table = SceneTableWidget()
    table.set_scenes(scenes)
    assert table.rowCount() == 2
    assert table.columnCount() == len(SCENE_TABLE_COLUMNS)
    # Scene ID is the first column; both granules must appear.
    ids = {table.item(row, 0).text() for row in range(table.rowCount())}
    assert ids == {_S1A, _S1B}


def test_main_window_import_populates_state_and_table(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")

    window.asf_cart_panel.cart_edit.setText(str(_write_cart(tmp_path)))
    window.asf_cart_panel.import_button.click()

    region = window.state.current_region()
    assert region is not None
    assert len(region.scenes) == 2
    assert window.scene_table.rowCount() == 2
    assert "Imported 2 scene" in window.status_bar_widget.status_text()


def test_main_window_import_without_region_reports_error(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")

    window.asf_cart_panel.cart_edit.setText(str(_write_cart(tmp_path)))
    window.asf_cart_panel.import_button.click()

    assert window.scene_table.rowCount() == 0
    assert "GUI002" in window.status_bar_widget.status_text()


def test_main_window_invalid_cart_reports_error(qt_app: object, tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace("C:/work")
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")

    bad = tmp_path / "bad.txt"
    bad.write_text("https://example.com/not-a-granule\n", encoding="utf-8")
    window.asf_cart_panel.cart_edit.setText(str(bad))
    window.asf_cart_panel.import_button.click()

    assert "ASF001" in window.status_bar_widget.status_text()
