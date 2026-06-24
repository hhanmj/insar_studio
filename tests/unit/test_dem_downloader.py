"""Tests for the real OpenTopography DEM downloader's transfer logic.

The network is never touched: a fake ``requests``-like session is injected so the
``.part`` -> atomic-rename, GeoTIFF-magic / size checks, retry/backoff,
key-rejection, and cancellation paths are all exercised offline.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from insar_prep.core.enums import DemDataset
from insar_prep.core.models import BBox
from insar_prep.providers.dem.credentials import DemKeySource, ResolvedDemKey
from insar_prep.providers.dem.downloader import (
    DemDownloader,
    DemDownloadOutcome,
    DemDownloadRequest,
    RealDemDownloader,
    dem_download_request_from_plan,
    opentopo_demtype,
)

# Valid little-endian GeoTIFF magic so the integrity check passes.
_TIFF = b"II*\x00"
_FAKE_KEY = ResolvedDemKey(source=DemKeySource.ENV, api_key="FAKE_KEY_XYZ")


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
        content_type: str = "application/octet-stream",
        chunks: tuple[bytes, ...] = (_TIFF + b"dem",),
    ) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {"Content-Type": content_type}
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
        self.last_params: dict[str, str] | None = None

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls += 1
        self.last_params = kwargs.get("params")  # type: ignore[assignment]
        action = self._actions.pop(0) if self._actions else _FakeResponse()
        if isinstance(action, Exception):
            raise action
        return action  # type: ignore[return-value]


def _request(tmp_path: Path, *, demtype: str = "COP30") -> DemDownloadRequest:
    return DemDownloadRequest(
        region_safe_name="demo",
        dataset="COP30",
        demtype=demtype,
        bbox=BBox(west=110.1, south=30.8, east=110.6, north=31.2),
        destination=tmp_path / "04_dem" / "raw" / "demo_cop30_raw.tif",
    )


def _downloader(session: object, **kw: object) -> RealDemDownloader:
    return RealDemDownloader(session=session, resolved=_FAKE_KEY, backoff_seconds=0.0, **kw)


def test_demtype_mapping() -> None:
    assert opentopo_demtype(DemDataset.COP30) == "COP30"
    assert opentopo_demtype(DemDataset.SRTM_GL1_ELLIPSOIDAL) == "SRTMGL1_E"
    assert opentopo_demtype(DemDataset.AW3D30_ELLIPSOIDAL) == "AW3D30_E"
    assert opentopo_demtype(DemDataset.USER_LOCAL) is None


def test_real_downloader_satisfies_protocol() -> None:
    assert isinstance(RealDemDownloader(session=_FakeSession([])), DemDownloader)


def test_construct_does_not_touch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    RealDemDownloader(key_source=DemKeySource.ENV)  # no session/key resolved yet


def test_success_streams_to_final_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    chunks = (_TIFF, b"payload")
    total = len(_TIFF) + len(b"payload")
    session = _FakeSession([_FakeResponse(content_length=total, chunks=chunks)])
    result = _downloader(session).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.SUCCESS
    assert result.bytes_written == total
    dest = tmp_path / "04_dem" / "raw" / "demo_cop30_raw.tif"
    assert dest.exists()
    assert dest.read_bytes() == _TIFF + b"payload"
    assert not list(tmp_path.rglob("*.part"))
    # The API key travels as the API_Key query parameter.
    assert session.last_params is not None
    assert session.last_params["API_Key"] == "FAKE_KEY_XYZ"
    assert session.last_params["demtype"] == "COP30"


def test_skip_when_already_present(tmp_path: Path) -> None:
    dest = tmp_path / "04_dem" / "raw" / "demo_cop30_raw.tif"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(_TIFF + b"existing")
    session = _FakeSession([])  # must not be used
    result = _downloader(session).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.SKIPPED
    assert session.calls == 0


def test_key_rejected_no_retry(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(status_code=403)])
    result = _downloader(session, max_retries=3).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM005"
    assert session.calls == 1
    assert not list(tmp_path.rglob("*.part"))


def test_transient_then_success(tmp_path: Path) -> None:
    session = _FakeSession(
        [_FakeResponse(status_code=503), _FakeResponse(content_length=4, chunks=(_TIFF,))]
    )
    result = _downloader(session, max_retries=3).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.SUCCESS
    assert session.calls == 2


def test_non_tiff_response_fails_dem001(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(chunks=(b"<html>error</html>",))] * 2)
    result = _downloader(session, max_retries=2).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "04_dem" / "raw" / "demo_cop30_raw.tif").exists()


def test_text_content_type_fails_dem001(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(content_type="text/html", chunks=(_TIFF,))] * 2)
    result = _downloader(session, max_retries=2).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"


def test_empty_response_fails_dem001(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(chunks=())] * 2)
    result = _downloader(session, max_retries=2).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"


def test_size_mismatch_fails_and_discards_part(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(content_length=100, chunks=(_TIFF + b"abc",))] * 2)
    result = _downloader(session, max_retries=2).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"
    assert not list(tmp_path.rglob("*.part"))


def test_cancellation_keeps_part(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    session = _FakeSession([_FakeResponse(content_length=4, chunks=(_TIFF,))])
    result = _downloader(session, cancel_event=cancel).download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.INTERRUPTED
    assert result.error_code == "DEM001"


def test_no_demtype_fails_dem001(tmp_path: Path) -> None:
    result = _downloader(_FakeSession([])).download(_request(tmp_path, demtype=""))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"


def test_missing_env_key_fails_dem005(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    monkeypatch.delenv("OPENTOPOGRAPHY_API_KEY", raising=False)
    downloader = RealDemDownloader(key_source=DemKeySource.ENV)
    result = downloader.download(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM005"


def test_verify_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    session = _FakeSession([_FakeResponse(chunks=(_TIFF + b"sample",))])
    result = _downloader(session).verify(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.VERIFIED
    assert not (tmp_path / "04_dem" / "raw" / "demo_cop30_raw.tif").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_verify_key_rejected_dem005(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(status_code=403)])
    result = _downloader(session).verify(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM005"


def test_verify_transport_error_dem001(tmp_path: Path) -> None:
    session = _FakeSession([ConnectionResetError("boom")])
    result = _downloader(session).verify(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"


def test_verify_non_tiff_fails_dem001(tmp_path: Path) -> None:
    session = _FakeSession([_FakeResponse(chunks=(b"not-a-tiff",))])
    result = _downloader(session).verify(_request(tmp_path))
    assert result.outcome is DemDownloadOutcome.FAILED
    assert result.error_code == "DEM001"


def test_dem_download_request_from_plan() -> None:
    class _Plan:
        region_safe_name = "demo"
        dataset = "COP30"
        request_bbox = BBox(west=1.0, south=2.0, east=3.0, north=4.0)
        raw_dem_path = Path("out/demo_cop30_raw.tif")

    request = dem_download_request_from_plan(_Plan())
    assert request is not None
    assert request.demtype == "COP30"
    assert request.destination == Path("out/demo_cop30_raw.tif")


def test_dem_download_request_from_plan_unsupported_returns_none() -> None:
    class _Plan:
        region_safe_name = "demo"
        dataset = "USER_LOCAL"
        request_bbox = BBox(west=1.0, south=2.0, east=3.0, north=4.0)
        raw_dem_path = Path("out/x.tif")

    assert dem_download_request_from_plan(_Plan()) is None
