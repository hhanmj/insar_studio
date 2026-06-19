"""Offline prepare-workflow manifest (Task 026).

Builds a flat, row-based ``manifest.csv`` that lists the inputs, plans, checks,
and outputs of one ``prepare`` run. The manifest is written next to the JSON +
Markdown report under ``07_reports``.

This module only *reuses* objects already produced by the ``prepare`` workflow:
it never re-parses ASF carts, re-scans orbit/GACOS directories, downloads, or
contacts any external service. Every cell is credential-masked via ``mask_text``
before it reaches disk, and all paths are written as strings.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import ReportError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import InsarBaseModel
from insar_prep.core.naming import is_sarscape_safe_name

if TYPE_CHECKING:
    from insar_prep.core.models import Scene
    from insar_prep.providers.dem.types import DemConversionReport, DemPlanningReport
    from insar_prep.providers.gacos.types import GacosImportCheckReport, GacosPlanningReport
    from insar_prep.providers.orbit.types import OrbitMatchReport
    from insar_prep.quality.types import SceneCheckReport
    from insar_prep.reporting.types import DataPreparationReport

logger = get_logger("reporting.manifest")

# Fixed CSV column order. Do not reorder: downstream readers rely on this header.
MANIFEST_COLUMNS = [
    "section",
    "item_type",
    "item_id",
    "item_name",
    "status",
    "path",
    "value",
    "notes",
]

MANIFEST_FILENAME_SUFFIX = "_manifest.csv"


class ManifestRow(InsarBaseModel):
    """One row of the prepare manifest (mirrors :data:`MANIFEST_COLUMNS`)."""

    section: str
    item_type: str
    item_id: str = ""
    item_name: str = ""
    status: str = ""
    path: str = ""
    value: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        """Return this row as a ``{column: value}`` dict for ``csv.DictWriter``."""
        return {column: getattr(self, column) for column in MANIFEST_COLUMNS}


def _as_str(value: object | None) -> str:
    """Render any path/value as a string; ``None`` becomes an empty string."""
    return "" if value is None else str(value)


def _bbox_text(bbox) -> str:
    return f"W{bbox.west},S{bbox.south},E{bbox.east},N{bbox.north}"


def _workflow_rows(report, region_id: str, region_safe_name: str) -> list[ManifestRow]:
    return [
        ManifestRow(
            section="workflow",
            item_type="cli_workflow",
            item_name="prepare",
            status="OK",
            value="prepare",
        ),
        ManifestRow(
            section="workflow",
            item_type="region",
            item_id=region_id,
            item_name=region_safe_name,
            status="OK",
            value=region_safe_name,
        ),
        ManifestRow(
            section="workflow",
            item_type="report_generated_at",
            item_name="report_generated_at",
            status="GENERATED",
            value=report.created_at.isoformat(),
        ),
        ManifestRow(
            section="workflow",
            item_type="overall_status",
            item_name="overall_status",
            status="OK",
            value=str(report.summary.get("overall_status", "")),
        ),
    ]


def _scene_status_by_id(scene_check_report) -> dict[str, str]:
    """Map ``scene_id`` to the worst per-scene check status (OK/WARNING/ERROR)."""
    rank = {"OK": 0, "INFO": 0, "WARNING": 1, "ERROR": 2}
    worst: dict[str, str] = {}
    if scene_check_report is None:
        return worst
    for issue in scene_check_report.issues:
        scene_id = issue.scene_id
        if not scene_id:
            continue
        severity = issue.severity.value
        status = "ERROR" if severity == "ERROR" else "WARNING" if severity == "WARNING" else "OK"
        if rank[status] > rank.get(worst.get(scene_id, "OK"), 0):
            worst[scene_id] = status
    return worst


def _scene_rows(scenes, scene_check_report) -> list[ManifestRow]:
    status_by_id = _scene_status_by_id(scene_check_report)
    rows: list[ManifestRow] = []
    for scene in scenes:
        date_str = (
            scene.acquisition_datetime.strftime("%Y%m%d")
            if scene.acquisition_datetime is not None
            else ""
        )
        value = "/".join(
            (
                scene.platform.value,
                scene.product_type.value,
                scene.beam_mode.value,
                scene.polarization.value,
            )
        )
        notes = (
            f"acquisition={date_str or 'unknown'}; "
            f"url={'present' if scene.url else 'missing'}; "
            f"local_path={'present' if scene.local_path else 'missing'}"
        )
        rows.append(
            ManifestRow(
                section="scene",
                item_type="scene",
                item_id=scene.scene_id,
                item_name=date_str or scene.scene_id,
                status=status_by_id.get(scene.scene_id, "OK"),
                path=_as_str(scene.local_path),
                value=value,
                notes=notes,
            )
        )
    if not rows:
        rows.append(
            ManifestRow(
                section="scene", item_type="scene", status="SKIPPED", notes="no scenes parsed"
            )
        )
    return rows


def _orbit_rows(orbit_match_report) -> list[ManifestRow]:
    if orbit_match_report is None:
        return [
            ManifestRow(
                section="orbit",
                item_type="orbit_match",
                status="SKIPPED",
                notes="--orbit-dir not provided",
            )
        ]
    rows: list[ManifestRow] = []
    for result in orbit_match_report.results:
        codes = "; ".join(issue.code for issue in result.issues)
        matched = result.matched_orbit
        if result.is_matched and matched is not None:
            rows.append(
                ManifestRow(
                    section="orbit",
                    item_type="orbit_match",
                    item_id=result.scene_id,
                    item_name=matched.file_name,
                    status="OK",
                    path=_as_str(matched.path),
                    value=matched.orbit_type.value,
                    notes=codes,
                )
            )
        else:
            rows.append(
                ManifestRow(
                    section="orbit",
                    item_type="orbit_match",
                    item_id=result.scene_id,
                    item_name="unmatched",
                    status="MISSING",
                    notes=codes,
                )
            )
    if not rows:
        rows.append(
            ManifestRow(
                section="orbit",
                item_type="orbit_match",
                status="SKIPPED",
                notes="no scenes to match",
            )
        )
    return rows


def _dem_rows(dem_planning_report, dem_conversion_report) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    plan = dem_planning_report.plan if dem_planning_report is not None else None
    if plan is not None:
        rows.append(
            ManifestRow(
                section="dem",
                item_type="dem_request_plan",
                item_id=plan.plan_id,
                item_name="raw_dem",
                status="PLANNED",
                path=_as_str(plan.raw_dem_path),
                value=f"{plan.provider}/{plan.dataset}",
                notes=f"request_bbox={_bbox_text(plan.request_bbox)}",
            )
        )
        rows.append(
            ManifestRow(
                section="dem",
                item_type="dem_request_plan",
                item_id=plan.plan_id,
                item_name="ellipsoid_dem",
                status="PLANNED",
                path=_as_str(plan.ellipsoid_dem_path),
                value=plan.target_vertical_datum.value,
            )
        )
        rows.append(
            ManifestRow(
                section="dem",
                item_type="dem_request_plan",
                item_id=plan.plan_id,
                item_name="sarscape_ready_dem",
                status="PLANNED",
                path=_as_str(plan.sarscape_ready_dem_path),
                value=plan.target_vertical_datum.value,
            )
        )
    conversion = dem_conversion_report.plan if dem_conversion_report is not None else None
    if conversion is not None:
        rows.append(
            ManifestRow(
                section="dem",
                item_type="dem_conversion_plan",
                item_id=conversion.plan_id,
                item_name="vertical_datum_conversion",
                status="PLANNED",
                path=_as_str(conversion.sarscape_ready_dem_path),
                value=(
                    f"{conversion.source_vertical_datum.value}"
                    f"->{conversion.target_vertical_datum.value}"
                ),
                notes=(
                    f"requires_conversion={conversion.requires_conversion}; "
                    f"requires_geoid={conversion.requires_geoid}"
                ),
            )
        )
    if not rows:
        rows.append(
            ManifestRow(
                section="dem",
                item_type="dem_request_plan",
                status="SKIPPED",
                notes="--dem-plan not provided",
            )
        )
    return rows


def _gacos_request_rows(gacos_planning_report) -> list[ManifestRow]:
    plan = gacos_planning_report.plan if gacos_planning_report is not None else None
    if plan is None:
        return [
            ManifestRow(
                section="gacos",
                item_type="gacos_request_date",
                status="SKIPPED",
                notes="--gacos-plan not provided",
            )
        ]
    rows = [
        ManifestRow(
            section="gacos",
            item_type="gacos_request_plan",
            item_id=plan.plan_id,
            item_name="gacos_request_plan",
            status="PLANNED",
            path=_as_str(plan.output_directory),
            value=f"{len(plan.unique_dates)} dates / {len(plan.batches)} batches",
            notes=f"manual_submission_required={plan.manual_submission_required}",
        )
    ]
    for day in plan.unique_dates:
        stamp = day.strftime("%Y%m%d")
        rows.append(
            ManifestRow(
                section="gacos",
                item_type="gacos_request_date",
                item_id=day.isoformat(),
                item_name=stamp,
                status="PLANNED",
                notes=f"expected {stamp}.ztd, {stamp}.ztd.rsc",
            )
        )
    return rows


def _gacos_import_rows(gacos_import_report) -> list[ManifestRow]:
    if gacos_import_report is None:
        return [
            ManifestRow(
                section="gacos",
                item_type="gacos_import_date",
                status="SKIPPED",
                notes="--gacos-import-dir not provided",
            )
        ]
    found = set(gacos_import_report.found_dates)
    missing = set(gacos_import_report.missing_dates)
    issues_by_date: dict[object, list] = {}
    for issue in gacos_import_report.issues:
        if issue.date is None:
            continue
        issues_by_date.setdefault(issue.date, []).append(issue)
    rows: list[ManifestRow] = []
    for day in gacos_import_report.expected_dates:
        issues = issues_by_date.get(day, [])
        codes = "; ".join(issue.code for issue in issues)
        if day in missing:
            status = "MISSING"
        elif any(issue.severity.value == "ERROR" for issue in issues):
            status = "ERROR"
        elif any(issue.severity.value == "WARNING" for issue in issues):
            status = "WARNING"
        elif day in found:
            status = "OK"
        else:
            status = "MISSING"
        rows.append(
            ManifestRow(
                section="gacos",
                item_type="gacos_import_date",
                item_id=day.isoformat(),
                item_name=day.strftime("%Y%m%d"),
                status=status,
                notes=codes,
            )
        )
    for day in gacos_import_report.extra_dates:
        codes = "; ".join(issue.code for issue in issues_by_date.get(day, [])) or "GACOS_EXTRA_DATE"
        rows.append(
            ManifestRow(
                section="gacos",
                item_type="gacos_import_date",
                item_id=day.isoformat(),
                item_name=day.strftime("%Y%m%d"),
                status="WARNING",
                notes=codes,
            )
        )
    return rows


def _report_rows(json_report_path, markdown_report_path, manifest_csv_path) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    if json_report_path is not None:
        rows.append(
            ManifestRow(
                section="report",
                item_type="json_report",
                item_name="json_report",
                status="GENERATED",
                path=_as_str(json_report_path),
            )
        )
    if markdown_report_path is not None:
        rows.append(
            ManifestRow(
                section="report",
                item_type="markdown_report",
                item_name="markdown_report",
                status="GENERATED",
                path=_as_str(markdown_report_path),
            )
        )
    if manifest_csv_path is not None:
        rows.append(
            ManifestRow(
                section="report",
                item_type="manifest_csv",
                item_name="manifest_csv",
                status="GENERATED",
                path=_as_str(manifest_csv_path),
            )
        )
    return rows


def build_manifest_rows(
    *,
    region_id: str,
    region_safe_name: str,
    report: DataPreparationReport,
    scenes: list[Scene],
    scene_check_report: SceneCheckReport | None = None,
    orbit_match_report: OrbitMatchReport | None = None,
    dem_planning_report: DemPlanningReport | None = None,
    dem_conversion_report: DemConversionReport | None = None,
    gacos_planning_report: GacosPlanningReport | None = None,
    gacos_import_report: GacosImportCheckReport | None = None,
    json_report_path: Path | str | None = None,
    markdown_report_path: Path | str | None = None,
    manifest_csv_path: Path | str | None = None,
) -> list[ManifestRow]:
    """Build flat manifest rows for one prepare run, reusing its existing objects.

    Optional modules that were not run (orbit/DEM/GACOS) contribute a single
    ``SKIPPED`` row so the manifest always documents every section.
    """
    rows: list[ManifestRow] = []
    rows.extend(_workflow_rows(report, region_id, region_safe_name))
    rows.extend(_scene_rows(scenes, scene_check_report))
    rows.extend(_orbit_rows(orbit_match_report))
    rows.extend(_dem_rows(dem_planning_report, dem_conversion_report))
    rows.extend(_gacos_request_rows(gacos_planning_report))
    rows.extend(_gacos_import_rows(gacos_import_report))
    rows.extend(_report_rows(json_report_path, markdown_report_path, manifest_csv_path))
    return rows


def manifest_path_for(reports_directory: Path | str, region_safe_name: str) -> Path:
    """Return the SARscape-safe manifest path inside an existing reports directory."""
    if not is_sarscape_safe_name(region_safe_name):
        raise ReportError(
            f"region_safe_name {region_safe_name!r} is not SARscape-safe",
            code=ErrorCode.REP001,
        )
    return Path(reports_directory) / f"{region_safe_name}{MANIFEST_FILENAME_SUFFIX}"


def write_manifest_csv(path: Path | str, rows: list[ManifestRow]) -> Path:
    """Write manifest rows as a UTF-8 CSV (credential-masked). Returns the path.

    Uses ``newline=""`` so CSV line endings stay stable across platforms.
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: mask_text(value) for key, value in row.to_row().items()})
    except OSError as exc:
        raise ReportError(
            f"failed to write manifest CSV {target}: {exc}", code=ErrorCode.REP001
        ) from exc
    logger.debug("wrote manifest CSV with %d rows to %s", len(rows), target)
    return target
