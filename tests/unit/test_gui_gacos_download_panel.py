"""Offscreen GUI tests for the GACOS download panel and language switching.

Requires PySide6 (the ``gui`` extra); skipped otherwise. A fake GACOS client and
monkeypatched email-status reads keep this fully offline: no network, no OS
keyring, no real GACOS account.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep import i18n
from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import Aoi, BBox
from insar_prep.providers.gacos.downloader import FakeGacosClient, GacosFetchOutcome

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_GACOS_PANEL = "insar_prep.gui.widgets.gacos_download_panel"
_DEM_PANEL = "insar_prep.gui.widgets.dem_download_panel"
_ASF_PANEL = "insar_prep.gui.widgets.download_panel"


@pytest.fixture(autouse=True)
def _offscreen_no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(f"{_GACOS_PANEL}.stored_gacos_email_status", lambda: "none")
    monkeypatch.setattr(f"{_DEM_PANEL}.stored_api_key_status", lambda: "none")
    monkeypatch.setattr(f"{_ASF_PANEL}.stored_credential_status", lambda: "none")
    # Never write the real per-user settings file when switching language.
    monkeypatch.setattr(i18n, "save_language", lambda code, **kw: None)
    i18n.set_language("en")
    from insar_prep.gui.app import create_application

    create_application([])
    yield
    i18n.set_language("en")


def _aoi() -> Aoi:
    return Aoi(
        source=AoiSource.MANUAL_BBOX,
        role=AoiRole.PROCESSING_AOI,
        bbox=BBox(west=110.1, south=30.8, east=110.6, north=31.2),
    )


def _ready_window(tmp_path: Path, *, with_aoi: bool = True):
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    if with_aoi:
        window.state.set_current_region_aoi(_aoi())
    return window


def test_panel_parses_dates_and_urls() -> None:
    from insar_prep.gui.widgets.gacos_download_panel import GacosDownloadPanel

    panel = GacosDownloadPanel()
    panel.dates_text.setPlainText("20240101\n20240113, 20240125")
    assert len(panel.manual_dates()) == 3
    panel.url_text.setPlainText("http://x/a.zip\nhttp://x/b.zip\n")
    assert panel.result_urls() == ["http://x/a.zip", "http://x/b.zip"]
    panel.time_edit.setText("18:30")
    assert panel.selected_time() == (18, 30)


def test_submit_with_injected_fake(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.gacos_download_panel.output_dir_edit.setText(str(tmp_path / "out"))
    window.gacos_download_panel.dates_text.setPlainText("20240101\n20240113")

    summary = window.apply_run_gacos_request(client=FakeGacosClient())
    assert summary is not None
    assert summary.submitted == 1
    assert (tmp_path / "out" / "gacos_request" / "gacos_request_results.csv").exists()
    assert "GACOS request" in window.status_bar_widget.status_text()


def test_submit_without_aoi_reports_aoi001(tmp_path: Path) -> None:
    window = _ready_window(tmp_path, with_aoi=False)
    window.gacos_download_panel.output_dir_edit.setText(str(tmp_path / "out"))
    window.gacos_download_panel.dates_text.setPlainText("20240101")
    assert window.apply_run_gacos_request(client=FakeGacosClient()) is None
    assert ErrorCode.AOI001.value in window.status_bar_widget.status_text()


def test_submit_without_output_root_reports_gui003(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.gacos_download_panel.dates_text.setPlainText("20240101")
    assert window.apply_run_gacos_request(client=FakeGacosClient()) is None
    assert ErrorCode.GUI003.value in window.status_bar_widget.status_text()


def test_download_with_injected_fake(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.gacos_download_panel.output_dir_edit.setText(str(tmp_path / "out"))
    window.gacos_download_panel.url_text.setPlainText("http://www.gacos.net/data/demo.zip")

    summary = window.apply_run_gacos_download(client=FakeGacosClient(write_placeholder=True))
    assert summary is not None
    assert summary.fetch_results
    assert summary.fetch_results[0].outcome is GacosFetchOutcome.SUCCESS
    assert "GACOS download" in window.status_bar_widget.status_text()


def test_download_without_urls_reports_gac004(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.gacos_download_panel.output_dir_edit.setText(str(tmp_path / "out"))
    assert window.apply_run_gacos_download(client=FakeGacosClient()) is None
    assert ErrorCode.GAC004.value in window.status_bar_widget.status_text()


def test_email_status_refresh(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.gacos_download_panel.refresh_email_status()
    assert "none" in window.gacos_download_panel.email_status_text()


def test_language_switch_retranslates_ui(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    assert window.gacos_download_panel.title() == "GACOS Download"
    window._on_change_language("zh")
    assert i18n.get_language() == "zh"
    assert window.gacos_download_panel.title() == "GACOS 下载"
    assert window.aoi_panel.title() == "研究范围（AOI）"
    assert window.new_workspace_action.text() == "新建工作区"
    window._on_change_language("en")
    assert window.gacos_download_panel.title() == "GACOS Download"
