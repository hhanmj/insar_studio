"""Offline data-preparation report generation (Task 014).

Consolidates the outcomes of the scene, orbit, DEM, and GACOS modules into one
structured :class:`DataPreparationReport`, renders a beginner-friendly Markdown
view, and writes JSON + Markdown to a SARscape-safe ``07_reports`` directory.

Strictly offline: no GUI, no PDF, no HTML, no browser, no network, no download,
and no external services. All written text is passed through ``mask_text`` (which
reuses ``mask_secret``) so credentials never reach disk.
"""

from __future__ import annotations

from pathlib import Path

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import ReportError
from insar_prep.core.logging import get_logger, log_event, mask_text
from insar_prep.core.naming import is_sarscape_safe_name
from insar_prep.quality.types import CheckSeverity
from insar_prep.reporting.types import (
    DataPreparationReport,
    ReportIssue,
    ReportOutput,
    ReportSection,
    ReportStatus,
)

logger = get_logger("reporting.generator")

REPORTS_SUBDIR = "07_reports"


def _to_report_issues(section: str, issues: list) -> list[ReportIssue]:
    """Normalize any issue carrying ``code``/``severity``/``message``."""
    return [
        ReportIssue(
            section=section,
            code=str(issue.code),
            severity=issue.severity,
            message=str(issue.message),
        )
        for issue in issues
    ]


def _status_from_issues(issues: list[ReportIssue]) -> ReportStatus:
    if any(issue.severity is CheckSeverity.ERROR for issue in issues):
        return ReportStatus.BLOCKED
    if any(issue.severity is CheckSeverity.WARNING for issue in issues):
        return ReportStatus.READY_WITH_WARNINGS
    return ReportStatus.READY


def _bbox_text(bbox) -> str:
    return f"W {bbox.west}, S {bbox.south}, E {bbox.east}, N {bbox.north}"


