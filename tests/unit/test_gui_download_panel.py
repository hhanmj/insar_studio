"""Offscreen GUI tests for the ASF SLC download panel.

Requires PySide6 (the ``gui`` extra); skipped otherwise. A fake downloader +
resolver and a monkeypatched credential-status read keep this fully offline: no
network, no OS keyring, no real Earthdata account, and no real SLC archive. The
real download is exercised through the synchronous ``apply_run_real_download``
path (the live GUI runs the same orchestration on a worker thread).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import Scene
from insar_prep.providers.asf.credentials import CredentialSource, ResolvedCredential
from insar_prep.providers.asf.downloader import (
    DownloadOutcome,
    DownloadRequest,
    DownloadResult,
)

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_PANEL_MODULE = "insar_prep.gui.widgets.download_panel"
_URL = "https://datapool.asf.alaska.edu/SLC/x.zip"


@pytest.fixture(autouse=True)
def _offscreen_no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    # The panel reads the stored-credential type on construction; never touch the
    # real OS keyring in tests.
    monkeypatch.setattr(f"{_PANEL_MODULE}.stored_credential_status", lambda: "none")
    from insar_prep.gui.app import create_application

    create_application([])


def _scene(scene_id: str, *, url: str | None = _URL) -> Scene:
    return Scene(scene_id=scene_id, url=url)


class _FakeDownloader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def download(self, request: DownloadRequest) -> DownloadResult:
        self.calls.append(request.scene_id)
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=DownloadOutcome.SUCCESS,
            path=request.destination,
            bytes_written=8,
            message="ok",
        )


def _fake_resolver(source: CredentialSource) -> ResolvedCredential:
    return ResolvedCredential(source=source, use_netrc=True)


def _ready_window(tmp_path: Path):
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    window.state.set_current_region_scenes([_scene("a"), _scene("b")])
    return window


def test_dry_run_writes_plan_and_no_download(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    out = tmp_path / "out"
    window.download_panel.output_dir_edit.setText(str(out))

    plan = window.apply_plan_downloads()
    assert plan is not None
    assert (out / "asf_download_plan" / "asf_download_plan.json").exists()
    assert (out / "asf_download_plan" / "asf_download_plan.csv").exists()
    assert not list(out.rglob("*.zip"))
    assert "dry-run" in window.status_bar_widget.status_text().lower()


def test_real_download_with_injected_fake(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    out = tmp_path / "out"
    window.download_panel.output_dir_edit.setText(str(out))

    fake = _FakeDownloader()
    summary = window.apply_run_real_download(downloader=fake, resolver=_fake_resolver)
    assert summary is not None
    assert summary.succeeded == 2
    assert fake.calls == ["a", "b"]
    assert (out / "asf_download_plan" / "asf_download_results.csv").exists()
    assert "Download:" in window.status_bar_widget.status_text()
    assert "finished" in window.download_panel.result_label.text().lower()


def test_download_without_region_reports_gui002(tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.download_panel.output_dir_edit.setText(str(tmp_path / "out"))

    assert window.apply_plan_downloads() is None
    assert ErrorCode.GUI002.value in window.status_bar_widget.status_text()


def test_real_download_without_scenes_reports_gui002(tmp_path: Path) -> None:
    from insar_prep.gui.main_window import MainWindow

    window = MainWindow()
    window.apply_new_workspace(str(tmp_path))
    window.apply_new_project("Demo Project")
    window.apply_new_region("Region One")
    window.download_panel.output_dir_edit.setText(str(tmp_path / "out"))

    result = window.apply_run_real_download(downloader=_FakeDownloader(), resolver=_fake_resolver)
    assert result is None
    assert ErrorCode.GUI002.value in window.status_bar_widget.status_text()


def test_download_without_output_root_reports_gui003(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    # No output root entered.
    assert window.apply_plan_downloads() is None
    assert ErrorCode.GUI003.value in window.status_bar_widget.status_text()


def test_credential_status_refresh_shows_type(tmp_path: Path) -> None:
    window = _ready_window(tmp_path)
    window.download_panel.refresh_credential_status()
    assert "none" in window.download_panel.credential_status_text()
