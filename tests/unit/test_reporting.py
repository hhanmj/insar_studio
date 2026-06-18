"""Tests for the data-preparation report backend (Task 014)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from insar_prep.core.models import Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.providers.gacos.planner import (
    create_gacos_request_plan,
    validate_gacos_request_plan,
)
from insar_prep.providers.orbit.types import OrbitMatchIssue, OrbitMatchReport
from insar_prep.quality.types import CheckIssue, CheckSeverity, SceneCheckReport
from insar_prep.reporting.generator import (
    build_data_preparation_report,
    render_report_markdown,
    save_report,
)
from insar_prep.reporting.types import DataPreparationReport, ReportStatus


def scene_report(*, with_error: bool = False) -> SceneCheckReport:
    issues = []
    if with_error:
        issues.append(
            CheckIssue(code="SCENE_BAD", severity=CheckSeverity.ERROR, message="bad scene")
        )
    return SceneCheckReport(
        total_scenes=2,
        valid_scenes=1 if with_error else 2,
        issues=issues,
        has_errors=with_error,
        has_warnings=False,
        summary={"platforms": ["S1A"], "product_types": ["SLC"]},
    )


def orbit_report_with_warning() -> OrbitMatchReport:
    return OrbitMatchReport(
        total_scenes=2,
        matched_scenes=1,
        unmatched_scenes=1,
        issues=[
            OrbitMatchIssue(
                code="ORBIT_MISSING",
                severity=CheckSeverity.WARNING,
                message="no orbit covers the scene",
            )
        ],
        summary={"orbit_types": ["POEORB"]},
    )


def gacos_planning_report(tmp_path: Path):
    scenes = [
        Scene(acquisition_datetime=datetime(2023, 1, 1, 12)),
        Scene(acquisition_datetime=datetime(2023, 1, 13, 12)),
    ]
    plan = create_gacos_request_plan(
        region_id="r1",
        region_safe_name="shiliushubao",
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        scenes=scenes,
        output_root=tmp_path,
    )
    return validate_gacos_request_plan(plan)


def test_scene_only_report_builds() -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    assert isinstance(report, DataPreparationReport)
    titles = [section.title for section in report.sections]
    assert "Scene consistency" in titles
    assert "Next actions" in titles


def test_multi_module_report_builds(tmp_path: Path) -> None:
    report = build_data_preparation_report(
        region_id="r1",
        region_safe_name="shiliushubao",
        scene_check_report=scene_report(),
        orbit_match_report=orbit_report_with_warning(),
        gacos_planning_report=gacos_planning_report(tmp_path),
    )
    titles = [section.title for section in report.sections]
    assert "Scene consistency" in titles
    assert "Orbit matching" in titles
    assert "GACOS request planning" in titles


def test_error_sets_has_errors() -> None:
    report = build_data_preparation_report(
        region_id="r1",
        region_safe_name="shiliushubao",
        scene_check_report=scene_report(with_error=True),
    )
    assert report.has_errors
    assert report.summary["overall_status"] == ReportStatus.BLOCKED.value


def test_warning_sets_has_warnings() -> None:
    report = build_data_preparation_report(
        region_id="r1",
        region_safe_name="shiliushubao",
        orbit_match_report=orbit_report_with_warning(),
    )
    assert not report.has_errors
    assert report.has_warnings
    assert report.summary["overall_status"] == ReportStatus.READY_WITH_WARNINGS.value


def test_markdown_contains_section_titles() -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    markdown = render_report_markdown(report)
    assert markdown.startswith("# ")
    assert "## Scene consistency" in markdown
    assert "## Next actions" in markdown


def test_report_json_loads() -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    parsed = json.loads(report.to_json())
    assert parsed["region_safe_name"] == "shiliushubao"
    assert isinstance(parsed["sections"], list)


def test_save_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    output = save_report(report, tmp_path)
    assert output.json_path.exists()
    assert output.markdown_path.exists()
    assert len(output.written_files) == 2


def test_output_filenames_are_safe(tmp_path: Path) -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    output = save_report(report, tmp_path)
    assert output.json_path.name == "shiliushubao_data_preparation_report.json"
    assert output.markdown_path.name == "shiliushubao_data_preparation_report.md"


def test_output_directory_is_07_reports(tmp_path: Path) -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    output = save_report(report, tmp_path)
    assert "07_reports" in output.json_path.parts


def test_secrets_are_masked(tmp_path: Path) -> None:
    leaky = SceneCheckReport(
        total_scenes=1,
        valid_scenes=1,
        issues=[],
        has_errors=False,
        has_warnings=False,
        summary={"note": "token=DEADBEEFCAFE1234"},
    )
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=leaky
    )
    output = save_report(report, tmp_path)
    json_text = output.json_path.read_text(encoding="utf-8")
    md_text = output.markdown_path.read_text(encoding="utf-8")
    assert "DEADBEEFCAFE1234" not in json_text
    assert "DEADBEEFCAFE1234" not in md_text
    assert "token" in md_text


def test_empty_inputs_build_basic_report() -> None:
    report = build_data_preparation_report(region_id="r1", region_safe_name="shiliushubao")
    assert isinstance(report, DataPreparationReport)
    assert not report.has_errors
    assert not report.has_warnings
    assert report.summary["overall_status"] == ReportStatus.READY.value
    assert [section.title for section in report.sections] == ["Next actions"]


def test_no_pdf_or_html_written(tmp_path: Path) -> None:
    report = build_data_preparation_report(
        region_id="r1", region_safe_name="shiliushubao", scene_check_report=scene_report()
    )
    output = save_report(report, tmp_path)
    suffixes = sorted(entry.suffix for entry in output.json_path.parent.iterdir())
    assert suffixes == [".json", ".md"]
