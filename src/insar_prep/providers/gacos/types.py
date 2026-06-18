"""Data structures for GACOS request planning and import checking (Tasks 012-013).

All models are JSON-serializable via the shared pydantic base model. GACOS
zenith-delay products must be requested and downloaded *manually* by the user
from the GACOS web service; these structures only describe *what* to request
(acquisition dates and a bounding box), *where* to later place the products the
user downloads, and *what* was actually found on disk. Nothing here contacts
GACOS, submits web forms, scrapes pages, drives a browser, downloads products,
or stores credentials.

Date-typed fields are annotated as ``datetime.date`` (module-qualified) on
purpose: a field literally named ``date`` would otherwise shadow the bare
``date`` type when a default is present and break annotation evaluation.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from insar_prep.core.models import BBox, InsarBaseModel, generate_id
from insar_prep.quality.types import CheckSeverity


class GacosRequestBatch(InsarBaseModel):
    """One batch of acquisition dates the user submits to GACOS together."""

    batch_id: str = Field(default_factory=lambda: generate_id("gacos_batch"))
    dates: list[datetime.date] = Field(default_factory=list)
    bbox: BBox
    date_count: int = 0
    notes: str = ""


class GacosRequestPlan(InsarBaseModel):
    """A planned (manually submitted) GACOS request for one region."""

    plan_id: str = Field(default_factory=lambda: generate_id("gacos_plan"))
    region_id: str
    region_safe_name: str
    processing_bbox: BBox
    request_bbox: BBox
    buffer_degrees: float
    unique_dates: list[datetime.date] = Field(default_factory=list)
    batches: list[GacosRequestBatch] = Field(default_factory=list)
    manual_submission_required: bool = True
    output_directory: Path
    expected_file_patterns: list[str] = Field(default_factory=list)
    # Provenance kept so ``validate_gacos_request_plan`` can work from the plan
    # alone (no scene list is re-passed to validation).
    max_dates_per_batch: int = 20
    scene_count: int = 0
    scene_missing_date_count: int = 0
    notes: str = ""


class GacosPlanningIssue(InsarBaseModel):
    """A single GACOS-planning finding."""

    code: str
    severity: CheckSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class GacosPlanningReport(InsarBaseModel):
    """The validation result for a GACOS request plan."""

    plan: GacosRequestPlan | None = None
    issues: list[GacosPlanningIssue] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)


class GacosProductFile(InsarBaseModel):
    """A scanned GACOS product pair (``.ztd`` + ``.ztd.rsc``) for one date.

    Paths and sizes are recorded for reporting only; file *contents* (``.ztd``
    rasters, ``.rsc`` spatial extents) are never parsed in Task 013.
    """

    date: datetime.date
    ztd_path: Path | None = None
    rsc_path: Path | None = None
    has_ztd: bool = False
    has_rsc: bool = False
    ztd_size_bytes: int | None = None
    rsc_size_bytes: int | None = None


class GacosImportIssue(InsarBaseModel):
    """A single GACOS import-check finding."""

    code: str
    severity: CheckSeverity
    message: str
    date: datetime.date | None = None
    file_path: Path | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GacosImportCheckReport(InsarBaseModel):
    """The result of checking a local GACOS product directory against a plan."""

    expected_dates: list[datetime.date] = Field(default_factory=list)
    found_dates: list[datetime.date] = Field(default_factory=list)
    missing_dates: list[datetime.date] = Field(default_factory=list)
    extra_dates: list[datetime.date] = Field(default_factory=list)
    products: list[GacosProductFile] = Field(default_factory=list)
    issues: list[GacosImportIssue] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
