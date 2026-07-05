"""Tests for the AOI input module (Task 005)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from insar_prep.core.enums import AoiRole, MultiFeatureMode
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import AoiFeature, BBox, BoundaryCompliance
from insar_prep.processing.aoi import (
    build_regions,
    make_download_aoi,
    make_processing_aoi_from_bbox,
    merge_features_to_one_region,
    select_feature,
    split_features_to_regions,
    validate_china_boundary_compliance,
)


def feat(
    feature_id: str,
    west: float,
    east: float,
    south: float,
    north: float,
    name: str = "",
    **properties: Any,
) -> AoiFeature:
    return AoiFeature(
        feature_id=feature_id,
        name=name,
        bbox=BBox(west=west, east=east, south=south, north=north),
        properties=properties,
    )


def test_bbox_valid_and_to_polygon() -> None:
    bbox = BBox(west=109.5, east=117.5, south=20.0, north=25.5)
    polygon = bbox.to_polygon()
    assert polygon.area > 0
    assert polygon.bounds == (109.5, 20.0, 117.5, 25.5)


def test_bbox_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        BBox(west=10.0, east=5.0, south=0.0, north=1.0)


def test_bbox_buffer() -> None:
    bbox = BBox(west=10.0, east=20.0, south=0.0, north=5.0)
    buffered = bbox.buffer(0.5)
    assert buffered.west == 9.5
    assert buffered.east == 20.5
    assert buffered.south == -0.5
    assert buffered.north == 5.5
    with pytest.raises(ValueError):
        bbox.buffer(-1.0)


def test_processing_to_download_aoi() -> None:
    processing = make_processing_aoi_from_bbox(10.0, 20.0, 0.0, 5.0)
    assert processing.role is AoiRole.PROCESSING_AOI
    download = make_download_aoi(processing, 0.05)
    assert download.role is AoiRole.DOWNLOAD_AOI
    assert download.bbox is not None
    assert download.bbox.west == pytest.approx(9.95)
    assert download.bbox.north == pytest.approx(5.05)


def test_merge_features_to_one_region() -> None:
    features = [feat("a", 10, 12, 0, 2), feat("b", 14, 16, 4, 6)]
    region = merge_features_to_one_region(features, "South China")
    assert region.region_safe_name == "south_china"
    assert region.aoi.bbox is not None
    assert region.aoi.bbox.west == 10.0
    assert region.aoi.bbox.east == 16.0
    assert region.aoi.bbox.south == 0.0
    assert region.aoi.bbox.north == 6.0


def test_select_feature() -> None:
    features = [feat("a", 10, 12, 0, 2), feat("b", 14, 16, 4, 6)]
    selected = select_feature(features, "b")
    assert selected.feature_id == "b"
    with pytest.raises(InputValidationError):
        select_feature(features, "missing")


def test_split_features_to_regions() -> None:
    features = [
        feat("a", 10, 12, 0, 2, name="Guangdong"),
        feat("b", 14, 16, 4, 6, name="Guangxi"),
    ]
    regions = split_features_to_regions(features)
    assert len(regions) == 2
    assert {region.region_safe_name for region in regions} == {"guangdong", "guangxi"}


def test_split_uses_name_field() -> None:
    features = [feat("a", 10, 12, 0, 2, NAME="Shiliushubao Area")]
    regions = split_features_to_regions(features, name_field="NAME")
    assert regions[0].region_safe_name == "shiliushubao_area"


def test_build_regions_modes() -> None:
    features = [
        feat("a", 10, 12, 0, 2, name="Guangdong"),
        feat("b", 14, 16, 4, 6, name="Guangxi"),
    ]
    merged = build_regions(features, MultiFeatureMode.MERGE_TO_ONE_REGION, region_name="merged")
    assert len(merged) == 1
    split = build_regions(features, MultiFeatureMode.SPLIT_TO_REGIONS)
    assert len(split) == 2
    selected = build_regions(features, MultiFeatureMode.SELECT_ONE_FEATURE, feature_id="a")
    assert len(selected) == 1


def test_china_boundary_missing_review_number() -> None:
    boundary = BoundaryCompliance(country="China", requires_review_number=True, review_number=None)
    with pytest.raises(InputValidationError) as excinfo:
        validate_china_boundary_compliance(boundary)
    assert excinfo.value.code is ErrorCode.AOI003


def test_china_boundary_with_review_number_ok() -> None:
    boundary = BoundaryCompliance(
        country="China", requires_review_number=True, review_number="GS(2024)1234"
    )
    validate_china_boundary_compliance(boundary)


def test_non_china_boundary_not_forced() -> None:
    boundary = BoundaryCompliance(country="USA", requires_review_number=False, review_number=None)
    validate_china_boundary_compliance(boundary)


def test_aoi_outputs_are_json_serializable() -> None:
    processing = make_processing_aoi_from_bbox(10.0, 20.0, 0.0, 5.0)
    region = merge_features_to_one_region([feat("a", 10, 12, 0, 2)], "merged")
    feature = feat("a", 10, 12, 0, 2, name="x", attr="bar")
    json.dumps(processing.to_dict())
    json.dumps(region.to_dict())
    json.dumps(feature.to_dict())
