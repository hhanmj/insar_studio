"""Data structures for DEM request planning (Task 010).

All models are JSON-serializable via the shared pydantic base model. This module
reuses the core ``DemDataset`` and ``VerticalDatum`` enums.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from insar_prep.core.enums import TaskStatus, VerticalDatum
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


class DemConversionStepType(StrEnum):
    """Types of planned DEM conversion steps (none are executed)."""

    VERTICAL_DATUM_CONVERSION = "VERTICAL_DATUM_CONVERSION"
    COPY_TO_SARSCAPE_READY = "COPY_TO_SARSCAPE_READY"
    NO_OP = "NO_OP"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class DemConversionStep(InsarBaseModel):
    """A single planned (not executed) DEM conversion step."""

    step_id: str = Field(default_factory=lambda: generate_id("dem_step"))
    step_type: DemConversionStepType
    description: str = ""
    input_path: Path | None = None
    output_path: Path | None = None
    source_vertical_datum: VerticalDatum
    target_vertical_datum: VerticalDatum
    requires_geoid: bool = False
    geoid_model: str | None = None
    status: TaskStatus = TaskStatus.PENDING


class DemConversionPlan(InsarBaseModel):
    """A planned DEM vertical-datum conversion for one region."""

    plan_id: str = Field(default_factory=lambda: generate_id("dem_conv"))
    region_id: str
    region_safe_name: str
    dataset: str
    source_vertical_datum: VerticalDatum
    target_vertical_datum: VerticalDatum
    raw_dem_path: Path
    ellipsoid_dem_path: Path
    sarscape_ready_dem_path: Path
    steps: list[DemConversionStep] = Field(default_factory=list)
    requires_conversion: bool = False
    requires_geoid: bool = False
    notes: str = ""


class DemConversionIssue(InsarBaseModel):
    """A single DEM-conversion-planning finding."""

    code: str
    severity: CheckSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DemConversionReport(InsarBaseModel):
    """The validation result for a DEM conversion plan."""

    plan: DemConversionPlan | None = None
    issues: list[DemConversionIssue] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
