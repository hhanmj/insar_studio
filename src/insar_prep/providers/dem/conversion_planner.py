"""DEM vertical-datum conversion planning (Task 011).

Plans (but never executes) DEM vertical-datum conversions. It does not call
GDAL/rasterio/pyproj, does not download geoids, does not read or write DEM
rasters, and does not access the network. Outputs are serializable plans.
"""

from __future__ import annotations

from insar_prep.core.enums import VerticalDatum
from insar_prep.core.logging import get_logger
from insar_prep.core.naming import validate_sarscape_ready_path
from insar_prep.providers.dem.types import (
    DemConversionIssue,
    DemConversionPlan,
    DemConversionReport,
    DemConversionStep,
    DemConversionStepType,
    DemRequestPlan,
)
from insar_prep.quality.types import CheckSeverity

logger = get_logger("providers.dem.conversion_planner")

DEM_CONVERSION_NOT_REQUIRED = "DEM_CONVERSION_NOT_REQUIRED"
DEM_GEOID_REQUIRED = "DEM_GEOID_REQUIRED"
DEM_GEOID_UNKNOWN = "DEM_GEOID_UNKNOWN"
DEM_VERTICAL_DATUM_UNKNOWN = "DEM_VERTICAL_DATUM_UNKNOWN"
DEM_SARSCAPE_READY_INVALID = "DEM_SARSCAPE_READY_INVALID"
DEM_MANUAL_REVIEW_REQUIRED = "DEM_MANUAL_REVIEW_REQUIRED"
DEM_CONVERSION_PLAN_READY = "DEM_CONVERSION_PLAN_READY"

_GEOID_SOURCES = {VerticalDatum.EGM96, VerticalDatum.EGM2008, VerticalDatum.ORTHOMETRIC}


def requires_geoid_conversion(
    source_vertical_datum: VerticalDatum, target_vertical_datum: VerticalDatum
) -> bool:
    """Return True if converting between these datums needs a geoid model."""
    if source_vertical_datum == target_vertical_datum:
        return False
    pair = {source_vertical_datum, target_vertical_datum}
    return VerticalDatum.WGS84_ELLIPSOID in pair and bool(pair & _GEOID_SOURCES)


def suggest_geoid_model(
    source_vertical_datum: VerticalDatum, target_vertical_datum: VerticalDatum
) -> str | None:
    """Suggest a geoid model name, or None when one cannot be inferred."""
    if not requires_geoid_conversion(source_vertical_datum, target_vertical_datum):
        return None
    pair = {source_vertical_datum, target_vertical_datum}
    if VerticalDatum.EGM96 in pair:
        return "EGM96"
    if VerticalDatum.EGM2008 in pair:
        return "EGM2008"
    return None


def _build_steps(
    request_plan: DemRequestPlan,
    *,
    requires_conversion: bool,
    requires_geoid: bool,
    geoid_model: str | None,
) -> list[DemConversionStep]:
    source = request_plan.source_vertical_datum
    target = request_plan.target_vertical_datum
    common = {"source_vertical_datum": source, "target_vertical_datum": target}

    if VerticalDatum.UNKNOWN in (source, target):
        return [
            DemConversionStep(
                step_type=DemConversionStepType.MANUAL_REVIEW_REQUIRED,
                description="vertical datum is unknown; specify it before conversion",
                input_path=request_plan.raw_dem_path,
                output_path=request_plan.sarscape_ready_dem_path,
                **common,
            )
        ]
    if not requires_conversion:
        return [
            DemConversionStep(
                step_type=DemConversionStepType.NO_OP,
                description="source already equals target vertical datum",
                input_path=request_plan.raw_dem_path,
                output_path=request_plan.raw_dem_path,
                **common,
            ),
            DemConversionStep(
                step_type=DemConversionStepType.COPY_TO_SARSCAPE_READY,
                description="export raw ellipsoid DEM to the SARscape-ready ENVI _dem raster",
                input_path=request_plan.raw_dem_path,
                output_path=request_plan.sarscape_ready_dem_path,
                **common,
            ),
        ]
    if requires_geoid and geoid_model is not None:
        return [
            DemConversionStep(
                step_type=DemConversionStepType.VERTICAL_DATUM_CONVERSION,
                description=f"convert {source.value} to {target.value} using {geoid_model}",
                input_path=request_plan.raw_dem_path,
                output_path=request_plan.ellipsoid_dem_path,
                requires_geoid=True,
                geoid_model=geoid_model,
                **common,
            ),
            DemConversionStep(
                step_type=DemConversionStepType.COPY_TO_SARSCAPE_READY,
                description="export ellipsoid DEM to the SARscape-ready ENVI _dem raster",
                input_path=request_plan.ellipsoid_dem_path,
                output_path=request_plan.sarscape_ready_dem_path,
                **common,
            ),
        ]
    return [
        DemConversionStep(
            step_type=DemConversionStepType.MANUAL_REVIEW_REQUIRED,
            description="conversion needs an explicit geoid model",
            input_path=request_plan.raw_dem_path,
            output_path=request_plan.sarscape_ready_dem_path,
            requires_geoid=True,
            **common,
        )
    ]


