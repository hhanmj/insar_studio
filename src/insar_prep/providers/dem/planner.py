"""DEM request planning (Task 010).

Builds and validates offline DEM acquisition plans. It does NOT call the
OpenTopography API, download DEMs, read rasters, convert vertical datums, or
contact SARscape. Created download tasks are planning artifacts only.
"""

from __future__ import annotations

from pathlib import Path

from insar_prep.core.enums import (
    AoiRole,
    DemDataset,
    Provider,
    TaskStatus,
    TaskType,
    VerticalDatum,
)
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import DemProcessingError, InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.core.models import Aoi, DownloadTask
from insar_prep.core.naming import (
    is_sarscape_safe_name,
    sarscape_safe_name,
    validate_sarscape_ready_path,
)
from insar_prep.providers.dem.types import (
    DemPlanningIssue,
    DemPlanningReport,
    DemProvider,
    DemRequestPlan,
)
from insar_prep.quality.types import CheckSeverity

logger = get_logger("providers.dem.planner")

DEM_BBOX_INVALID = "DEM_BBOX_INVALID"
DEM_BUFFER_INVALID = "DEM_BUFFER_INVALID"
DEM_DATASET_UNSUPPORTED = "DEM_DATASET_UNSUPPORTED"
DEM_PROVIDER_UNSUPPORTED = "DEM_PROVIDER_UNSUPPORTED"
DEM_SARSCAPE_NAME_INVALID = "DEM_SARSCAPE_NAME_INVALID"
DEM_VERTICAL_DATUM_UNKNOWN = "DEM_VERTICAL_DATUM_UNKNOWN"
DEM_PLAN_READY = "DEM_PLAN_READY"

_DEM_SOURCE_STEMS = {
    "SRTM_GL3": "SRTM90m",
    "SRTM_GL1": "SRTM30m",
    "SRTM_GL1_ELLIPSOIDAL": "SRTM30m",
    "AW3D30": "AW3D30m",
    "AW3D30_ELLIPSOIDAL": "AW3D30m",
    "COP90": "COP90m",
    "COP30": "COP30m",
    "NASADEM": "NASADEM",
}


def dem_source_stem(dataset: DemDataset | str) -> str:
    """Return the short output filename stem for a DEM source."""
    value = dataset.value if isinstance(dataset, DemDataset) else str(dataset)
    return _DEM_SOURCE_STEMS.get(value.upper(), sarscape_safe_name(value).upper())

_PROVIDER_TO_TASK_PROVIDER = {
    DemProvider.OPENTOPOGRAPHY.value: Provider.OPENTOPOGRAPHY,
    DemProvider.LOCAL.value: Provider.USER_LOCAL,
}


def create_dem_download_task(plan: DemRequestPlan) -> DownloadTask:
    """Create a planning-only DEM download task (PENDING, no network)."""
    bbox = plan.request_bbox
    return DownloadTask(
        job_id="",
        region_id=plan.region_id,
        provider=_PROVIDER_TO_TASK_PROVIDER.get(plan.provider, Provider.USER_LOCAL),
        task_type=TaskType.DOWNLOAD_DEM,
        status=TaskStatus.PENDING,
        local_path=plan.raw_dem_path,
        input={
            "dataset": plan.dataset,
            "provider": plan.provider,
            "bbox": [bbox.west, bbox.south, bbox.east, bbox.north],
        },
    )


