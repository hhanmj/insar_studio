"""Tests for the DEM request planner (Task 010)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from insar_prep.core.enums import TaskStatus, TaskType
from insar_prep.core.exceptions import DemProcessingError, InputValidationError
from insar_prep.core.models import Aoi
from insar_prep.processing.aoi import make_download_aoi, make_processing_aoi_from_bbox
from insar_prep.providers.dem.planner import (
    DEM_DATASET_UNSUPPORTED,
    DEM_PLAN_READY,
    create_dem_download_task,
    create_dem_request_plan,
    validate_dem_request_plan,
)


def make_processing(
    west: float = 109.5,
    east: float = 117.5,
    south: float = 20.0,
    north: float = 25.5,
) -> Aoi:
    return make_processing_aoi_from_bbox(west, east, south, north)


def build_plan(
    tmp_path: Path, *, region_safe_name: str = "shiliushubao", aoi: Aoi | None = None, **kwargs
):
    return create_dem_request_plan(
        region_id="r1",
        region_safe_name=region_safe_name,
        processing_aoi=aoi or make_processing(),
        output_root=tmp_path,
        **kwargs,
    )


def test_default_plan(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert plan.dataset == "COP30"
    assert plan.provider == "OPENTOPOGRAPHY"
    assert plan.sarscape_ready_dem_path.name == "shiliushubao_dem.tif"


def test_invalid_region_safe_name_raises(tmp_path: Path) -> None:
    with pytest.raises(DemProcessingError):
        build_plan(tmp_path, region_safe_name="Shiliushubao-Area")


def test_negative_buffer_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, buffer_degrees=-0.1)


def test_buffer_expands_bbox(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, buffer_degrees=0.5)
    assert plan.request_bbox.west == 109.0
    assert plan.request_bbox.east == 118.0
    assert plan.request_bbox.south == 19.5
    assert plan.request_bbox.north == 26.0


def test_bbox_is_clamped(tmp_path: Path) -> None:
    aoi = make_processing(west=-179.99, east=-179.0, south=89.0, north=89.99)
    plan = build_plan(tmp_path, aoi=aoi, buffer_degrees=0.05)
    assert plan.request_bbox.west == -180.0
    assert plan.request_bbox.north == 90.0


def test_sarscape_ready_dem_name(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, region_safe_name="guangdong_2024")
    assert plan.sarscape_ready_dem_path.name == "guangdong_2024_dem.tif"


def test_three_paths_differ(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert plan.raw_dem_path != plan.ellipsoid_dem_path
    assert plan.ellipsoid_dem_path != plan.sarscape_ready_dem_path
    assert "raw" in plan.raw_dem_path.parts
    assert "ellipsoid" in plan.ellipsoid_dem_path.parts


def test_ellipsoid_is_not_sarscape_ready(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert "_ellipsoid" in plan.ellipsoid_dem_path.name
    assert not plan.sarscape_ready_dem_path.name.endswith("_ellipsoid.tif")
    assert plan.sarscape_ready_dem_path.name.endswith("_dem.tif")


def test_download_task_planned_not_executed(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    task = plan.download_task
    assert task is not None
    assert task.status is TaskStatus.PENDING
    assert task.task_type is TaskType.DOWNLOAD_DEM
    assert task.input["dataset"] == plan.dataset
    assert task.local_path == plan.raw_dem_path


def test_create_download_task_standalone(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    task = create_dem_download_task(plan)
    assert task.task_type is TaskType.DOWNLOAD_DEM
    assert task.status is TaskStatus.PENDING


def test_plan_is_json_serializable(tmp_path: Path) -> None:
    plan = build_plan(tmp_path)
    assert isinstance(json.dumps(plan.to_dict()), str)


def test_report_ready_and_serializable(tmp_path: Path) -> None:
    report = validate_dem_request_plan(build_plan(tmp_path))
    assert not report.has_errors
    assert any(issue.code == DEM_PLAN_READY for issue in report.issues)
    assert isinstance(json.dumps(report.to_dict()), str)


def test_unsupported_dataset_flagged(tmp_path: Path) -> None:
    report = validate_dem_request_plan(build_plan(tmp_path, dataset="FOODEM"))
    assert report.has_errors
    assert any(issue.code == DEM_DATASET_UNSUPPORTED for issue in report.issues)


def test_non_processing_aoi_raises(tmp_path: Path) -> None:
    download_aoi = make_download_aoi(make_processing(), 0.05)
    with pytest.raises(InputValidationError):
        build_plan(tmp_path, aoi=download_aoi)
