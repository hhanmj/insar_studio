"""Tests for the offline prepare manifest backend (Task 026)."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from insar_prep.core.enums import Platform
from insar_prep.core.exceptions import ReportError
from insar_prep.core.models import Scene
from insar_prep.providers.orbit.types import (
    OrbitFile,
    OrbitMatchReport,
    OrbitMatchResult,
    OrbitType,
)
from insar_prep.quality.types import CheckIssue, CheckSeverity, SceneCheckReport
from insar_prep.reporting.manifest import (
    MANIFEST_COLUMNS,
    ManifestRow,
    build_manifest_rows,
    manifest_path_for,
    write_manifest_csv,
)
from insar_prep.reporting.types import DataPreparationReport


def _report() -> DataPreparationReport:
    return DataPreparationReport(
        region_id="r1",
        region_safe_name="shiliushubao",
        summary={"overall_status": "ready"},
    )


def _scenes() -> list[Scene]:
    return [
        Scene(
            scene_id="S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
            platform=Platform.S1A,
            acquisition_datetime=datetime(2024, 1, 1, 10, tzinfo=UTC),
            url="https://datapool.asf.alaska.edu/SLC/SA/scene_a.zip",
        ),
        Scene(
            scene_id="S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064ABD_5678",
            platform=Platform.S1B,
            acquisition_datetime=datetime(2024, 1, 13, 10, tzinfo=UTC),
        ),
    ]


def _minimal_rows() -> list[ManifestRow]:
    return build_manifest_rows(
        region_id="r1",
        region_safe_name="shiliushubao",
        report=_report(),
        scenes=_scenes(),
        json_report_path=Path("a.json"),
        markdown_report_path=Path("a.md"),
        manifest_csv_path=Path("a_manifest.csv"),
    )


def test_manifest_columns_are_fixed() -> None:
    assert MANIFEST_COLUMNS == [
        "section",
        "item_type",
        "item_id",
        "item_name",
        "status",
        "path",
        "value",
        "notes",
    ]


def test_minimal_rows_cover_required_sections() -> None:
    rows = _minimal_rows()
    sections = {row.section for row in rows}
    assert {"workflow", "scene", "orbit", "dem", "gacos", "report"} <= sections


def test_minimal_rows_have_one_row_per_scene() -> None:
    rows = _minimal_rows()
    scene_rows = [row for row in rows if row.section == "scene" and row.item_type == "scene"]
    assert len(scene_rows) == 2
    assert all(row.status == "OK" for row in scene_rows)
    # The scene with a URL records it as present; the other as missing.
    notes = " ".join(row.notes for row in scene_rows)
    assert "url=present" in notes
    assert "url=missing" in notes


def test_report_rows_list_all_three_outputs() -> None:
    rows = _minimal_rows()
    report_types = {row.item_type for row in rows if row.section == "report"}
    assert report_types == {"json_report", "markdown_report", "manifest_csv"}


def test_optional_modules_emit_skipped_rows() -> None:
    rows = _minimal_rows()

    def statuses(section: str) -> set[str]:
        return {row.status for row in rows if row.section == section}

    assert "SKIPPED" in statuses("orbit")
    assert "SKIPPED" in statuses("dem")
    assert "SKIPPED" in statuses("gacos")


def test_scene_status_reflects_check_severity() -> None:
    scenes = _scenes()
    check = SceneCheckReport(
        total_scenes=2,
        valid_scenes=1,
        issues=[
            CheckIssue(
                code="SCENE_BAD",
                severity=CheckSeverity.ERROR,
                message="bad",
                scene_id=scenes[0].scene_id,
            )
        ],
        has_errors=True,
    )
    rows = build_manifest_rows(
        region_id="r1",
        region_safe_name="shiliushubao",
        report=_report(),
        scenes=scenes,
        scene_check_report=check,
    )
    by_id = {row.item_id: row for row in rows if row.section == "scene"}
    assert by_id[scenes[0].scene_id].status == "ERROR"
    assert by_id[scenes[1].scene_id].status == "OK"


def test_orbit_rows_record_matched_and_unmatched() -> None:
    matched = OrbitFile(
        file_name="S1A_OPER_AUX_POEORB_OPOD.EOF",
        platform=Platform.S1A,
        orbit_type=OrbitType.POEORB,
        creation_datetime=datetime(2024, 1, 2, tzinfo=UTC),
        validity_start=datetime(2024, 1, 1, tzinfo=UTC),
        validity_stop=datetime(2024, 1, 2, tzinfo=UTC),
        path=Path("/orbits/S1A_OPER_AUX_POEORB_OPOD.EOF"),
    )
    orbit_report = OrbitMatchReport(
        total_scenes=2,
        matched_scenes=1,
        unmatched_scenes=1,
        results=[
            OrbitMatchResult(scene_id="A", matched_orbit=matched, is_matched=True),
            OrbitMatchResult(scene_id="B", is_matched=False),
        ],
    )
    rows = build_manifest_rows(
        region_id="r1",
        region_safe_name="shiliushubao",
        report=_report(),
        scenes=[],
        orbit_match_report=orbit_report,
    )
    orbit_rows = {row.item_id: row for row in rows if row.section == "orbit"}
    assert orbit_rows["A"].status == "OK"
    assert orbit_rows["A"].value == "POEORB"
    assert orbit_rows["B"].status == "MISSING"


def test_write_manifest_round_trips_via_dictreader(tmp_path: Path) -> None:
    path = tmp_path / "shiliushubao_manifest.csv"
    written = write_manifest_csv(path, _minimal_rows())
    assert written == path
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MANIFEST_COLUMNS
        read_rows = list(reader)
    assert len(read_rows) == len(_minimal_rows())
    report_item_types = {row["item_type"] for row in read_rows if row["section"] == "report"}
    assert {"json_report", "markdown_report", "manifest_csv"} <= report_item_types


def test_write_manifest_masks_secrets(tmp_path: Path) -> None:
    rows = [
        ManifestRow(
            section="workflow",
            item_type="note",
            notes="token=DEADBEEFCAFE1234",
        )
    ]
    path = tmp_path / "x_manifest.csv"
    write_manifest_csv(path, rows)
    text = path.read_text(encoding="utf-8")
    assert "DEADBEEFCAFE1234" not in text
    assert "token" in text


def test_write_manifest_preserves_windows_path_and_commas(tmp_path: Path) -> None:
    windows_path = r"C:\Users\me\My Work\shiliushubao_manifest.csv"
    rows = [
        ManifestRow(
            section="report",
            item_type="manifest_csv",
            item_name="manifest_csv",
            status="GENERATED",
            path=windows_path,
            notes="a, b, c",
        )
    ]
    path = tmp_path / "w_manifest.csv"
    write_manifest_csv(path, rows)
    with path.open(encoding="utf-8", newline="") as handle:
        read_rows = list(csv.DictReader(handle))
    assert read_rows[0]["path"] == windows_path
    assert read_rows[0]["notes"] == "a, b, c"


def test_manifest_csv_has_no_blank_interleaved_lines(tmp_path: Path) -> None:
    path = tmp_path / "shiliushubao_manifest.csv"
    write_manifest_csv(path, _minimal_rows())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "" not in lines
    assert lines[0] == ",".join(MANIFEST_COLUMNS)


def test_manifest_path_for_uses_safe_suffix(tmp_path: Path) -> None:
    path = manifest_path_for(tmp_path, "shiliushubao")
    assert path.name == "shiliushubao_manifest.csv"
    assert path.parent == tmp_path


def test_manifest_path_for_rejects_unsafe_name(tmp_path: Path) -> None:
    with pytest.raises(ReportError):
        manifest_path_for(tmp_path, "Bad-Name")


def test_gacos_import_marks_missing_and_extra() -> None:
    from insar_prep.providers.gacos.types import (
        GacosImportCheckReport,
        GacosImportIssue,
    )

    import_report = GacosImportCheckReport(
        expected_dates=[date(2024, 1, 1), date(2024, 1, 13)],
        found_dates=[date(2024, 1, 1)],
        missing_dates=[date(2024, 1, 13)],
        extra_dates=[date(2024, 2, 1)],
        issues=[
            GacosImportIssue(
                code="GACOS_ZTD_MISSING",
                severity=CheckSeverity.ERROR,
                message="missing",
                date=date(2024, 1, 13),
            )
        ],
    )
    rows = build_manifest_rows(
        region_id="r1",
        region_safe_name="shiliushubao",
        report=_report(),
        scenes=[],
        gacos_import_report=import_report,
    )
    import_rows = {row.item_name: row for row in rows if row.item_type == "gacos_import_date"}
    assert import_rows["20240101"].status == "OK"
    assert import_rows["20240113"].status == "MISSING"
    assert import_rows["20240201"].status == "WARNING"