def create_dem_conversion_plan(request_plan: DemRequestPlan) -> DemConversionPlan:
    """Build an offline DEM vertical-datum conversion plan."""
    source = request_plan.source_vertical_datum
    target = request_plan.target_vertical_datum
    requires_conversion = source != target
    requires_geoid = requires_geoid_conversion(source, target)
    geoid_model = suggest_geoid_model(source, target)
    steps = _build_steps(
        request_plan,
        requires_conversion=requires_conversion,
        requires_geoid=requires_geoid,
        geoid_model=geoid_model,
    )
    logger.debug("created DEM conversion plan for region %s", request_plan.region_safe_name)
    return DemConversionPlan(
        region_id=request_plan.region_id,
        region_safe_name=request_plan.region_safe_name,
        dataset=request_plan.dataset,
        source_vertical_datum=source,
        target_vertical_datum=target,
        raw_dem_path=request_plan.raw_dem_path,
        ellipsoid_dem_path=request_plan.ellipsoid_dem_path,
        sarscape_ready_dem_path=request_plan.sarscape_ready_dem_path,
        steps=steps,
        requires_conversion=requires_conversion,
        requires_geoid=requires_geoid,
    )


def validate_dem_conversion_plan(plan: DemConversionPlan) -> DemConversionReport:
    """Validate a DEM conversion plan and return a structured report."""
    issues: list[DemConversionIssue] = []
    source = plan.source_vertical_datum
    target = plan.target_vertical_datum

    if VerticalDatum.UNKNOWN in (source, target):
        issues.append(
            DemConversionIssue(
                code=DEM_VERTICAL_DATUM_UNKNOWN,
                severity=CheckSeverity.ERROR,
                message="DEM vertical datum is unknown",
            )
        )
    elif not plan.requires_conversion:
        issues.append(
            DemConversionIssue(
                code=DEM_CONVERSION_NOT_REQUIRED,
                severity=CheckSeverity.INFO,
                message="source vertical datum already equals target",
            )
        )
    elif plan.requires_geoid:
        geoid_model = suggest_geoid_model(source, target)
        if geoid_model is not None:
            issues.append(
                DemConversionIssue(
                    code=DEM_GEOID_REQUIRED,
                    severity=CheckSeverity.INFO,
                    message=f"conversion requires geoid model {geoid_model}",
                )
            )
        else:
            issues.append(
                DemConversionIssue(
                    code=DEM_GEOID_UNKNOWN,
                    severity=CheckSeverity.WARNING,
                    message="conversion requires a geoid model that cannot be inferred",
                )
            )
            issues.append(
                DemConversionIssue(
                    code=DEM_MANUAL_REVIEW_REQUIRED,
                    severity=CheckSeverity.WARNING,
                    message="select an explicit geoid model before converting",
                )
            )

    name = plan.sarscape_ready_dem_path.name
    name_invalid = not name.endswith("_dem") or name.endswith("_ellipsoid_dem")
    try:
        validate_sarscape_ready_path(plan.sarscape_ready_dem_path)
    except ValueError:
        name_invalid = True
    if name_invalid:
        issues.append(
            DemConversionIssue(
                code=DEM_SARSCAPE_READY_INVALID,
                severity=CheckSeverity.ERROR,
                message=f"invalid SARscape-ready DEM path {name!r}",
            )
        )

    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in issues)
    if not has_errors:
        issues.append(
            DemConversionIssue(
                code=DEM_CONVERSION_PLAN_READY,
                severity=CheckSeverity.INFO,
                message="DEM conversion plan is ready",
            )
        )
    summary = {
        "region_safe_name": plan.region_safe_name,
        "source_vertical_datum": source.value,
        "target_vertical_datum": target.value,
        "requires_conversion": plan.requires_conversion,
        "requires_geoid": plan.requires_geoid,
        "step_count": len(plan.steps),
    }
    logger.debug("validated DEM conversion plan for region %s", plan.region_safe_name)
    return DemConversionReport(
        plan=plan,
        issues=issues,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )
