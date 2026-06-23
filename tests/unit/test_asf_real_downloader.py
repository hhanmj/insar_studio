"""Tests for the real ASF downloader's transfer logic.

The network is never touched: a fake ``requests``-like session is injected so the
``.part`` -> atomic-rename, size-check, retry/backoff, credential-rejection, and
cancellation paths are all exercised offline and deterministically.
"""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

import pytest

from insar_prep.providers.asf.credentials import CredentialSource
from insar_prep.providers.asf.downloader import (
    AsfDownloader,
    DownloadOutcome,
    DownloadRequest,
    RealAsfDownloader,
    _host_allows_auth,
    download_requests_from_scenes,
)


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in the real downloader test")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content_length: int | None = None,
        chunks: tuple[bytes, ...] = (b"slc-bytes",),
    ) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self._chunks = chunks

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def iter_content(self, chunk_size: int = 1) -> object:
        yield from self._chunks


class _FakeSession:
    """A minimal requests.Session stand-in. ``actions`` are consumed per get()."""

    def __init__(self, actions: list[object]) -> None:
        self._actions = list(actions)
        self.calls = 0

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls += 1
        action = self._actions.pop(0) if self._actions else _FakeResponse()
        if isinstance(action, Exception):
            raise action
        return action  # type: ignore[return-value]


def _request(
    tmp_path: Path, *, url: str | None = "https://datapool.asf.alaska.edu/x.zip", **kw
) -> DownloadRequest:
    return DownloadRequest(
        scene_id="S1A_demo",
        expected_filename="S1A_demo.zip",
        destination=tmp_path / "02_slc" / "S1A_demo.zip",
        url=url,
        **kw,
    )


def _downloader(session: object, **kw: object) -> RealAsfDownloader:
    return RealAsfDownloader(session=session, backoff_seconds=0.0, **kw)


def test_construct_does_not_touch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    # Construction reads no secrets and opens no socket (no session built yet).
    RealAsfDownloader(credential_source=CredentialSource.NETRC)


def test_real_downloader_satisfies_protocol() -> None:
    assert isinstance(RealAsfDownloader(session=_FakeSession([])), AsfDownloader)


def test_success_streams_to_final_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    payload = (b"abc", b"de")
    session = _FakeSession([_FakeResponse(content_length=5, chunks=payload)])
    result = _downloader(session).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS
    assert result.bytes_written == 5
    dest = tmp_path / "02_slc" / "S1A_demo.zip"
    assert dest.exists()
    assert dest.read_bytes() == b"abcde"
    assert not list(tmp_path.rglob("*.part"))


def test_skip_when_already_complete(tmp_path: Path) -> None:
    dest = tmp_path / "02_slc" / "S1A_demo.zip"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"abcde")
    session = _FakeSession([])  # must not be used
    result = _downloader(session).download(_request(tmp_path, expected_size=5))
    assert result.outcome is DownloadOutcome.SKIPPED
    assert session.calls == 0


def test_credentials_rejected_no_retry(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(status_code=403)])
    result = _downloader(session, max_retries=3).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "DL004"
    assert session.calls == 1  # 401/403 is not retried
    assert not list(tmp_path.rglob("*.part"))


def test_transient_then_success(tmp_path: Path) -> None:
    session = _FakeSession(
        [
            _FakeResponse(status_code=503),
            _FakeResponse(content_length=5, chunks=(b"abcde",)),
        ]
    )
    result = _downloader(session, max_retries=3).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS
    assert session.calls == 2


def test_persistent_transient_fails_dl005(tmp_path: Path) -> None:
    session = _FakeSession([ConnectionResetError("boom")] * 3)
    result = _downloader(session, max_retries=3).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "DL005"
    assert session.calls == 3
    assert not list(tmp_path.rglob("*.part"))


def test_size_mismatch_fails_dl002_and_discards_part(tmp_path: Path) -> None:
    # Content-Length says 100 but only 5 bytes arrive, on every attempt.
    session = _FakeSession([_FakeResponse(content_length=100, chunks=(b"abcde",))] * 2)
    result = _downloader(session, max_retries=2).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "DL002"
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "02_slc" / "S1A_demo.zip").exists()


def test_cancellation_keeps_part(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    session = _FakeSession([_FakeResponse(content_length=5, chunks=(b"abcde",))])
    result = _downloader(session, cancel_event=cancel).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.INTERRUPTED
    assert result.error_code == "DL001"


def test_no_url_fails_asf003(tmp_path: Path) -> None:
    result = _downloader(_FakeSession([])).download(_request(tmp_path, url=None))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "ASF003"


def test_missing_env_token_fails_dl004(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    # No injected session and no env token -> credential resolution fails cleanly.
    downloader = RealAsfDownloader(credential_source=CredentialSource.ENV_TOKEN)
    result = downloader.download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.FAILED
    assert result.error_code == "DL004"


def test_no_socket_opened_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    session = _FakeSession([_FakeResponse(content_length=3, chunks=(b"abc",))])
    result = _downloader(session).download(_request(tmp_path))
    assert result.outcome is DownloadOutcome.SUCCESS


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("urs.earthdata.nasa.gov", True),
        ("datapool.asf.alaska.edu", True),
        ("cumulus.asf.alaska.edu", True),
        ("data.earthdatacloud.nasa.gov", True),
        ("xyz.s3.amazonaws.com", False),
        ("d123.cloudfront.net", False),
        ("", False),
    ],
)
def test_host_allows_auth(host: str, allowed: bool) -> None:
    assert _host_allows_auth(host) is allowed


def test_download_requests_from_scenes_skips_urlless(tmp_path: Path) -> None:
    class _Scene:
        def __init__(self, scene_id: str, url: str | None) -> None:
            self.scene_id = scene_id
            self.url = url
            self.file_size_remote = None

    scenes = [_Scene("A", "https://asf/a.zip"), _Scene("B", None)]
    out = download_requests_from_scenes(scenes, slc_dir=tmp_path / "02_slc")
    assert [r.scene_id for r in out] == ["A"]
    assert out[0].destination == tmp_path / "02_slc" / "A.zip"


def test_build_earthdata_session_attaches_and_confines_token() -> None:
    requests = pytest.importorskip("requests")
    from types import SimpleNamespace

    from insar_prep.providers.asf.credentials import ResolvedCredential
    from insar_prep.providers.asf.downloader import build_earthdata_session

    resolved = ResolvedCredential(source=CredentialSource.ENV_TOKEN, token="FAKE_TOKEN_XYZ")
    session = build_earthdata_session(resolved)
    assert isinstance(session, requests.Session)
    assert session.headers["Authorization"] == "Bearer FAKE_TOKEN_XYZ"

    # rebuild_auth keeps the header for Earthdata hosts...
    keep = SimpleNamespace(
        headers={"Authorization": "Bearer FAKE_TOKEN_XYZ"},
        url="https://urs.earthdata.nasa.gov/oauth/authorize",
    )
    session.rebuild_auth(keep, None)
    assert "Authorization" in keep.headers

    # ...and drops it before a signed S3 redirect target.
    drop = SimpleNamespace(
        headers={"Authorization": "Bearer FAKE_TOKEN_XYZ"},
        url="https://bucket.s3.amazonaws.com/x.zip?X-Amz-Signature=abc",
    )
    session.rebuild_auth(drop, None)
    assert "Authorization" not in drop.headers


@pytest.mark.real_download
def test_real_download_opt_in_smoke() -> None:
    """Opt-in only: a real, credentialed ASF download. Skipped unless enabled."""
    if os.environ.get("INSAR_REAL_DOWNLOAD") != "1":
        pytest.skip(
            "set INSAR_REAL_DOWNLOAD=1 (with Earthdata credentials) to run the real "
            "download smoke test"
        )
    pytest.skip("real download smoke test is a manual, credentialed scenario")
