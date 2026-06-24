"""Offscreen GUI tests for the DEM download panel.

Requires PySide6 (the ``gui`` extra); skipped otherwise. A fake downloader and a
monkeypatched key-status read keep this fully offline: no network, no OS keyring,
no real OpenTopography key, and no real GeoTIFF. The real download is exercised
through the synchronous ``apply_run_real_dem_download`` path (the live GUI runs
the same orchestration on a worker thread).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import Aoi, BBox
from insar_prep.providers.dem.downloader import (
    DemDownloadOutcome,
    DemDownloadRequest,
    DemDownloadResult,
)

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_DEM_PANEL_MODULE = "insar_prep.gui.widgets.dem_download_panel"
_ASF_PANEL_MODULE = "insar_prep.gui.widgets.download_panel"


@pytest.fixture(autouse=True)
def _offscreen_no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    # Both panels read a stored-credential type on construction; never touch the
    # real OS keyring in tests.
    monkeypatch.setattr(f"{_DEM_PANEL_MODULE}.stored_api_key_status", lambda: "none")
    monkeypatch.setattr(f"{_ASF_PANEL_MODULE}.stored_credential_status", lambda: "none")
    from insar_prep.gui.app import create_application

    create_application([])


def _aoi() -> Aoi:
    return Aoi(
        source=AoiSource.MANUAL_BBOX,
        role=AoiRole.PROCESSING_AOI,
        bbox=BBox(west=110.1, south=30.8, east=110.6, north=31.2),
    )


class _FakeDemDownloader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def download(self, request: DemDownloadRequest) -> DemDownloadResult:
        self.calls.append(request.demtype)
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=DemDownloadOutcome.SUCCESS,
            path=request.destination,
            bytes_written=16,
            message="ok",
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


def test_dry_run_shows_plan_and_no_download(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    out = tmp_path / "out"
    window.dem_download_panel.output_dir_edit.setText(str(out))

    plan = window.apply_plan_dem_download()
    assert plan is not None
    assert plan.dataset == "COP30"
    assert not list(out.rglob("*.tif"))
    assert "dry-run" in window.status_bar_widget.status_text().lower()


def test_real_download_with_injected_fake(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    out = tmp_path / "out"
    window.dem_download_panel.output_dir_edit.setText(str(out))

    fake = _FakeDemDownloader()
    summary = window.apply_run_real_dem_download(downloader=fake)
    assert summary is not None
    assert summary.succeeded == 1
    assert fake.calls == ["COP30"]
    assert (out / "dem_download" / "dem_download_results.csv").exists()
    assert "DEM download:" in window.status_bar_widget.status_text()
    assert "finished" in window.dem_download_panel.result_label.text().lower()


def test_dem_download_without_region_reports_gui002(tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.dem_download_panel.output_dir_edit.setText(str(tmp_path / "out"))

    assert window.apply_plan_dem_download() is None
    assert ErrorCode.GUI002.value in window.status_bar_widget.status_text()


def test_dem_download_without_aoi_reports_aoi001(tmp_path: Path) -> None:
    window = _ready_window(tmp_path, with_aoi=False)
    window.dem_download_panel.output_dir_edit.setText(str(tmp_path / "out"))

    # The region starts with a placeholder AOI (no bbox); planning must reject it.
    assert window.apply_plan_dem_download() is None
    assert ErrorCode.AOI001.value in window.status_bar_widget.status_text()


def test_dem_download_without_output_root_reports_gui003(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    assert window.apply_plan_dem_download() is None
    assert ErrorCode.GUI003.value in window.status_bar_widget.status_text()


def test_key_status_refresh_shows_status(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.dem_download_panel.refresh_key_status()
    assert "none" in window.dem_download_panel.key_status_text()
