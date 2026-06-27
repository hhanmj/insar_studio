"""Tests for the real DEM vertical-datum converter (Task 053).

The geoid math and orchestration are exercised with numpy only; the end-to-end
GeoTIFF round-trip is gated behind ``importorskip('rasterio')`` so CI (which does
not install the ``convert`` extra) skips it while a local ``--extra convert``
environment runs it. No network is ever used.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from insar_prep.core.enums import DemDataset, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.providers.dem.converter import (
    DemConversionOutcome,
    FakeDemConverter,
    RealDemConverter,
    dataset_source_vertical_datum,
    default_geoid_model_for,
)
from insar_prep.providers.dem.geoid import load_bundled_geoid
from insar_prep.providers.dem.types import DemConversionPlan


def _plan(
    tmp_path: Path,
    *,
    source: VerticalDatum,
    target: VerticalDatum = VerticalDatum.WGS84_ELLIPSOID,
    dataset: str = DemDataset.COP30.value,
) -> DemConversionPlan:
    region = tmp_path / "demo"
    return DemConversionPlan(
        region_id="",
        region_safe_name="demo",
        dataset=dataset,
        source_vertical_datum=source,
        target_vertical_datum=target,
        raw_dem_path=region / "04_dem" / "raw" / "demo_raw.tif",
        ellipsoid_dem_path=region / "04_dem" / "ellipsoid" / "demo_ellipsoid.tif",
        sarscape_ready_dem_path=region / "04_dem" / "demo_dem.tif",
        requires_conversion=source != target,
        requires_geoid=source != target,
    )


def _write_geotiff(path: Path, array: np.ndarray, *, west: float, north: float, res: float, crs):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(west, north, res, res)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(array.astype(np.float32), 1)


def test_dataset_source_vertical_datum() -> None:
    assert dataset_source_vertical_datum(DemDataset.COP30) is VerticalDatum.EGM2008
    assert dataset_source_vertical_datum(DemDataset.SRTM_GL3) is VerticalDatum.EGM96
    assert dataset_source_vertical_datum(DemDataset.SRTM_GL1) is VerticalDatum.EGM96
    assert dataset_source_vertical_datum(DemDataset.SRTM_GL1_ELLIPSOIDAL) is (
        VerticalDatum.WGS84_ELLIPSOID
    )
    assert dataset_source_vertical_datum(DemDataset.USER_LOCAL) is VerticalDatum.UNKNOWN


def test_default_geoid_model_for() -> None:
    assert default_geoid_model_for(VerticalDatum.EGM96) == "EGM96"
    assert default_geoid_model_for(VerticalDatum.EGM2008) == "EGM2008"
    assert default_geoid_model_for(VerticalDatum.WGS84_ELLIPSOID) is None


def test_fake_converter_success_and_failure(tmp_path: Path) -> None:
    plan = _plan(tmp_path, source=VerticalDatum.EGM96)
    plan.raw_dem_path.parent.mkdir(parents=True, exist_ok=True)
    plan.raw_dem_path.write_bytes(b"raw-bytes")

    ok = FakeDemConverter().convert(plan)
    assert ok.outcome is DemConversionOutcome.SUCCESS
    assert plan.sarscape_ready_dem_path.read_bytes() == b"raw-bytes"

    bad = FakeDemConverter(outcome=DemConversionOutcome.FAILED).convert(plan)
    assert bad.outcome is DemConversionOutcome.FAILED
    assert bad.error_code == ErrorCode.DEM003.value


def test_real_converter_skips_when_dest_present(tmp_path: Path) -> None:
    plan = _plan(tmp_path, source=VerticalDatum.EGM96)
    plan.sarscape_ready_dem_path.parent.mkdir(parents=True, exist_ok=True)
    plan.sarscape_ready_dem_path.write_bytes(b"already-there")
    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.SKIPPED


def test_real_converter_unknown_datum_fails(tmp_path: Path) -> None:
    plan = _plan(tmp_path, source=VerticalDatum.UNKNOWN)
    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.FAILED
    assert result.error_code == ErrorCode.DEM002.value


def test_real_converter_missing_raw_fails(tmp_path: Path) -> None:
    plan = _plan(tmp_path, source=VerticalDatum.EGM96)
    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.FAILED
    assert result.error_code == ErrorCode.DEM003.value


def test_real_converter_copies_already_ellipsoidal(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        source=VerticalDatum.WGS84_ELLIPSOID,
        dataset=DemDataset.SRTM_GL1_ELLIPSOIDAL.value,
    )
    plan.raw_dem_path.parent.mkdir(parents=True, exist_ok=True)
    plan.raw_dem_path.write_bytes(b"ellipsoidal-dem")
    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.COPIED
    assert plan.sarscape_ready_dem_path.read_bytes() == b"ellipsoidal-dem"


def test_real_converter_applies_geoid_offset(tmp_path: Path) -> None:
    pytest.importorskip("rasterio")
    from rasterio.crs import CRS

    plan = _plan(tmp_path, source=VerticalDatum.EGM96, dataset=DemDataset.SRTM_GL1.value)
    west, north, res = 10.0, 46.0, 0.25
    heights = np.full((4, 4), 100.0, dtype=np.float32)
    heights[0, 0] = -9999.0  # nodata pixel must be preserved
    _write_geotiff(
        plan.raw_dem_path, heights, west=west, north=north, res=res, crs=CRS.from_epsg(4326)
    )

    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.SUCCESS, result.message
    assert result.geoid_model == "EGM96"

    import rasterio

    with rasterio.open(plan.sarscape_ready_dem_path) as src:
        out = src.read(1)
    geoid = load_bundled_geoid("EGM96")
    rows = np.arange(4) + 0.5
    cols = np.arange(4) + 0.5
    col_grid, row_grid = np.meshgrid(cols, rows)
    lon = west + col_grid * res
    lat = north - row_grid * res
    expected = 100.0 + geoid.undulation_at(lat, lon)
    # nodata pixel preserved
    assert out[0, 0] == pytest.approx(-9999.0)
    mask = np.ones((4, 4), dtype=bool)
    mask[0, 0] = False
    assert np.allclose(out[mask], expected[mask].astype(np.float32), atol=1e-3)


def test_real_converter_rejects_projected_crs(tmp_path: Path) -> None:
    pytest.importorskip("rasterio")
    from rasterio.crs import CRS

    plan = _plan(tmp_path, source=VerticalDatum.EGM96, dataset=DemDataset.SRTM_GL1.value)
    heights = np.full((4, 4), 100.0, dtype=np.float32)
    _write_geotiff(
        plan.raw_dem_path,
        heights,
        west=500000.0,
        north=5200000.0,
        res=30.0,
        crs=CRS.from_epsg(32632),
    )
    result = RealDemConverter().convert(plan)
    assert result.outcome is DemConversionOutcome.FAILED
    assert result.error_code == ErrorCode.DEM003.value
