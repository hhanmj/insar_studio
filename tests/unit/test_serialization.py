"""Tests for JSON serialization helpers (Task 002, JSON only)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

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
from insar_prep.core.enums import AoiSource, Provider, TaskType
from insar_prep.core.serialization import (
    load_json,
    model_from_json,
    model_to_json,
    save_json,
)


def build_workspace() -> Workspace:
    scene = Scene(platform="S1A", acquisition_datetime=datetime(2024, 1, 1, tzinfo=UTC))
    dem = DemProduct(
        region_id="r1",
        source=Provider.OPENTOPOGRAPHY,
        dataset="COP30",
        sarscape_ready_path="06_sarscape_ready/DEM/guangdong_dem",
    )
    atmo = AtmosphericProduct(
        region_id="r1",
        provider=Provider.GACOS,
        method="request_assistant",
        date=date(2024, 1, 1),
    )
    region = Region(
        region_id="r1",
        project_id="proj1",
        region_name="Guangdong",
        region_safe_name="guangdong",
        region_root="regions/guangdong",
        aoi=Aoi(
            source=AoiSource.MANUAL_BBOX,
            bbox=BBox(west=109.5, east=117.5, south=20.0, north=25.5),
        ),
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
    job = Job(job_id="job1", project_id="proj1", name="download", tasks=[task])
    project = Project(
        project_id="proj1",
        workspace_id="ws1",
        project_name="South China",
        safe_name="south_china",
        project_root="projects/sc",
        regions=[region],
        jobs=[job],
    )
    return Workspace(workspace_id="ws1", workspace_root="D:/InSAR_Workspace", projects=[project])


def test_json_roundtrip_workspace() -> None:
    workspace = build_workspace()
    restored = model_from_json(Workspace, model_to_json(workspace))
    assert restored == workspace


def test_dump_contains_only_json_primitives() -> None:
    workspace = build_workspace()
    data = workspace.to_dict()
    # Must serialize via plain json with no custom encoder.
    assert isinstance(json.dumps(data), str)
    scene = data["projects"][0]["regions"][0]["scenes"][0]
    assert isinstance(scene["acquisition_datetime"], str)  # datetime -> ISO string
    task = data["projects"][0]["jobs"][0]["tasks"][0]
    assert task["task_type"] == "DOWNLOAD_SLC"  # enum -> plain string
    assert isinstance(data["workspace_root"], str)  # Path -> string


def test_save_and_load_json(tmp_path: Path) -> None:
    workspace = build_workspace()
    path = tmp_path / "workspace.json"
    saved = save_json(workspace, path)
    assert saved.exists()
    assert load_json(Workspace, path) == workspace


def test_individual_models_roundtrip() -> None:
    models = [
        BBox(west=0.0, east=1.0, south=0.0, north=1.0),
        Scene(platform="S1A"),
        DownloadTask(
            job_id="j",
            region_id="r",
            provider=Provider.ASF,
            task_type=TaskType.DOWNLOAD_SLC,
        ),
        AtmosphericProduct(
            region_id="r",
            provider=Provider.GACOS,
            method="request_assistant",
            date=date(2024, 1, 1),
        ),
    ]
    for model in models:
        restored = model_from_json(type(model), model_to_json(model))
        assert restored == model
