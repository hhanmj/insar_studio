"""Offline tests for the shared ASF download orchestration (``run_asf_download``).

No network and no real Earthdata account: a fake downloader and a fake resolver
are injected so the success / failure / cancel / no-scenes paths run
deterministically. The credential-safe results CSV is verified too.
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path

import pytest

from insar_prep.core.exceptions import CredentialError, InsarPrepError
from insar_prep.core.models import Scene
from insar_prep.providers.asf.credentials import CredentialSource
from insar_prep.providers.asf.download_runner import (
    run_asf_download,
    write_download_results_csv,
)
from insar_prep.providers.asf.downloader import (
    DownloadOutcome,
    DownloadRequest,
    DownloadResult,
)

_URL = "https://datapool.asf.alaska.edu/SLC/x.zip"


def _scene(scene_id: str, *, url: str | None = _URL) -> Scene:
    return Scene(scene_id=scene_id, url=url)


class _FakeDownloader:
    """Records calls and returns a fixed outcome; never touches the network."""

    def __init__(self, *, outcome: DownloadOutcome = DownloadOutcome.SUCCESS) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def download(self, request: DownloadRequest) -> DownloadResult:
        self.calls.append(request.scene_id)
        success = self.outcome is DownloadOutcome.SUCCESS
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=self.outcome,
            path=request.destination if success else None,
            bytes_written=8 if success else 0,
            message="ok" if success else "failed",
            error_code=None if success else "DL005",
        )


def test_success_writes_masked_results_csv(tmp_path: Path) -> None:
    fake = _FakeDownloader()
    progress: list[DownloadResult] = []
    summary = run_asf_download(
        [_scene("a"), _scene("b")], tmp_path, downloader=fake, progress=progress.append
    )

    assert fake.calls == ["a", "b"]
    assert summary.total == 2
    assert summary.succeeded == 2
    assert not summary.has_failures
    assert summary.cancelled is False
    assert len(progress) == 2

    results_csv = tmp_path / "asf_download_plan" / "asf_download_results.csv"
    assert summary.results_path == results_csv
    with results_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["scene_id"] for row in rows] == ["a", "b"]
    assert all(row["outcome"] == "success" for row in rows)
    # The fake never writes a real archive.
    assert not list(tmp_path.rglob("*.zip"))


def test_failure_is_counted_not_raised(tmp_path: Path) -> None:
    summary = run_asf_download(
        [_scene("a")], tmp_path, downloader=_FakeDownloader(outcome=DownloadOutcome.FAILED)
    )
    assert summary.failed == 1
    assert summary.has_failures


def test_no_scenes_with_url_raises(tmp_path: Path) -> None:
    with pytest.raises(InsarPrepError):
        run_asf_download([_scene("a", url=None)], tmp_path, downloader=_FakeDownloader())


def test_resolver_invoked_only_when_no_downloader(tmp_path: Path) -> None:
    seen: list[CredentialSource] = []

    def _resolver(source: CredentialSource):
        seen.append(source)
        # Stop before any real (network) download is attempted.
        raise CredentialError("no credentials configured")

    with pytest.raises(CredentialError):
        run_asf_download(
            [_scene("a")],
            tmp_path,
            credential_source=CredentialSource.KEYRING,
            resolver=_resolver,
        )
    assert seen == [CredentialSource.KEYRING]


def test_cancel_before_start_downloads_nothing(tmp_path: Path) -> None:
    fake = _FakeDownloader()
    cancel = threading.Event()
    cancel.set()
    summary = run_asf_download([_scene("a")], tmp_path, downloader=fake, cancel_event=cancel)
    assert fake.calls == []
    assert summary.total == 0
    assert summary.cancelled is True
    assert summary.results_path is None


def test_write_results_csv_has_fixed_header(tmp_path: Path) -> None:
    results = [
        DownloadResult(
            scene_id="s1", outcome=DownloadOutcome.SUCCESS, bytes_written=10, message="ok"
        )
    ]
    path = write_download_results_csv(tmp_path, results)
    with path.open(encoding="utf-8", newline="") as handle:
        header = handle.readline().strip()
    assert header == "scene_id,outcome,bytes_written,error_code,message"
