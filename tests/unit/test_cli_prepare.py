"""Tests for the ``insar-prep prepare`` CLI workflow (Task 015)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from insar_prep.cli.main import main
from insar_prep.core.naming import sarscape_safe_name

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asf"
URLS_CART = FIXTURES / "urls.txt"
CSV_CART = FIXTURES / "scenes.csv"


def report_paths(output_root: Path, region_name: str) -> tuple[Path, Path]:
    safe = sarscape_safe_name(region_name)
    base = Path(output_root) / safe / "07_reports"
    return (
        base / f"{safe}_data_preparation_report.json",
        base / f"{safe}_data_preparation_report.md",
    )


def test_top_level_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "insar-prep 0.1.0" in capsys.readouterr().out


def test_prepare_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["prepare", "--help"])
    assert exc.value.code == 0


def test_prepare_runs_with_fixture(tmp_path: Path) -> None:
    json_path, md_path = report_paths(tmp_path, "shiliushubao")
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert json_path.exists()
    assert md_path.exists()


def test_prepare_generates_valid_json(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
        ]
    )
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["region_safe_name"] == "shiliushubao"
    assert isinstance(data["sections"], list)


def test_prepare_generates_markdown(tmp_path: Path) -> None:
    _, md_path = report_paths(tmp_path, "shiliushubao")
    main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
        ]
    )
    text = md_path.read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert "## Scene consistency" in text


def test_output_directory_is_07_reports(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert "07_reports" in json_path.parts
    assert json_path.exists()


def test_region_name_converted_to_safe_name(tmp_path: Path) -> None:
    region = "Shiliushubao Area-1"
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            region,
            "--output-root",
            str(tmp_path),
        ]
    )
    assert code == 0
    safe = sarscape_safe_name(region)
    assert safe == "shiliushubao_area_1"
    assert (tmp_path / safe / "07_reports" / f"{safe}_data_preparation_report.json").exists()


def test_missing_cart_file_fails(tmp_path: Path) -> None:
    code = main(
        [
            "prepare",
            "--cart",
            str(tmp_path / "does_not_exist.txt"),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert code != 0


def test_require_urls_flag_promotes_to_error(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "csvregion")
    code = main(
        [
            "prepare",
            "--cart",
            str(CSV_CART),
            "--region-name",
            "csvregion",
            "--output-root",
            str(tmp_path),
            "--require-urls",
        ]
    )
    assert code == 0
    text = json_path.read_text(encoding="utf-8")
    assert "SCENE_URL_MISSING" in text
    assert json.loads(text)["has_errors"] is True


def test_without_require_urls_missing_url_is_not_error(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "csvregion")
    main(
        [
            "prepare",
            "--cart",
            str(CSV_CART),
            "--region-name",
            "csvregion",
            "--output-root",
            str(tmp_path),
        ]
    )
    assert json.loads(json_path.read_text(encoding="utf-8"))["has_errors"] is False


def test_expected_polarization_flag_flags_mismatch(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "polregion")
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "polregion",
            "--output-root",
            str(tmp_path),
            "--expected-polarization",
            "VV",
        ]
    )
    assert code == 0
    text = json_path.read_text(encoding="utf-8")
    assert "SCENE_POLARIZATION_MISMATCH" in text
    assert json.loads(text)["has_errors"] is True
