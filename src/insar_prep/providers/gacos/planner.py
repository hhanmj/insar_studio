"""GACOS request planning (Task 012).

Builds and validates *offline* GACOS request plans: which acquisition dates and
which bounding box the user must submit manually to the GACOS web service, and
where to place the products they later download. This module never contacts
GACOS, submits its web form, scrapes pages, bypasses request limits, downloads
products, drives a browser, reads accounts, or stores credentials.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from insar_prep.core.enums import AoiRole
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import Aoi, Scene
from insar_prep.providers.gacos.types import (
    GacosPlanningIssue,
    GacosPlanningReport,
    GacosRequestBatch,
    GacosRequestPlan,
)
from insar_prep.quality.types import CheckSeverity

logger = get_logger("providers.gacos.planner")

GACOS_NO_SCENES = "GACOS_NO_SCENES"
GACOS_NO_VALID_DATES = "GACOS_NO_VALID_DATES"
GACOS_SCENE_DATE_MISSING = "GACOS_SCENE_DATE_MISSING"
GACOS_BUFFER_INVALID = "GACOS_BUFFER_INVALID"
GACOS_BATCH_SIZE_INVALID = "GACOS_BATCH_SIZE_INVALID"
GACOS_PLAN_READY = "GACOS_PLAN_READY"
GACOS_MANUAL_SUBMISSION_REQUIRED = "GACOS_MANUAL_SUBMISSION_REQUIRED"

# Region-relative output layout for products the user downloads manually.
GACOS_REQUESTS_SUBDIR = ("05_atmosphere", "gacos", "requests")
GACOS_EXPECTED_FILE_PATTERNS = ["*.ztd", "*.ztd.rsc", "YYYYMMDD.ztd", "YYYYMMDD.ztd.rsc"]


def extract_gacos_dates_from_scenes(scenes: list[Scene]) -> list[date]:
    """Return sorted, de-duplicated acquisition dates from ``scenes``.

    Scenes without an ``acquisition_datetime`` cannot contribute a date and are
    skipped. Extraction is purely in-memory and never touches the network.
    """
    unique: set[date] = set()
    for scene in scenes:
        if scene.acquisition_datetime is not None:
            unique.add(scene.acquisition_datetime.date())
    return sorted(unique)


def _chunk_dates(dates: list[date], max_dates_per_batch: int) -> list[list[date]]:
    return [
        dates[start : start + max_dates_per_batch]
        for start in range(0, len(dates), max_dates_per_batch)
    ]


def create_gacos_request_plan(
    *,
    region_id: str,
    region_safe_name: str,
    processing_aoi: Aoi,
    scenes: list[Scene],
    output_root: Path | str,
    buffer_degrees: float = 0.05,
    max_dates_per_batch: int = 20,
) -> GacosRequestPlan:
    """Build an offline GACOS request plan for one region's Processing AOI."""
    if not scenes:
        raise InputValidationError(
            "GACOS planning requires at least one scene", code=ErrorCode.GAC001
        )
    if processing_aoi.role is not AoiRole.PROCESSING_AOI:
        raise InputValidationError(
            "GACOS planning requires a Processing AOI", code=ErrorCode.AOI001
        )
    if processing_aoi.bbox is None:
        raise InputValidationError("processing AOI has no bbox", code=ErrorCode.AOI001)
    if buffer_degrees < 0:
        raise InputValidationError("buffer_degrees must be non-negative", code=ErrorCode.AOI001)
    if max_dates_per_batch < 1:
        raise InputValidationError("max_dates_per_batch must be >= 1", code=ErrorCode.AOI001)

    processing_bbox = processing_aoi.bbox
    request_bbox = processing_bbox.buffer(buffer_degrees)
    unique_dates = extract_gacos_dates_from_scenes(scenes)
    scene_missing = sum(1 for scene in scenes if scene.acquisition_datetime is None)

    batches = [
        GacosRequestBatch(dates=list(chunk), bbox=request_bbox, date_count=len(chunk))
        for chunk in _chunk_dates(unique_dates, max_dates_per_batch)
    ]
    output_directory = Path(output_root).joinpath(region_safe_name, *GACOS_REQUESTS_SUBDIR)

    plan = GacosRequestPlan(
        region_id=region_id,
        region_safe_name=region_safe_name,
        processing_bbox=processing_bbox,
        request_bbox=request_bbox,
        buffer_degrees=buffer_degrees,
        unique_dates=unique_dates,
        batches=batches,
        manual_submission_required=True,
        output_directory=output_directory,
        expected_file_patterns=list(GACOS_EXPECTED_FILE_PATTERNS),
        max_dates_per_batch=max_dates_per_batch,
        scene_count=len(scenes),
        scene_missing_date_count=scene_missing,
    )
    log_event(
        logger,
        EventType.GACOS_BATCH_CREATED,
        f"planned {len(batches)} GACOS batch(es) for region {region_safe_name}",
        module="providers.gacos.planner",
        region_id=region_id,
        payload={"date_count": len(unique_dates), "batch_count": len(batches)},
    )
    logger.debug("created GACOS request plan for region %s", region_safe_name)
    return plan


def validate_gacos_request_plan(plan: GacosRequestPlan) -> GacosPlanningReport:
    """Validate a GACOS request plan and return a structured report."""
    issues: list[GacosPlanningIssue] = []

    if plan.scene_count <= 0:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_NO_SCENES,
                severity=CheckSeverity.ERROR,
                message="no scenes were provided for GACOS planning",
            )
        )
    if plan.buffer_degrees < 0:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_BUFFER_INVALID,
                severity=CheckSeverity.ERROR,
                message="buffer_degrees must be non-negative",
            )
        )
    if plan.max_dates_per_batch < 1:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_BATCH_SIZE_INVALID,
                severity=CheckSeverity.ERROR,
                message="max_dates_per_batch must be >= 1",
            )
        )
    if not plan.unique_dates:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_NO_VALID_DATES,
                severity=CheckSeverity.ERROR,
                message="no valid acquisition dates were found",
            )
        )
    elif sum(batch.date_count for batch in plan.batches) != len(plan.unique_dates):
        issues.append(
            GacosPlanningIssue(
                code=GACOS_BATCH_SIZE_INVALID,
                severity=CheckSeverity.ERROR,
                message="batched date count does not match the unique date count",
            )
        )
    if plan.scene_missing_date_count > 0:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_SCENE_DATE_MISSING,
                severity=CheckSeverity.WARNING,
                message=f"{plan.scene_missing_date_count} scene(s) skipped: no acquisition date",
            )
        )
    if plan.manual_submission_required:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_MANUAL_SUBMISSION_REQUIRED,
                severity=CheckSeverity.INFO,
                message="GACOS products must be requested and downloaded manually by the user",
            )
        )

    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in issues)
    if not has_errors:
        issues.append(
            GacosPlanningIssue(
                code=GACOS_PLAN_READY,
                severity=CheckSeverity.INFO,
                message="GACOS request plan is ready",
            )
        )
    summary = {
        "region_safe_name": plan.region_safe_name,
        "unique_date_count": len(plan.unique_dates),
        "batch_count": len(plan.batches),
        "scene_count": plan.scene_count,
        "scene_missing_date_count": plan.scene_missing_date_count,
        "output_directory": str(plan.output_directory),
    }
    logger.debug("validated GACOS plan for region %s", plan.region_safe_name)
    return GacosPlanningReport(
        plan=plan,
        issues=issues,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )
