"""Tests for the offline single-file HTML data-preparation report (Task 031)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insar_prep.core.exceptions import ReportError
from insar_prep.quality.types import CheckSeverity
from insar_prep.reporting.html import (
    html_report_path_for,
    render_report_html,
    save_report_html,
)
from insar_prep.reporting.types import (
    DataPreparationReport,
    ReportIssue,
    ReportSection,
    ReportStatus,
)


def _report(*, sections: list[ReportSection] | None = None) -> DataPreparationReport:
    return DataPreparationReport(
        region_id="region_shiliushubao",
        region_safe_name="shiliushubao",
        title="InSAR data preparation report: shiliushubao",
        sections=sections if sections is not None else [],
        summary={
            "overall_status": "ready",
            "section_count": len(sections or []),
            "error_count": 0,
            "warning_count": 0,
        },
    )


def _scene_section() -> ReportSection:
    return ReportSection(
        title="Scene consistency",
        status=ReportStatus.READY_WITH_WARNINGS,
        items=["Total scenes: 2", "Valid scenes: 2"],
        issues=[
            ReportIssue(
                section="Scene consistency",
                code="SCENE_PLATFORM_MIXED",
                severity=CheckSeverity.WARNING,
                message="stack mixes Sentinel-1 platforms",
            )
        ],
    )


def test_render_html_is_well_formed() -> None:
    html = render_report_html(_report(sections=[_scene_section()]))
    assert "<!DOCTYPE html>" in html
    assert '<meta charset="utf-8">' in html
    assert html.strip().endswith("</html>")


def test_render_html_contains_title_and_sections() -> None:
    html = render_report_html(_report(sections=[_scene_section()]))
    assert "InSAR data preparation report: shiliushubao" in html
    assert "Scene consistency" in html
    assert "SCENE_PLATFORM_MIXED" in html


def test_render_html_escapes_user_text() -> None:
    section = ReportSection(
        title="Scene consistency",
        status=ReportStatus.BLOCKED,
        items=["<script>alert('x')</script>"],
        issues=[
            ReportIssue(
                section="Scene consistency",
                code="SCENE_BAD",
                severity=CheckSeverity.ERROR,
                message="<img src=x onerror=alert(1)>",
            )
        ],
    )
    html = render_report_html(_report(sections=[section]))
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x" not in html


def test_render_html_no_sections_still_readable() -> None:
    html = render_report_html(_report(sections=[]))
    assert "<!DOCTYPE html>" in html
    # Summary cards always render, so the document is never blank.
    assert "Overall status" in html


def test_save_html_masks_secrets(tmp_path: Path) -> None:
    section = ReportSection(
        title="Scene consistency",
        status=ReportStatus.READY,
        items=["token=DEADBEEFCAFE1234"],
    )
    path = tmp_path / "shiliushubao_data_preparation_report.html"
    assert save_report_html(_report(sections=[section]), path) == path
    text = path.read_text(encoding="utf-8")
    assert "DEADBEEFCAFE1234" not in text
    assert "token" in text


def test_html_report_path_for_uses_suffix(tmp_path: Path) -> None:
    path = html_report_path_for(tmp_path, "shiliushubao")
    assert path.name == "shiliushubao_data_preparation_report.html"
    assert path.parent == tmp_path


def test_html_report_path_for_rejects_unsafe_name(tmp_path: Path) -> None:
    with pytest.raises(ReportError):
        html_report_path_for(tmp_path, "Bad-Name")
