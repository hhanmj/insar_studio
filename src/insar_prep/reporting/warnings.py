"""Offline prepare-workflow warnings summary (Task 028).

Builds a flat ``warnings.csv`` that aggregates only the *problems* surfaced by a
``prepare`` run -- scene/orbit/DEM/GACOS issues with ``WARNING`` or ``ERROR``
severity (plus a small allowlist of informational limitation notes). It is a
problem summary, **not** the full inventory (that is ``manifest.csv``): normal
``OK`` / ``PLANNED`` / selection / "ready" notes are intentionally excluded.

This module only reuses objects already produced by the workflow; it never
re-parses carts, re-scans directories, re-runs checks, downloads, or contacts any
service. Every cell is credential-masked via ``mask_text`` and paths are strings.
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
    from insar_prep.providers.dem.types import DemConversionReport, DemPlanningReport
    from insar_prep.providers.gacos.types import GacosImportCheckReport, GacosPlanningReport
    from insar_prep.providers.orbit.types import OrbitMatchReport
    from insar_prep.quality.types import SceneCheckReport

logger = get_logger("reporting.warnings")

# Fixed CSV column order. Do not reorder: downstream readers rely on this header.
WARNINGS_COLUMNS = [
    "severity",
    "section",
    "item_type",
    "item_id",
    "item_name",
    "code",
    "message",
    "path",
    "action",
]

WARNINGS_FILENAME_SUFFIX = "_warnings.csv"

# Informational issues that are limitations worth surfacing (kept despite INFO).
_INFO_INCLUDE_CODES = {"SCENE_COVERAGE_NOT_CHECKED"}


class WarningRow(InsarBaseModel):
    """One row of the prepare warnings summary (mirrors :data:`WARNINGS_COLUMNS`)."""

    severity: str
    section: str
    item_type: str
    item_id: str = ""
    item_name: str = ""
    code: str = ""
    message: str = ""
    path: str = ""
    action: str = ""

    def to_row(self) -> dict[str, str]:
        """Return this row as a ``{column: value}`` dict for ``csv.DictWriter``."""
        return {column: getattr(self, column) for column in WARNINGS_COLUMNS}


def _as_str(value: object | None) -> str:
    return "" if value is None else str(value)


def _is_included(severity: str, code: str) -> bool:
    """Keep WARNING/ERROR always, and a small allowlist of INFO limitation notes."""
    if severity in ("WARNING", "ERROR"):
        return True
    return severity == "INFO" and code in _INFO_INCLUDE_CODES


def _action_for(section: str, code: str, severity: str) -> str:
    """Suggest a short next step for the user based on the issue code/section."""
    upper = (code or "").upper()
    if "POLARIZATION" in upper:
        return "review scene polarization consistency"
    if "PLATFORM" in upper:
        return "prefer a single Sentinel-1 platform for the stack"
    if "DUPLICATE" in upper:
        return "remove the duplicate scene from the cart"
    if "URL" in upper:
        return "provide a download URL for the scene"
    if "SOURCE" in upper:
        return "provide a download URL or local file for the scene"
    if "COVERAGE" in upper or "NOT_CHECKED" in upper:
        return "verify AOI coverage after downloading the SAFE"
    if section == "orbit" or "ORBIT" in upper:
        return "provide a matching Sentinel-1 orbit (.EOF) file"
    if section == "gacos" or "GACOS" in upper:
        if "MISSING" in upper:
            return "download the missing GACOS product for this date"
        if "EMPTY" in upper:
            return "re-download the empty GACOS product"
        if "EXTRA" in upper:
            return "verify this unexpected GACOS date"
        if "FILENAME" in upper:
            return "rename the GACOS file to YYYYMMDD.ztd[.rsc]"
        return "check the GACOS products"
    if section == "dem":
        return "review the DEM plan / vertical datum"
    if severity == "ERROR":
        return "resolve this error before SARscape import"
    if severity == "WARNING":
        return "review this warning before processing"
    return ""


def _row_from_issue(
    issue,
    *,
    section: str,
    item_type: str,
    item_id: str = "",
    item_name: str = "",
    path: str = "",
) -> WarningRow | None:
    """Convert a sub-report issue into a WarningRow, or None if it is not a problem."""
    severity = issue.severity.value
    code = str(issue.code)
    if not _is_included(severity, code):
        return None
    return WarningRow(
        severity=severity,
        section=section,
        item_type=item_type,
        item_id=item_id,
        item_name=item_name,
        code=code,
        message=str(issue.message),
        path=path,
        action=_action_for(section, code, severity),
    )


def _scene_rows(scene_check_report) -> list[WarningRow]:
    if scene_check_report is None:
        return []
    rows: list[WarningRow] = []
    for issue in scene_check_report.issues:
        scene_id = issue.scene_id or ""
        row = _row_from_issue(
            issue,
            section="scene",
            item_type="scene",
            item_id=scene_id,
            item_name=scene_id or "scene collection",
        )
        if row is not None:
            rows.append(row)
    return rows


def _orbit_rows(orbit_match_report) -> list[WarningRow]:
    if orbit_match_report is None:
        return []
    rows: list[WarningRow] = []
    for issue in orbit_match_report.issues:
        scene_id = issue.scene_id or ""
        orbit_file = getattr(issue, "orbit_file", None) or ""
        row = _row_from_issue(
            issue,
            section="orbit",
            item_type="orbit_match",
            item_id=scene_id,
            item_name=orbit_file or scene_id,
        )
        if row is not None:
            rows.append(row)
    return rows


def _dem_rows(dem_planning_report, dem_conversion_report) -> list[WarningRow]:
    rows: list[WarningRow] = []
    if dem_planning_report is not None:
        for issue in dem_planning_report.issues:
            row = _row_from_issue(
                issue, section="dem", item_type="dem_plan", item_name="DEM planning"
            )
            if row is not None:
                rows.append(row)
    if dem_conversion_report is not None:
        for issue in dem_conversion_report.issues:
            row = _row_from_issue(
                issue, section="dem", item_type="dem_conversion", item_name="DEM conversion"
            )
            if row is not None:
                rows.append(row)
    return rows


def _gacos_rows(gacos_planning_report, gacos_import_report) -> list[WarningRow]:
    rows: list[WarningRow] = []
    if gacos_planning_report is not None:
        for issue in gacos_planning_report.issues:
            row = _row_from_issue(
                issue,
                section="gacos",
                item_type="gacos_request",
                item_name="GACOS request planning",
            )
            if row is not None:
                rows.append(row)
    if gacos_import_report is not None:
        for issue in gacos_import_report.issues:
            day = getattr(issue, "date", None)
            stamp = day.strftime("%Y%m%d") if day is not None else ""
            row = _row_from_issue(
                issue,
                section="gacos",
                item_type="gacos_import",
                item_id=day.isoformat() if day is not None else "",
                item_name=stamp or "GACOS import",
                path=_as_str(getattr(issue, "file_path", None)),
            )
            if row is not None:
                rows.append(row)
    return rows


def build_warning_rows(
    *,
    region_safe_name: str,
    scene_check_report: SceneCheckReport | None = None,
    orbit_match_report: OrbitMatchReport | None = None,
    dem_planning_report: DemPlanningReport | None = None,
    dem_conversion_report: DemConversionReport | None = None,
    gacos_planning_report: GacosPlanningReport | None = None,
    gacos_import_report: GacosImportCheckReport | None = None,
) -> list[WarningRow]:
    """Aggregate WARNING/ERROR problems from the prepare sub-reports.

    Returns one row per problem. When nothing is wrong, returns a single INFO
    summary row so the file is always non-empty and self-explanatory.
    """
    rows: list[WarningRow] = []
    rows.extend(_scene_rows(scene_check_report))
    rows.extend(_orbit_rows(orbit_match_report))
    rows.extend(_dem_rows(dem_planning_report, dem_conversion_report))
    rows.extend(_gacos_rows(gacos_planning_report, gacos_import_report))
    if not rows:
        rows.append(
            WarningRow(
                severity="INFO",
                section="workflow",
                item_type="warnings_summary",
                item_name=region_safe_name,
                message="No warnings or errors were detected.",
            )
        )
    return rows


def warnings_path_for(reports_directory: Path | str, region_safe_name: str) -> Path:
    """Return the SARscape-safe warnings path inside an existing reports directory."""
    if not is_sarscape_safe_name(region_safe_name):
        raise ReportError(
            f"region_safe_name {region_safe_name!r} is not SARscape-safe",
            code=ErrorCode.REP001,
        )
    return Path(reports_directory) / f"{region_safe_name}{WARNINGS_FILENAME_SUFFIX}"


def write_warnings_csv(path: Path | str, rows: list[WarningRow]) -> Path:
    """Write warning rows as a UTF-8 CSV (credential-masked). Returns the path.

    Uses ``newline=""`` so CSV line endings stay stable across platforms.
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=WARNINGS_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: mask_text(value) for key, value in row.to_row().items()})
    except OSError as exc:
        raise ReportError(
            f"failed to write warnings CSV {target}: {exc}", code=ErrorCode.REP001
        ) from exc
    logger.debug("wrote warnings CSV with %d rows to %s", len(rows), target)
    return target