def _scene_section(report) -> ReportSection:
    issues = _to_report_issues("Scene consistency", report.issues)
    items = [
        f"Total scenes: {report.total_scenes}",
        f"Valid scenes: {report.valid_scenes}",
    ]
    items.extend(f"{key}: {value}" for key, value in report.summary.items())
    return ReportSection(
        title="Scene consistency",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _orbit_section(report) -> ReportSection:
    issues = _to_report_issues("Orbit matching", report.issues)
    items = [
        f"Total scenes: {report.total_scenes}",
        f"Matched scenes: {report.matched_scenes}",
        f"Unmatched scenes: {report.unmatched_scenes}",
    ]
    orbit_types = report.summary.get("orbit_types")
    if orbit_types is not None:
        items.append(f"Orbit types available: {orbit_types}")
    return ReportSection(
        title="Orbit matching",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _dem_planning_section(report) -> ReportSection:
    issues = _to_report_issues("DEM planning", report.issues)
    plan = report.plan
    items: list[str] = []
    if plan is not None:
        items = [
            f"Dataset: {plan.dataset}",
            f"Provider: {plan.provider}",
            f"Request bbox: {_bbox_text(plan.request_bbox)}",
            f"Raw DEM path: {plan.raw_dem_path}",
            f"Ellipsoid DEM path: {plan.ellipsoid_dem_path}",
            f"SARscape-ready DEM path: {plan.sarscape_ready_dem_path}",
        ]
    return ReportSection(
        title="DEM planning",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _dem_conversion_section(report) -> ReportSection:
    issues = _to_report_issues("DEM conversion", report.issues)
    plan = report.plan
    items: list[str] = []
    if plan is not None:
        manual_review = any(step.step_type == "MANUAL_REVIEW_REQUIRED" for step in plan.steps)
        items = [
            f"Source vertical datum: {plan.source_vertical_datum}",
            f"Target vertical datum: {plan.target_vertical_datum}",
            f"Requires conversion: {plan.requires_conversion}",
            f"Requires geoid: {plan.requires_geoid}",
            f"Manual review required: {manual_review}",
        ]
    return ReportSection(
        title="DEM conversion",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _gacos_planning_section(report) -> ReportSection:
    issues = _to_report_issues("GACOS request planning", report.issues)
    plan = report.plan
    items: list[str] = []
    if plan is not None:
        items = [
            f"Total acquisition dates: {len(plan.unique_dates)}",
            f"Request batches: {len(plan.batches)}",
            f"Request bbox: {_bbox_text(plan.request_bbox)}",
            f"Manual submission required: {plan.manual_submission_required}",
        ]
    return ReportSection(
        title="GACOS request planning",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _gacos_import_section(report) -> ReportSection:
    issues = _to_report_issues("GACOS import check", report.issues)
    empty_files = sum(1 for issue in issues if issue.code == "GACOS_EMPTY_FILE")
    items = [
        f"Expected dates: {len(report.expected_dates)}",
        f"Found dates: {len(report.found_dates)}",
        f"Missing dates: {len(report.missing_dates)}",
        f"Extra dates: {len(report.extra_dates)}",
        f"Empty files: {empty_files}",
    ]
    return ReportSection(
        title="GACOS import check",
        status=_status_from_issues(issues),
        summary=dict(report.summary),
        items=items,
        issues=issues,
    )


def _next_actions_section(sections: list[ReportSection]) -> ReportSection:
    actionable = [
        issue
        for section in sections
        for issue in section.issues
        if issue.severity in (CheckSeverity.ERROR, CheckSeverity.WARNING)
    ]
    items = [
        f"[{issue.severity.value}] {issue.section} / {issue.code}: {issue.message}"
        for issue in actionable
    ]
    if not items:
        items.append("No action required. Data appears ready for SARscape import.")
    return ReportSection(
        title="Next actions",
        status=_status_from_issues(actionable),
        items=items,
        issues=actionable,
    )


def build_data_preparation_report(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    region_id: str,
    region_safe_name: str,
    scene_check_report=None,
    orbit_match_report=None,
    dem_planning_report=None,
    dem_conversion_report=None,
    gacos_planning_report=None,
    gacos_import_report=None,
) -> DataPreparationReport:
    """Consolidate available module reports into one data-preparation report."""
    sections: list[ReportSection] = []
    if scene_check_report is not None:
        sections.append(_scene_section(scene_check_report))
    if orbit_match_report is not None:
        sections.append(_orbit_section(orbit_match_report))
    if dem_planning_report is not None:
        sections.append(_dem_planning_section(dem_planning_report))
    if dem_conversion_report is not None:
        sections.append(_dem_conversion_section(dem_conversion_report))
    if gacos_planning_report is not None:
        sections.append(_gacos_planning_section(gacos_planning_report))
    if gacos_import_report is not None:
        sections.append(_gacos_import_section(gacos_import_report))

    all_issues = [issue for section in sections for issue in section.issues]
    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in all_issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in all_issues)
    overall = _status_from_issues(all_issues)

    sections.append(_next_actions_section(sections))
    summary = {
        "overall_status": overall.value,
        "section_count": len(sections),
        "error_count": sum(1 for issue in all_issues if issue.severity is CheckSeverity.ERROR),
        "warning_count": sum(1 for issue in all_issues if issue.severity is CheckSeverity.WARNING),
    }
    report = DataPreparationReport(
        workspace_id=workspace_id,
        project_id=project_id,
        region_id=region_id,
        region_safe_name=region_safe_name,
        title=f"InSAR data preparation report: {region_safe_name}",
        sections=sections,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )
    logger.debug("built data preparation report for region %s", region_safe_name)
    return report


def render_report_markdown(report: DataPreparationReport) -> str:
    """Render a beginner-friendly Markdown view of a report."""
    lines = [
        f"# {report.title or 'InSAR data preparation report'}",
        "",
        f"- Project: {report.project_id or '-'}",
        f"- Region: {report.region_safe_name} ({report.region_id})",
        f"- Created: {report.created_at.isoformat()}",
        f"- Overall status: {report.summary.get('overall_status', '-')}",
        "",
    ]
    for section in report.sections:
        lines.append(f"## {section.title}")
        lines.append(f"- Status: {section.status.value}")
        lines.extend(f"- {item}" for item in section.items)
        if section.issues:
            lines.append("")
            lines.append("Issues:")
            lines.extend(
                f"- [{issue.severity.value}] {issue.code}: {issue.message}"
                for issue in section.issues
            )
        lines.append("")
    return "\n".join(lines)


def save_report(report: DataPreparationReport, output_directory: Path | str) -> ReportOutput:
    """Write a report as UTF-8 JSON + Markdown under ``07_reports`` (masked)."""
    safe = report.region_safe_name
    if not is_sarscape_safe_name(safe):
        raise ReportError(f"region_safe_name {safe!r} is not SARscape-safe", code=ErrorCode.REP001)
    stem = f"{safe}_data_preparation_report"
    if not is_sarscape_safe_name(stem):  # safety net; should not happen
        raise ReportError(f"report file stem {stem!r} is not SARscape-safe", code=ErrorCode.REP001)

    out_dir = Path(output_directory) / safe / REPORTS_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    json_path.write_text(mask_text(report.to_json(indent=2)), encoding="utf-8")
    md_path.write_text(mask_text(render_report_markdown(report)), encoding="utf-8")

    log_event(
        logger,
        EventType.REPORT_GENERATED,
        f"wrote data preparation report for {safe}",
        module="reporting.generator",
        region_id=report.region_id,
        payload={"json": str(json_path), "markdown": str(md_path)},
    )
    logger.debug("saved report to %s", out_dir)
    return ReportOutput(
        json_path=json_path,
        markdown_path=md_path,
        written_files=[json_path, md_path],
    )
