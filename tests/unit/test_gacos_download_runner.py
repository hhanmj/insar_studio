"""Tests for the GACOS request/download orchestration (offline).

Uses injected fake clients so the batch-splitting, results CSV, and the
fetch -> import chain run with no network and no real GACOS account.
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import BBox
from insar_prep.providers.gacos.download_runner import (
    run_gacos_download,
    run_gacos_request,
)
from insar_prep.providers.gacos.downloader import (
    FakeGacosClient,
    GacosFetchOutcome,
    GacosFetchResult,
    GacosRequest,
    GacosSubmitOutcome,
)

_BBOX = BBox(west=110.1, south=30.8, east=110.6, north=31.2)


def _dates(n: int) -> list[date]:
    return [date(2024, 1, 1 + i) for i in range(n)]


def test_request_splits_into_batches_and_writes_csv(tmp_path: Path) -> None:
    fake = FakeGacosClient()
    summary = run_gacos_request(
        region_safe_name="demo",
        bbox=_BBOX,
        dates=_dates(25),
        email="tester@example.com",
        output_root=tmp_path,
        client=fake,
    )
    assert summary.total == 2
    assert summary.submitted == 2
    assert [len(req.dates) for req in fake.submitted] == [20, 5]
    csv_path = tmp_path / "GACOS" / "gacos_request_results.csv"
    assert csv_path.exists()
    assert summary.results[0].batch_count == 2


def test_request_requires_dates(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        run_gacos_request(
            region_safe_name="demo",
            bbox=_BBOX,
            dates=[],
            email="tester@example.com",
            output_root=tmp_path,
            client=FakeGacosClient(),
        )


def test_request_rejects_bad_time(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        run_gacos_request(
            region_safe_name="demo",
            bbox=_BBOX,
            dates=_dates(2),
            email="tester@example.com",
            output_root=tmp_path,
            hour=99,
            client=FakeGacosClient(),
        )


def test_request_submission_failure_is_captured(tmp_path: Path) -> None:
    fake = FakeGacosClient(submit_outcome=GacosSubmitOutcome.FAILED)
    summary = run_gacos_request(
        region_safe_name="demo",
        bbox=_BBOX,
        dates=_dates(3),
        email="tester@example.com",
        output_root=tmp_path,
        client=fake,
    )
    assert summary.has_failures
    assert summary.failed == 1


def _make_product_zip(path: Path) -> None:
    """Write a zip with one valid GACOS product (16-byte ztd + matching rsc)."""
    rsc = "WIDTH 2\nFILE_LENGTH 2\nX_FIRST 110.0\nY_FIRST 31.5\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("20240101.ztd", b"\x00" * 16)
        zf.writestr("20240101.ztd.rsc", rsc)


class _ProductZipClient:
    """A fake GACOS client whose fetch writes a real product zip to disk."""

    def submit(self, request: GacosRequest):  # pragma: no cover - not used here
        raise NotImplementedError

    def fetch(self, url: str, destination: Path) -> GacosFetchResult:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _make_product_zip(destination)
        return GacosFetchResult(
            outcome=GacosFetchOutcome.SUCCESS,
            path=destination,
            bytes_written=destination.stat().st_size,
            message="fetched",
        )


def test_download_fetches_and_imports(tmp_path: Path) -> None:
    output_dir = tmp_path / "demo" / "GACOS" / "requests"
    summary = run_gacos_download(
        ["http://www.gacos.net/data/demo.zip"],
        output_dir,
        expected_dates=[date(2024, 1, 1)],
        client=_ProductZipClient(),
    )
    assert summary.fetched == 1
    assert summary.import_result is not None
    assert summary.import_result.summary["product_date_count"] == 1
    assert summary.import_result.summary["valid_product_count"] == 1
    assert not summary.import_result.missing_dates
    # Product organized into the requests directory under the canonical name.
    assert (output_dir / "20240101.ztd").exists()
    assert (output_dir / "20240101.ztd.rsc").exists()
    # A staging archive is kept alongside, and a fetch results CSV is written.
    assert (tmp_path / "demo" / "GACOS" / "downloads").exists()
    assert (output_dir / "gacos_download_results.csv").exists()


def test_download_requires_urls(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        run_gacos_download([], tmp_path, client=_ProductZipClient())


def test_download_failure_is_captured(tmp_path: Path) -> None:
    fake = FakeGacosClient(fetch_outcome=GacosFetchOutcome.FAILED)
    summary = run_gacos_download(
        ["http://www.gacos.net/data/demo.zip"],
        tmp_path / "out",
        client=fake,
    )
    assert summary.has_failures
    assert summary.import_result is None
