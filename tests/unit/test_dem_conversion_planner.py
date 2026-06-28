"""Tests for the DEM vertical-datum conversion planner (Task 011)."""

from __future__ import annotations

import json
from pathlib import Path

from insar_prep.core.enums import VerticalDatum
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.providers.dem.conversion_planner import (
    DEM_CONVERSION_NOT_REQUIRED,
    DEM_CONVERSION_PLAN_READY,
    DEM_GEOID_REQUIRED,
    DEM_MANUAL_REVIEW_REQUIRED,
    DEM_VERTICAL_DATUM_UNKNOWN,
    create_dem_conversion_plan,
    requires_geoid_conversion,
    suggest_geoid_model,
    validate_dem_conversion_plan,
)
from insar_prep.providers.dem.planner import create_dem_request_plan


def make_request_plan(
    tmp_path: Path,
    *,
    source: VerticalDatum = VerticalDatum.EGM2008,
    target: VerticalDatum = VerticalDatum.WGS84_ELLIPSOID,
):
    return create_dem_request_plan(
        region_id="r1",
        region_safe_name="shiliushubao",
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        output_root=tmp_path,
        source_vertical_datum=source,
        target_vertical_datum=target,
    )


def _codes(report: object) -> set[str]:
    return {issue.code for issue in report.issues}  # type: ignore[attr-defined]


def test_egm2008_requires_conversion(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path, source=VerticalDatum.EGM2008))
    assert plan.requires_conversion
    assert plan.requires_geoid
    report = validate_dem_conversion_plan(plan)
    assert not report.has_errors
    assert DEM_GEOID_REQUIRED in _codes(report)


def test_egm96_requires_conversion(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path, source=VerticalDatum.EGM96))
    assert plan.requires_conversion
    assert plan.requires_geoid


def test_same_datum_no_conversion(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(
        make_request_plan(
            tmp_path,
            source=VerticalDatum.WGS84_ELLIPSOID,
            target=VerticalDatum.WGS84_ELLIPSOID,
        )
    )
    assert not plan.requires_conversion
    assert not plan.requires_geoid
    report = validate_dem_conversion_plan(plan)
    assert DEM_CONVERSION_NOT_REQUIRED in _codes(report)
    assert plan.sarscape_ready_dem_path.name.endswith("_dem")


def test_orthometric_requires_manual_review(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path, source=VerticalDatum.ORTHOMETRIC))
    report = validate_dem_conversion_plan(plan)
    assert DEM_MANUAL_REVIEW_REQUIRED in _codes(report)


def test_unknown_datum_is_error(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path, source=VerticalDatum.UNKNOWN))
    report = validate_dem_conversion_plan(plan)
    assert report.has_errors
    assert DEM_VERTICAL_DATUM_UNKNOWN in _codes(report)


def test_requires_geoid_conversion_function() -> None:
    assert requires_geoid_conversion(VerticalDatum.EGM2008, VerticalDatum.WGS84_ELLIPSOID)
    assert requires_geoid_conversion(VerticalDatum.EGM96, VerticalDatum.WGS84_ELLIPSOID)
    assert not requires_geoid_conversion(
        VerticalDatum.WGS84_ELLIPSOID, VerticalDatum.WGS84_ELLIPSOID
    )


def test_suggest_geoid_model() -> None:
    assert suggest_geoid_model(VerticalDatum.EGM96, VerticalDatum.WGS84_ELLIPSOID) == "EGM96"
    assert suggest_geoid_model(VerticalDatum.EGM2008, VerticalDatum.WGS84_ELLIPSOID) == "EGM2008"
    assert suggest_geoid_model(VerticalDatum.ORTHOMETRIC, VerticalDatum.WGS84_ELLIPSOID) is None
    assert suggest_geoid_model(VerticalDatum.WGS84_ELLIPSOID, VerticalDatum.WGS84_ELLIPSOID) is None


def test_plan_has_three_paths(tmp_path: Path) -> None:
    request_plan = make_request_plan(tmp_path)
    plan = create_dem_conversion_plan(request_plan)
    assert plan.raw_dem_path == request_plan.raw_dem_path
    assert plan.ellipsoid_dem_path == request_plan.ellipsoid_dem_path
    assert plan.sarscape_ready_dem_path == request_plan.sarscape_ready_dem_path


def test_sarscape_ready_is_envi_dem(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path))
    assert plan.sarscape_ready_dem_path.name.endswith("_dem")
    assert not plan.sarscape_ready_dem_path.name.endswith("_ellipsoid_dem")
    assert "_ellipsoid" in plan.ellipsoid_dem_path.name


def test_no_dem_files_created(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path))
    assert not plan.raw_dem_path.exists()
    assert not plan.ellipsoid_dem_path.exists()
    assert not plan.sarscape_ready_dem_path.exists()


def test_plan_and_report_json_serializable(tmp_path: Path) -> None:
    plan = create_dem_conversion_plan(make_request_plan(tmp_path))
    report = validate_dem_conversion_plan(plan)
    assert isinstance(json.dumps(plan.to_dict()), str)
    assert isinstance(json.dumps(report.to_dict()), str)
    assert DEM_CONVERSION_PLAN_READY in _codes(report)
