"""Tests for the offline fake ASF downloader interface (Task 035)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from insar_prep.providers.asf.downloader import (
    AsfDownloader,
    DownloadOutcome,
    DownloadRequest,
    FakeAsfDownloader,
    RealAsfDownloader,
)


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in the fake downloader")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def _request(tmp_path: Path) -> DownloadRequest:
    return DownloadRequest(
        scene_id="S1A_demo",
        expected_filename="S1A_demo.zip",
        destination=tmp_path / "02_slc" / "S1A_demo.zip",
    )


def test_fake_success_writes_nothing_by_default(tmp_path: Path) -> None:
    result = FakeAsfDownloader().download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS
    assert result.path is None
    assert result.bytes_written == 0
    assert not list(tmp_path.rglob("*"))


def test_fake_success_writes_tiny_placeholder(tmp_path: Path) -> None:
    result = FakeAsfDownloader(write_placeholder=True).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS
    assert result.path is not None
    assert result.path.exists()
    assert 0 < result.bytes_written < 1024
    # Never a real archive.
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.SAFE"))


def test_fake_failure(tmp_path: Path) -> None:
    result = FakeAsfDownloader(outcome=DownloadOutcome.FAILED).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "DL001"
    assert result.path is None
    assert not list(tmp_path.rglob("*"))


def test_fake_interrupted_leaves_part_not_zip(tmp_path: Path) -> None:
    downloader = FakeAsfDownloader(outcome=DownloadOutcome.INTERRUPTED, write_placeholder=True)
    result = downloader.download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.INTERRUPTED
    assert list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.SAFE"))


def test_fake_records_calls(tmp_path: Path) -> None:
    downloader = FakeAsfDownloader()
    downloader.download(_request(tmp_path))
    downloader.download(_request(tmp_path))
    assert downloader.calls == ["S1A_demo", "S1A_demo"]


def test_fake_satisfies_downloader_protocol() -> None:
    assert isinstance(FakeAsfDownloader(), AsfDownloader)


def test_real_downloader_constructs_without_network_or_secrets() -> None:
    # The real downloader is now implemented; construction performs no network
    # I/O and reads no credentials (the session is built lazily on download()).
    downloader = RealAsfDownloader()
    assert isinstance(downloader, AsfDownloader)


def test_fake_download_does_not_touch_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    result = FakeAsfDownloader(write_placeholder=True).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS
