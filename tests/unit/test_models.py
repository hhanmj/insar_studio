"""Tests for core data models (Task 002)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from insar_prep.core import (
    Aoi,
    AtmosphericProduct,
    BBox,
    DemProduct,
    DownloadTask,
    Job,
    Project,
    Region,
    Scene,
    Workspace,
)
from insar_prep.core.enums import (
    AoiSource,
    CoverageStatus,
    JobStatus,
    Provider,
    TargetSoftware,
    TaskStatus,
    TaskType,
)


def make_bbox() -> BBox:
    return BBox(west=109.5, east=117.5, south=20.0, north=25.5)


def make_region(**overrides: Any) -> Region:
    fields: dict[str, Any] = {
        "project_id": "proj_x",
        "region_name": "Guangdong",
        "region_safe_name": "guangdong",
        "region_root": "regions/guangdong",
        "aoi": Aoi(source=AoiSource.MANUAL_BBOX, bbox=make_bbox()),
    }
    fields.update(overrides)
    return Region(**fields)


def test_scene_defaults() -> None:
    scene = Scene()
    assert scene.download_status is TaskStatus.PENDING
    assert scene.asf_footprint_coverage is CoverageStatus.UNKNOWN
    assert scene.product_type.value == "SLC"
    assert scene.scene_id.startswith("scene_")


def test_aoi_buffer_defaults() -> None:
    aoi = Aoi(source=AoiSource.MANUAL_BBOX, bbox=make_bbox())
    assert aoi.buffer.dem == 0.02
    assert aoi.buffer.gacos == 0.05
    assert aoi.buffer.era5 == 0.25


def test_project_defaults() -> None:
    project = Project(
        workspace_id="ws_x",
        project_name="South China",
        safe_name="south_china_insar_2026",
        project_root="projects/sc",
    )
    assert project.target_software is TargetSoftware.SARSCAPE
    assert project.regions == []
    assert project.jobs == []
    assert project.project_id.startswith("proj_")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        BBox(west=0.0, east=1.0, south=0.0, north=1.0, nonsense=123)


def test_bbox_ordering_invalid() -> None:
    with pytest.raises(ValidationError):
        BBox(west=10.0, east=5.0, south=0.0, north=1.0)
    with pytest.raises(ValidationError):
        BBox(west=0.0, east=1.0, south=10.0, north=5.0)


def test_bbox_range_invalid() -> None:
    with pytest.raises(ValidationError):
        BBox(west=-200.0, east=1.0, south=0.0, north=1.0)
    with pytest.raises(ValidationError):
        BBox(west=0.0, east=1.0, south=-100.0, north=1.0)


def test_safe_name_valid() -> None:
    for name in ("guangdong", "guangdong_2024", "south_china_insar_2026"):
        region = make_region(region_safe_name=name)
        assert region.region_safe_name == name


def test_safe_name_invalid() -> None:
    for name in ("Guangdong", "guangdong-2024", "guangdong__2024", "_guangdong", "guangdong_"):
        with pytest.raises(ValidationError):
            make_region(region_safe_name=name)


def test_invalid_enum_rejected() -> None:
    with pytest.raises(ValidationError):
        DownloadTask(
            job_id="j",
            region_id="r",
            provider="NOT_A_PROVIDER",
            task_type=TaskType.DOWNLOAD_SLC,
        )


def test_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        # workspace_id is required.
        Project(project_name="x", safe_name="x", project_root="projects/x")


def test_dem_sarscape_suffix_valid() -> None:
    dem = DemProduct(
        region_id="r1",
        source=Provider.OPENTOPOGRAPHY,
        dataset="COP30",
        sarscape_ready_path="06_sarscape_ready/DEM/guangdong_dem.tif",
    )
    assert dem.sarscape_ready_path is not None
    assert dem.sarscape_ready_path.name == "guangdong_dem.tif"


def test_dem_sarscape_suffix_invalid() -> None:
    with pytest.raises(ValidationError):
        DemProduct(
            region_id="r1",
            source=Provider.OPENTOPOGRAPHY,
            dataset="COP30",
            sarscape_ready_path="06_sarscape_ready/DEM/guangdong_ellipsoid.tif",
        )


def test_download_task_progress_out_of_range() -> None:
    with pytest.raises(ValidationError):
        DownloadTask(
            job_id="j",
            region_id="r",
            provider=Provider.ASF,
            task_type=TaskType.DOWNLOAD_SLC,
            progress=150.0,
        )


def test_full_hierarchy_builds() -> None:
    scene = Scene(platform="S1A", acquisition_datetime=datetime(2024, 1, 1, tzinfo=UTC))
    dem = DemProduct(region_id="r1", source=Provider.OPENTOPOGRAPHY, dataset="COP30")
    atmo = AtmosphericProduct(
        region_id="r1",
        provider=Provider.GACOS,
        method="request_assistant",
        date=date(2024, 1, 1),
    )
    region = make_region(
        region_id="r1",
        scenes=[scene],
        dem_products=[dem],
        atmospheric_products=[atmo],
    )
    task = DownloadTask(
        job_id="job1",
        region_id="r1",
        provider=Provider.ASF,
        task_type=TaskType.DOWNLOAD_SLC,
    )
    job = Job(job_id="job1", project_id="proj1", name="download guangdong", tasks=[task])
    project = Project(
        project_id="proj1",
        workspace_id="ws1",
        project_name="South China",
        safe_name="south_china",
        project_root="projects/sc",
        regions=[region],
        jobs=[job],
    )
    workspace = Workspace(workspace_root="D:/InSAR_Workspace", projects=[project])

    assert workspace.projects[0].regions[0].scenes[0].platform.value == "S1A"
    assert workspace.projects[0].jobs[0].tasks[0].task_type is TaskType.DOWNLOAD_SLC
    assert workspace.projects[0].jobs[0].status is JobStatus.NOT_STARTED
    assert len(workspace.projects[0].regions[0].atmospheric_products) == 1
