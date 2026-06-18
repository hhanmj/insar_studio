"""Data structures for DEM request planning (Task 010).

All models are JSON-serializable via the shared pydantic base model. This module
reuses the core ``DemDataset`` and ``VerticalDatum`` enums.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from insar_prep.core.enums import VerticalDatum
from insar_prep.core.models import BBox, DownloadTask, InsarBaseModel, generate_id
from insar_prep.quality.types import CheckSeverity


class DemProvider(StrEnum):
    """Where a DEM is planned to come from."""

    OPENTOPOGRAPHY = "OPENTOPOGRAPHY"
    LOCAL = "LOCAL"
    UNKNOWN = "UNKNOWN"


class DemRequestPlan(InsarBaseModel):
    """A planned (not executed) DEM acquisition for one region."""

    plan_id: str = Field(default_factory=lambda: generate_id("dem_plan"))
    region_id: str
    region_safe_name: str
    provider: str
    dataset: str
    request_bbox: BBox
    processing_bbox: BBox
    buffer_degrees: float
    source_vertical_datum: VerticalDatum
    target_vertical_datum: VerticalDatum
    raw_dem_path: Path
    ellipsoid_dem_path: Path
    sarscape_ready_dem_path: Path
    download_task: DownloadTask | None = None
    notes: str = ""


class DemPlanningIssue(InsarBaseModel):
    """A single DEM-planning finding."""

    code: str
    severity: CheckSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DemPlanningReport(InsarBaseModel):
    """The validation result for a DEM request plan."""

    plan: DemRequestPlan | None = None
    issues: list[DemPlanningIssue] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