def create_dem_request_plan(
    *,
    region_id: str,
    region_safe_name: str,
    processing_aoi: Aoi,
    output_root: Path | str,
    dataset: DemDataset | str = DemDataset.COP30,
    provider: DemProvider | str = DemProvider.OPENTOPOGRAPHY,
    buffer_degrees: float = 0.05,
    source_vertical_datum: VerticalDatum = VerticalDatum.EGM2008,
    target_vertical_datum: VerticalDatum = VerticalDatum.WGS84_ELLIPSOID,
) -> DemRequestPlan:
    """Build an offline DEM request plan for one region's Processing AOI."""
    if not is_sarscape_safe_name(region_safe_name):
        raise DemProcessingError(
            f"region_safe_name {region_safe_name!r} is not SARscape-safe", code=ErrorCode.DEM004
        )
    if processing_aoi.role is not AoiRole.PROCESSING_AOI:
        raise InputValidationError("DEM planning requires a Processing AOI", code=ErrorCode.AOI001)
    if processing_aoi.bbox is None:
        raise InputValidationError("processing AOI has no bbox", code=ErrorCode.AOI001)
    if buffer_degrees < 0:
        raise InputValidationError("buffer_degrees must be non-negative", code=ErrorCode.AOI001)

    dataset_value = dataset.value if isinstance(dataset, DemDataset) else str(dataset)
    provider_value = provider.value if isinstance(provider, DemProvider) else str(provider)
    processing_bbox = processing_aoi.bbox
    request_bbox = processing_bbox.buffer(buffer_degrees)

    dem_root = Path(output_root)
    source_stem = dem_source_stem(dataset_value)
    raw_dem_path = dem_root / f"{source_stem}.tif"
    ellipsoid_dem_path = dem_root / f"{source_stem}_ellipsoid.tif"
    sarscape_ready_dem_path = dem_root / f"{source_stem}_dem"
    validate_sarscape_ready_path(sarscape_ready_dem_path)

    plan = DemRequestPlan(
        region_id=region_id,
        region_safe_name=region_safe_name,
        provider=provider_value,
        dataset=dataset_value,
        request_bbox=request_bbox,
        processing_bbox=processing_bbox,
        buffer_degrees=buffer_degrees,
        source_vertical_datum=source_vertical_datum,
        target_vertical_datum=target_vertical_datum,
        raw_dem_path=raw_dem_path,
        ellipsoid_dem_path=ellipsoid_dem_path,
        sarscape_ready_dem_path=sarscape_ready_dem_path,
    )
    plan.download_task = create_dem_download_task(plan)
    logger.debug("created DEM request plan for region %s", region_safe_name)
    return plan


def validate_dem_request_plan(plan: DemRequestPlan) -> DemPlanningReport:
    """Validate a DEM request plan and return a structured report."""
    issues: list[DemPlanningIssue] = []
    valid_datasets = {dataset.value for dataset in DemDataset}
    valid_providers = {provider.value for provider in DemProvider}

    if plan.buffer_degrees < 0:
        issues.append(
            DemPlanningIssue(
                code=DEM_BUFFER_INVALID,
                severity=CheckSeverity.ERROR,
                message="buffer_degrees must be non-negative",
            )
        )
    bbox = plan.request_bbox
    in_range = -180.0 <= bbox.west < bbox.east <= 180.0 and -90.0 <= bbox.south < bbox.north <= 90.0
    if not in_range:
        issues.append(
            DemPlanningIssue(
                code=DEM_BBOX_INVALID,
                severity=CheckSeverity.ERROR,
                message="request bbox is out of range",
            )
        )
    if plan.dataset not in valid_datasets:
        issues.append(
            DemPlanningIssue(
                code=DEM_DATASET_UNSUPPORTED,
                severity=CheckSeverity.ERROR,
                message=f"unsupported DEM dataset {plan.dataset!r}",
            )
        )
    if plan.provider not in valid_providers:
        issues.append(
            DemPlanningIssue(
                code=DEM_PROVIDER_UNSUPPORTED,
                severity=CheckSeverity.ERROR,
                message=f"unsupported DEM provider {plan.provider!r}",
            )
        )
    name = plan.sarscape_ready_dem_path.name
    name_invalid = (
        not name.endswith("_dem")
        or name.endswith("_ellipsoid_dem")
        or not is_sarscape_safe_name(plan.region_safe_name)
    )
    if name_invalid:
        issues.append(
            DemPlanningIssue(
                code=DEM_SARSCAPE_NAME_INVALID,
                severity=CheckSeverity.ERROR,
                message=f"invalid SARscape-ready DEM name {name!r}",
            )
        )
    if VerticalDatum.UNKNOWN in (plan.source_vertical_datum, plan.target_vertical_datum):
        issues.append(
            DemPlanningIssue(
                code=DEM_VERTICAL_DATUM_UNKNOWN,
                severity=CheckSeverity.WARNING,
                message="DEM vertical datum is unknown",
            )
        )

    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in issues)
    if not has_errors:
        issues.append(
            DemPlanningIssue(
                code=DEM_PLAN_READY,
                severity=CheckSeverity.INFO,
                message="DEM request plan is ready",
            )
        )
    summary = {
        "region_safe_name": plan.region_safe_name,
        "dataset": plan.dataset,
        "provider": plan.provider,
        "buffer_degrees": plan.buffer_degrees,
        "sarscape_ready_dem": str(plan.sarscape_ready_dem_path),
    }
    logger.debug("validated DEM plan for region %s", plan.region_safe_name)
    return DemPlanningReport(
        plan=plan,
        issues=issues,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )
