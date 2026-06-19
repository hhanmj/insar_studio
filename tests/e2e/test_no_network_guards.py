"""No-network guards for the offline ASF paths (Task 035).

Proves that the dry-run planner CLI and the fake downloader never open a socket,
and that the guard itself actually blocks network access (a meta-check so the
other no-network assertions in the suite are meaningful).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from insar_prep.cli.main import main
from insar_prep.providers.asf.downloader import (
    DownloadOutcome,
    DownloadRequest,
    FakeAsfDownloader,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asf"
URLS_CART = FIXTURES / "urls.txt"


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_network_guard_actually_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    with pytest.raises(AssertionError):
        socket.socket()
    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 443))


def test_plan_asf_downloads_cli_opens_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        ["plan-asf-downloads", "--cart", str(URLS_CART), "--output-dir", str(tmp_path / "out")]
    )
    assert code == 0


def test_fake_downloader_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    request = DownloadRequest(
        scene_id="S1A_demo",
        expected_filename="S1A_demo.zip",
        destination=tmp_path / "02_slc" / "S1A_demo.zip",
    )
    result = FakeAsfDownloader(write_placeholder=True).download(request)
    assert result.outcome is DownloadOutcome.SUCCESS
    assert not list(tmp_path.rglob("*.zip"))
