"""Offline tests for the shared DEM download orchestration (``run_dem_download``).

No network and no real OpenTopography key: the library's ``FakeDemDownloader`` is
injected so the success / failure / all-skipped / cancel paths run
deterministically. The masked results TXT is verified too.
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path

import pytest

from insar_prep.core.enums import AoiRole, AoiSource, DemDataset
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.models import Aoi, BBox
from insar_prep.providers.dem.download_runner import (
    run_dem_download,
    write_dem_download_results_csv,
)
from insar_prep.providers.dem.downloader import (
    DemDownloadOutcome,
    DemDownloadResult,
    FakeDemDownloader,
)
from insar_prep.providers.dem.planner import create_dem_request_plan


def _aoi() -> Aoi:
    return Aoi(
        source=AoiSource.MANUAL_BBOX,
        role=AoiRole.PROCESSING_AOI,
        bbox=BBox(west=110.1, south=30.8, east=110.6, north=31.2),
    )


def _plan(tmp_path: Path, *, dataset: DemDataset = DemDataset.COP30, name: str = "demo"):
    provider = "OPENTOPOGRAPHY" if dataset is not DemDataset.USER_LOCAL else "LOCAL"
    return create_dem_request_plan(
        region_id="",
        region_safe_name=name,
        processing_aoi=_aoi(),
        output_root=tmp_path,
        dataset=dataset,
        provider=provider,
    )


def test_success_writes_masked_results_txt(tmp_path: Path) -> None:
    fake = FakeDemDownloader(outcome=DemDownloadOutcome.SUCCESS, write_placeholder=True)
    progress: list[DemDownloadResult] = []
    summary = run_dem_download(
        [_plan(tmp_path)], tmp_path, downloader=fake, progress=progress.append
    )
    assert summary.total == 1
    assert summary.succeeded == 1
    assert not summary.has_failures
    assert len(progress) == 1

    results_txt = summary.results_path
    assert results_txt is not None
    assert results_txt.parent == tmp_path
    assert results_txt.name.startswith("dem_download_results_")
    assert results_txt.name.endswith(".txt")
    assert results_txt.name.isascii()
    with results_txt.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["region_safe_name"] == "demo"
    assert rows[0]["outcome"] == "success"
    # The fake never writes a real GeoTIFF.
    assert not list(tmp_path.rglob("*.tif"))


def test_failure_is_counted_not_raised(tmp_path: Path) -> None:
    fake = FakeDemDownloader(outcome=DemDownloadOutcome.FAILED)
    summary = run_dem_download([_plan(tmp_path)], tmp_path, downloader=fake)
    assert summary.failed == 1
    assert summary.has_failures


def test_no_plans_raises(tmp_path: Path) -> None:
    with pytest.raises(InsarPrepError):
        run_dem_download([], tmp_path, downloader=FakeDemDownloader())


def test_all_unsupported_raises(tmp_path: Path) -> None:
    plan = _plan(tmp_path, dataset=DemDataset.USER_LOCAL, name="local_only")
    with pytest.raises(InsarPrepError):
        run_dem_download([plan], tmp_path, downloader=FakeDemDownloader())


def test_cancel_before_start_downloads_nothing(tmp_path: Path) -> None:
    fake = FakeDemDownloader()
    cancel = threading.Event()
    cancel.set()
    summary = run_dem_download([_plan(tmp_path)], tmp_path, downloader=fake, cancel_event=cancel)
    assert fake.calls == []
    assert summary.total == 0
    assert summary.cancelled is True
    assert summary.results_path is None


def test_write_results_txt_has_fixed_header(tmp_path: Path) -> None:
    results = [
        DemDownloadResult(
            region_safe_name="demo",
            dataset="COP30",
            outcome=DemDownloadOutcome.SUCCESS,
            bytes_written=10,
            message="ok",
        )
    ]
    path = write_dem_download_results_csv(tmp_path, results)
    with path.open(encoding="utf-8", newline="") as handle:
        header = handle.readline().strip()
    assert header == "region_safe_name\tdataset\toutcome\tbytes_written\terror_code\tmessage"


def test_each_results_log_has_an_independent_ascii_filename(tmp_path: Path) -> None:
    result = DemDownloadResult(
        region_safe_name="demo",
        dataset="COP30",
        outcome=DemDownloadOutcome.SUCCESS,
        bytes_written=10,
        message="ok",
    )

    first = write_dem_download_results_csv(tmp_path, [result])
    second = write_dem_download_results_csv(tmp_path, [result])

    assert first != second
    assert first.exists() and second.exists()
    assert first.name.isascii() and second.name.isascii()
