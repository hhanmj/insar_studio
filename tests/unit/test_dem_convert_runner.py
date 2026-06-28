"""Tests for the DEM conversion runner + results CSV (Task 053). Offline only."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from insar_prep.core.enums import DemDataset, VerticalDatum
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.providers.dem.convert_runner import (
    DEM_CONVERT_SUBDIR,
    run_dem_conversion,
)
from insar_prep.providers.dem.converter import DemConversionOutcome, FakeDemConverter
from insar_prep.providers.dem.types import DemConversionPlan


def _plan(tmp_path: Path, name: str) -> DemConversionPlan:
    region = tmp_path / name
    return DemConversionPlan(
        region_id="",
        region_safe_name=name,
        dataset=DemDataset.COP30.value,
        source_vertical_datum=VerticalDatum.EGM2008,
        target_vertical_datum=VerticalDatum.WGS84_ELLIPSOID,
        raw_dem_path=region / "raw.tif",
        ellipsoid_dem_path=region / "ellipsoid.tif",
        sarscape_ready_dem_path=region / f"{name}_dem",
        requires_conversion=True,
        requires_geoid=True,
    )


def test_run_dem_conversion_writes_results_csv(tmp_path: Path) -> None:
    plans = [_plan(tmp_path, "alpha"), _plan(tmp_path, "beta")]
    for plan in plans:
        plan.raw_dem_path.parent.mkdir(parents=True, exist_ok=True)
        plan.raw_dem_path.write_bytes(b"dem")

    summary = run_dem_conversion(plans, tmp_path, converter=FakeDemConverter())
    assert summary.total == 2
    assert summary.succeeded == 2
    assert not summary.has_failures
    assert "2 converted" in summary.summary_line()

    results_csv = tmp_path / DEM_CONVERT_SUBDIR / "dem_convert_results.csv"
    assert results_csv == summary.results_path
    rows = list(csv.DictReader(results_csv.open(encoding="utf-8")))
    assert [r["region_safe_name"] for r in rows] == ["alpha", "beta"]
    assert all(r["outcome"] == "success" for r in rows)
    assert all(r["source_vertical_datum"] == "EGM2008" for r in rows)


def test_run_dem_conversion_records_failures(tmp_path: Path) -> None:
    plans = [_plan(tmp_path, "alpha")]
    summary = run_dem_conversion(
        plans, tmp_path, converter=FakeDemConverter(outcome=DemConversionOutcome.FAILED)
    )
    assert summary.has_failures
    assert summary.failed == 1


def test_run_dem_conversion_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(InsarPrepError):
        run_dem_conversion([], tmp_path, converter=FakeDemConverter())
