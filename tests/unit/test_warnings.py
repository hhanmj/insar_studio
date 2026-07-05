"""Tests for the offline prepare warnings backend (Task 028)."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from insar_prep.core.exceptions import ReportError
from insar_prep.providers.gacos.types import GacosImportCheckReport, GacosImportIssue
from insar_prep.providers.orbit.types import OrbitMatchIssue, OrbitMatchReport
from insar_prep.quality.types import CheckIssue, CheckSeverity, SceneCheckReport
from insar_prep.reporting.warnings import (
    WARNINGS_COLUMNS,
    WarningRow,
    build_warning_rows,
    warnings_path_for,
    write_warnings_csv,
)


def _scene_report(*issues: CheckIssue) -> SceneCheckReport:
    return SceneCheckReport(
        total_scenes=2,
        valid_scenes=2,
        issues=list(issues),
        has_errors=any(i.severity is CheckSeverity.ERROR for i in issues),
        has_warnings=any(i.severity is CheckSeverity.WARNING for i in issues),
    )


def test_warnings_columns_are_fixed() -> None:
    assert WARNINGS_COLUMNS == [
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


def test_no_problems_emits_single_info_summary() -> None:
    rows = build_warning_rows(
        region_safe_name="shiliushubao",
        scene_check_report=_scene_report(),
    )
    assert len(rows) == 1
    summary = rows[0]
    assert summary.severity == "INFO"
    assert summary.section == "workflow"
    assert summary.item_type == "warnings_summary"
    assert "No warnings or errors" in summary.message


def test_scene_warning_and_error_become_rows() -> None:
    rows = build_warning_rows(
        region_safe_name="shiliushubao",
        scene_check_report=_scene_report(
            CheckIssue(
                code="SCENE_PLATFORM_MIXED",
                severity=CheckSeverity.WARNING,
                message="stack mixes Sentinel-1 platforms",
            ),
            CheckIssue(
                code="SCENE_DUPLICATE_ID",
                severity=CheckSeverity.ERROR,
                message="scene_id appears twice",
                scene_id="S1A_dup",
            ),
        ),
    )
    by_code = {row.code: row for row in rows}
    assert by_code["SCENE_PLATFORM_MIXED"].severity == "WARNING"
    assert by_code["SCENE_PLATFORM_MIXED"].section == "scene"
    assert by_code["SCENE_DUPLICATE_ID"].severity == "ERROR"
    assert by_code["SCENE_DUPLICATE_ID"].item_id == "S1A_dup"
    assert by_code["SCENE_DUPLICATE_ID"].action


def test_info_success_notes_are_excluded() -> None:
    orbit = OrbitMatchReport(
        total_scenes=1,
        matched_scenes=1,
        unmatched_scenes=0,
        issues=[
            OrbitMatchIssue(
                code="ORBIT_SELECTED_POEORB",
                severity=CheckSeverity.INFO,
                message="selected POEORB orbit",
                scene_id="A",
            )
        ],
    )
    rows = build_warning_rows(region_safe_name="shiliushubao", orbit_match_report=orbit)
    # Success/selection INFO note must not appear; only the INFO summary remains.
    assert all(row.code != "ORBIT_SELECTED_POEORB" for row in rows)
    assert len(rows) == 1
    assert rows[0].item_type == "warnings_summary"


def test_coverage_not_checked_info_is_included() -> None:
    rows = build_warning_rows(
        region_safe_name="shiliushubao",
        scene_check_report=_scene_report(
            CheckIssue(
                code="SCENE_COVERAGE_NOT_CHECKED",
                severity=CheckSeverity.INFO,
                message="scene footprints unavailable; AOI coverage not checked",
            )
        ),
    )
    codes = {row.code for row in rows}
    assert "SCENE_COVERAGE_NOT_CHECKED" in codes


def test_orbit_unmatched_becomes_row() -> None:
    orbit = OrbitMatchReport(
        total_scenes=1,
        matched_scenes=0,
        unmatched_scenes=1,
        issues=[
            OrbitMatchIssue(
                code="ORBIT_MISSING",
                severity=CheckSeverity.WARNING,
                message="no orbit files",
                scene_id="A",
            )
        ],
    )
    rows = build_warning_rows(region_safe_name="shiliushubao", orbit_match_report=orbit)
    row = next(r for r in rows if r.code == "ORBIT_MISSING")
    assert row.section == "orbit"
    assert row.item_id == "A"
    assert "orbit" in row.action.lower()


def test_gacos_missing_product_becomes_row() -> None:
    report = GacosImportCheckReport(
        expected_dates=[date(2024, 1, 13)],
        found_dates=[],
        missing_dates=[date(2024, 1, 13)],
        issues=[
            GacosImportIssue(
                code="GACOS_ZTD_MISSING",
                severity=CheckSeverity.ERROR,
                message="missing .ztd for 20240113",
                date=date(2024, 1, 13),
            )
        ],
    )
    rows = build_warning_rows(region_safe_name="shiliushubao", gacos_import_report=report)
    row = next(r for r in rows if r.code == "GACOS_ZTD_MISSING")
    assert row.severity == "ERROR"
    assert row.section == "gacos"
    assert row.item_id == "2024-01-13"
    assert row.item_name == "20240113"
    assert "GACOS" in row.action or "download" in row.action


def test_write_and_read_back(tmp_path: Path) -> None:
    rows = build_warning_rows(
        region_safe_name="shiliushubao",
        scene_check_report=_scene_report(
            CheckIssue(
                code="SCENE_PLATFORM_MIXED",
                severity=CheckSeverity.WARNING,
                message="stack mixes Sentinel-1 platforms",
            )
        ),
    )
    path = tmp_path / "shiliushubao_warnings.csv"
    assert write_warnings_csv(path, rows) == path
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == WARNINGS_COLUMNS
        read_rows = list(reader)
    assert len(read_rows) == len(rows)
    assert read_rows[0]["severity"] == "WARNING"


def test_empty_case_still_writes_header(tmp_path: Path) -> None:
    rows = build_warning_rows(region_safe_name="shiliushubao", scene_check_report=_scene_report())
    path = tmp_path / "shiliushubao_warnings.csv"
    write_warnings_csv(path, rows)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(WARNINGS_COLUMNS)
    assert "" not in lines  # no blank interleaved lines


def test_write_warnings_masks_secrets(tmp_path: Path) -> None:
    rows = [
        WarningRow(
            severity="ERROR",
            section="workflow",
            item_type="note",
            message="token=DEADBEEFCAFE1234",
        )
    ]
    path = tmp_path / "x_warnings.csv"
    write_warnings_csv(path, rows)
    text = path.read_text(encoding="utf-8")
    assert "DEADBEEFCAFE1234" not in text
    assert "token" in text


def test_windows_path_and_commas_round_trip(tmp_path: Path) -> None:
    windows_path = r"C:\Users\me\My Work\20240113.ztd"
    rows = [
        WarningRow(
            severity="ERROR",
            section="gacos",
            item_type="gacos_import",
            item_id="2024-01-13",
            item_name="20240113",
            code="GACOS_EMPTY_FILE",
            message="empty GACOS file, please re-download",
            path=windows_path,
            action="re-download the empty GACOS product",
        )
    ]
    path = tmp_path / "w_warnings.csv"
    write_warnings_csv(path, rows)
    with path.open(encoding="utf-8", newline="") as handle:
        read_rows = list(csv.DictReader(handle))
    assert read_rows[0]["path"] == windows_path
    assert read_rows[0]["message"] == "empty GACOS file, please re-download"


def test_warnings_path_for_uses_safe_suffix(tmp_path: Path) -> None:
    path = warnings_path_for(tmp_path, "shiliushubao")
    assert path.name == "shiliushubao_warnings.csv"
    assert path.parent == tmp_path


def test_warnings_path_for_rejects_unsafe_name(tmp_path: Path) -> None:
    with pytest.raises(ReportError):
        warnings_path_for(tmp_path, "Bad-Name")
