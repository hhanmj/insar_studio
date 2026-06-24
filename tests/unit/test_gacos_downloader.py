"""Tests for the real GACOS client (form submission + result fetch).

A fake ``requests``-style session is injected so the submit/fetch logic runs with
no network and no real GACOS account. The :class:`FakeGacosClient` is also
exercised for the offline orchestration paths.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from insar_prep.core.models import BBox
from insar_prep.providers.gacos.downloader import (
    GACOS_SUBMIT_ENDPOINT,
    FakeGacosClient,
    GacosFetchOutcome,
    GacosOutputFormat,
    GacosRequest,
    GacosSubmitOutcome,
    RealGacosClient,
)


def _request(email: str = "tester@example.com") -> GacosRequest:
    return GacosRequest(
        region_safe_name="demo",
        bbox=BBox(west=110.1, south=30.8, east=110.6, north=31.2),
        dates=[date(2024, 1, 1), date(2024, 1, 13)],
        hour=18,
        minute=30,
        output_format=GacosOutputFormat.GEOTIFF,
        email=email,
    )


class _Response:
    def __init__(self, status_code=200, text="", headers=None, chunks=None) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._chunks = chunks or []

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def iter_content(self, chunk_size: int = 0):
        yield from self._chunks


class _FakeSession:
    def __init__(self, *, post_response=None, get_response=None) -> None:
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []
        self._post_response = post_response or _Response(200, text="Request received")
        self._get_response = get_response

    def post(self, url, data=None, timeout=None):
        self.post_calls.append({"url": url, "data": data})
        return self._post_response

    def get(self, url, stream=False, timeout=None):
        self.get_calls.append(url)
        return self._get_response


def test_form_data_maps_to_gacos_fields() -> None:
    client = RealGacosClient(session=_FakeSession())
    data = client._form_data(_request(), "tester@example.com")
    assert data["N"] == "31.2"
    assert data["S"] == "30.8"
    assert data["W"] == "110.1"
    assert data["E"] == "110.6"
    assert data["H"] == "18"
    assert data["M"] == "30"
    assert data["type"] == "2"  # GeoTIFF
    assert data["date"] == "20240101\n20240113"
    assert data["email"] == "tester@example.com"


def test_binary_format_maps_to_type_1() -> None:
    client = RealGacosClient(session=_FakeSession())
    request = _request()
    request.output_format = GacosOutputFormat.BINARY
    data = client._form_data(request, "tester@example.com")
    assert data["type"] == "1"


def test_submit_success() -> None:
    session = _FakeSession(post_response=_Response(200, text="<html>Request received</html>"))
    client = RealGacosClient(session=session)
    result = client.submit(_request())
    assert result.outcome is GacosSubmitOutcome.SUBMITTED
    assert session.post_calls[0]["url"] == GACOS_SUBMIT_ENDPOINT
    assert "tester@example.com" not in result.message  # masked


def test_submit_detects_error_page() -> None:
    session = _FakeSession(post_response=_Response(200, text="Error: maximum 20 dates exceeded"))
    client = RealGacosClient(session=session)
    result = client.submit(_request())
    assert result.outcome is GacosSubmitOutcome.FAILED


def test_submit_http_error() -> None:
    session = _FakeSession(post_response=_Response(400, text="bad request"))
    client = RealGacosClient(session=session)
    result = client.submit(_request())
    assert result.outcome is GacosSubmitOutcome.FAILED
    assert result.error_code is not None


def test_submit_without_email_fails_when_unresolved() -> None:
    client = RealGacosClient(session=_FakeSession(), resolved=None)
    request = _request(email="")
    # No email passed and none stored -> resolution fails (no network attempted).
    result = client.submit(request)
    assert result.outcome is GacosSubmitOutcome.FAILED


def test_fetch_http_writes_and_renames(tmp_path: Path) -> None:
    payload = [b"PK\x03\x04", b"abc", b"def"]
    get_response = _Response(200, headers={"Content-Length": "10"}, chunks=payload)
    session = _FakeSession(get_response=get_response)
    client = RealGacosClient(session=session)
    dest = tmp_path / "result.zip"
    result = client.fetch("http://www.gacos.net/data/result.zip", dest)
    assert result.outcome is GacosFetchOutcome.SUCCESS
    assert dest.exists()
    assert dest.read_bytes() == b"PK\x03\x04abcdef"
    assert not (tmp_path / "result.zip.part").exists()


def test_fetch_skips_existing(tmp_path: Path) -> None:
    dest = tmp_path / "result.zip"
    dest.write_bytes(b"already here")
    client = RealGacosClient(session=_FakeSession())
    result = client.fetch("http://www.gacos.net/data/result.zip", dest)
    assert result.outcome is GacosFetchOutcome.SKIPPED


def test_fetch_rejects_unknown_scheme(tmp_path: Path) -> None:
    client = RealGacosClient(session=_FakeSession())
    result = client.fetch("gopher://nope/result.zip", tmp_path / "r.zip")
    assert result.outcome is GacosFetchOutcome.FAILED


def test_fake_client_submit_and_fetch(tmp_path: Path) -> None:
    fake = FakeGacosClient(write_placeholder=True)
    submit = fake.submit(_request())
    assert submit.outcome is GacosSubmitOutcome.SUBMITTED
    assert fake.submitted
    dest = tmp_path / "r.zip"
    fetch = fake.fetch("http://x/r.zip", dest)
    assert fetch.outcome is GacosFetchOutcome.SUCCESS
    assert dest.exists()
