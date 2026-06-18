"""Tests for the GACOS request planner (Task 012)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi, Scene
from insar_prep.processing.aoi import make_download_aoi, make_processing_aoi_from_bbox
from insar_prep.providers.gacos.planner import (
    GACOS_MANUAL_SUBMISSION_REQUIRED,
    GACOS_NO_VALID_DATES,
    GACOS_PLAN_READY,
    GACOS_SCENE_DATE_MISSING,
    create_gacos_request_plan,
    extract_gacos_dates_from_scenes,
    validate_gacos_request_plan,
)


def make_processing(
    west: float = 109.5,
    east: float = 117.5,
    south: float = 20.0,
    north: float = 25.5,
) -> Aoi:
    return make_processing_aoi_from_bbox(west, east, south, north)


def make_scene(dt: datetime | None) -> Scene:
    return Scene(acquisition_datetime=dt)


def sequential_scenes(count: int, *, step_days: int = 12) -> list[Scene]:
    start = datetime(2023, 1, 1, 12, 0, 0)
    return [make_scene(start + timedelta(days=step_days * i)) for i in range(count)]


def build_plan(
    tmp_path: Path,
    *,
    scenes: list[Scene] | None = None,
    region_safe_name: str = "shiliushubao",
    aoi: Aoi | None = None,
    **kwargs,
):
    return create_gacos_request_plan(
        region_id="r1",
        region_safe_name=region_safe_name,
        processing_aoi=aoi or make_processing(),
        scenes=sequential_scenes(3) if scenes is None else scenes,
        output_root=tmp_path,
        **kwargs,
    )


def test_extract_dates_deduplicates_and_sorts() -> None:
    scenes = [
        make_scene(datetime(2023, 1, 13, 12, 0)),
        make_scene(datetime(2023, 1, 1, 6, 0)),
        make_scene(datetime(2023, 1, 1, 18, 0)),  # same calendar day as above
        make_scene(datetime(2023, 1, 25, 0, 0)),
    ]
    assert extract_gacos_dates_from_scenes(scenes) == [
        date(2023, 1, 1),
        date(2023, 1, 13),
        date(2023, 1, 25),
    ]


def test_extract_dates_skips_missing() -> None:
    scenes = [
        make_scene(datetime(2023, 1, 1)),
        make_scene(None),
        make_scene(datetime(2023, 1, 13)),
    ]
    assert extract_gacos_dates_from_scenes(scenes) == [date(2023, 1, 1), date(2023, 1, 13)]


def test_missing_scene_dates_warned(tmp_path: Path) -> None:
    scenes = [
        make_scene(datetime(2023, 1, 1)),
        make_scene(None),
        make_scene(datetime(2023, 1, 13)),
    ]
    plan = build_plan(tmp_path, scenes=scenes)
    assert plan.scene_missing_date_count == 1
    assert plan.unique_dates == [date(2023, 1, 1), date(2023, 1, 13)]
    report = validate_gacos_request_plan(plan)
    assert report.has_warnings
    assert any(issue.code == GACOS_SCENE_DATE_MISSING for issue in report.issues)


def test_empty_scene_list_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, scenes=[])


def test_negative_buffer_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, buffer_degrees=-0.1)


def test_batch_size_below_one_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, max_dates_per_batch=0)


def test_non_processing_aoi_raises(tmp_path: Path) -> None:
    download_aoi = make_download_aoi(make_processing(), 0.05)
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, aoi=download_aoi)


def test_batching_splits_dates(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, scenes=sequential_scenes(45), max_dates_per_batch=20)
    assert len(plan.unique_dates) == 45
    assert [batch.date_count for batch in plan.batches] == [20, 20, 5]
    assert sum(batch.date_count for batch in plan.batches) == 45
    assert all(len(batch.dates) == batch.date_count for batch in plan.batches)


def test_request_bbox_is_buffered(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, buffer_degrees=0.5)
    assert plan.request_bbox.west == 109.0
    assert plan.request_bbox.east == 118.0
    assert plan.request_bbox.south == 19.5
    assert plan.request_bbox.north == 26.0
    assert all(batch.bbox == plan.request_bbox for batch in plan.batches)


def test_request_bbox_is_clamped(tmp_path: Path) -> None:
    aoi = make_processing(west=-179.99, east=-179.0, south=89.0, north=89.99)
    plan = build_plan(tmp_path, aoi=aoi, buffer_degrees=0.05)
    assert plan.request_bbox.west == -180.0
    assert plan.request_bbox.north == 90.0


def test_output_directory_uses_safe_name_and_layout(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, region_safe_name="guangdong_2024")
    parts = plan.output_directory.parts
    assert "guangdong_2024" in parts
    assert "05_atmosphere" in parts
    assert "gacos" in parts
    assert plan.output_directory.name == "requests"


def test_expected_file_patterns_include_ztd(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert "*.ztd" in plan.expected_file_patterns
    assert "*.ztd.rsc" in plan.expected_file_patterns


def test_manual_submission_required(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert plan.manual_submission_required is True
    report = validate_gacos_request_plan(plan)
    assert any(issue.code == GACOS_MANUAL_SUBMISSION_REQUIRED for issue in report.issues)


def test_plan_is_json_serializable(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, scenes=sequential_scenes(5))
    encoded = json.dumps(plan.to_dict())
    assert isinstance(encoded, str)
    assert "2023-01-01" in encoded


def test_report_ready_and_serializable(tmp_path: Path) -> None:
    report = validate_gacos_request_plan(build_plan(tmp_path))
    assert not report.has_errors
    assert any(issue.code == GACOS_PLAN_READY for issue in report.issues)
    assert isinstance(json.dumps(report.to_dict()), str)


def test_report_flags_plan_without_dates(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    plan.unique_dates = []
    plan.batches = []
    report = validate_gacos_request_plan(plan)
    assert report.has_errors
    assert any(issue.code == GACOS_NO_VALID_DATES for issue in report.issues)


def test_planning_creates_no_files(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    # Planning is offline: it must not create the output directory or any files.
    assert not plan.output_directory.exists()
    assert not any(tmp_path.iterdir())
