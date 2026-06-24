"""Tests for the ``insar-prep prepare`` CLI workflow (Task 015)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from insar_prep import __version__
from insar_prep.cli.main import main
from insar_prep.core.naming import sarscape_safe_name

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asf"
URLS_CART = FIXTURES / "urls.txt"
CSV_CART = FIXTURES / "scenes.csv"

# Orbit EOFs covering the two urls.txt scenes (S1A 2024-01-01, S1B 2024-01-13).
_MATCHING_ORBIT_NAMES = (
    "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T000000.EOF",
    "S1B_OPER_AUX_POEORB_OPOD_20240114T120000_V20240113T000000_20240114T000000.EOF",
)


def report_paths(output_root: Path, region_name: str) -> tuple[Path, Path]:
    safe = sarscape_safe_name(region_name)
    base = Path(output_root) / safe / "07_reports"
    return (
        base / f"{safe}_data_preparation_report.json",
        base / f"{safe}_data_preparation_report.md",
    )


def find_section(data: dict, title: str) -> dict | None:
    return next((section for section in data["sections"] if section["title"] == title), None)


def write_matching_orbits(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in _MATCHING_ORBIT_NAMES:
        (directory / name).write_text("placeholder; contents are never parsed\n", encoding="utf-8")
    return directory


def test_top_level_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert f"insar-prep {__version__}" in capsys.readouterr().out


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


def test_prepare_prints_output_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    out = capsys.readouterr().out
    assert "Data preparation report written:" in out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_output_filenames_exact(tmp_path: Path) -> None:
    json_path, md_path = report_paths(tmp_path, "shiliushubao")
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
    assert json_path.name == "shiliushubao_data_preparation_report.json"
    assert md_path.name == "shiliushubao_data_preparation_report.md"
    assert json_path.parent.name == "07_reports"


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


def test_prepare_help_shows_orbit_dir(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["prepare", "--help"])
    assert "--orbit-dir" in capsys.readouterr().out


def test_prepare_without_orbit_dir_has_no_orbit_section(tmp_path: Path) -> None:
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
    assert find_section(data, "Orbit matching") is None


def test_prepare_with_matching_orbits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    orbit_dir = write_matching_orbits(tmp_path / "orbits")
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
            "--orbit-dir",
            str(orbit_dir),
        ]
    )
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "Orbit matching")
    assert section is not None
    assert section["summary"]["matched"] == 2
    out = capsys.readouterr().out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_missing_orbit_dir_fails(tmp_path: Path) -> None:
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--orbit-dir",
            str(tmp_path / "no_orbits_here"),
        ]
    )
    assert code != 0


def test_prepare_orbit_dir_without_matches(tmp_path: Path) -> None:
    empty_orbits = tmp_path / "orbits_empty"
    empty_orbits.mkdir()
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--orbit-dir",
            str(empty_orbits),
        ]
    )
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "Orbit matching")
    assert section is not None
    assert section["summary"]["matched"] == 0
    assert section["issues"]


def _prepare_with_dem(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--dem-plan",
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            *extra,
        ]
    )


def test_prepare_help_shows_dem_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["prepare", "--help"])
    out = capsys.readouterr().out
    assert "--dem-plan" in out
    assert "--bbox" in out


def test_prepare_without_dem_plan_has_no_dem_sections(tmp_path: Path) -> None:
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
    assert find_section(data, "DEM planning") is None
    assert find_section(data, "DEM conversion") is None


def test_prepare_with_dem_plan_adds_sections(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    json_path, md_path = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_dem(tmp_path)
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    planning = find_section(data, "DEM planning")
    conversion = find_section(data, "DEM conversion")
    assert planning is not None
    assert conversion is not None
    items = " ".join(planning["items"])
    assert "04_dem" in items
    assert "raw" in items
    assert "ellipsoid" in items
    assert "06_sarscape_ready" in items
    assert "shiliushubao_dem.tif" in items
    out = capsys.readouterr().out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_dem_markdown_has_section_titles(tmp_path: Path) -> None:
    _, md_path = report_paths(tmp_path, "shiliushubao")
    _prepare_with_dem(tmp_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## DEM planning" in text
    assert "## DEM conversion" in text


def test_prepare_dem_plan_requires_bbox(tmp_path: Path) -> None:
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--dem-plan",
        ]
    )
    assert code != 0


def test_prepare_invalid_bbox_fails(tmp_path: Path) -> None:
    # west >= east is invalid.
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--dem-plan",
            "--bbox",
            "110.6",
            "30.8",
            "110.1",
            "31.2",
        ]
    )
    assert code != 0


def test_prepare_negative_dem_buffer_fails(tmp_path: Path) -> None:
    code = _prepare_with_dem(tmp_path, "--dem-buffer", "-0.1")
    assert code != 0


def test_prepare_dem_plan_creates_no_tif(tmp_path: Path) -> None:
    code = _prepare_with_dem(tmp_path)
    assert code == 0
    assert not list(tmp_path.rglob("*.tif"))


def _prepare_with_gacos(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--gacos-plan",
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            *extra,
        ]
    )


def _write_dated_cart(path: Path, count: int) -> Path:
    """Write an ASF URL cart with ``count`` scenes on ``count`` distinct dates."""
    base = datetime(2024, 1, 1)
    lines = ["# generated ASF download URLs (one per line)"]
    for index in range(count):
        day = base + timedelta(days=12 * index)
        start = day.strftime("%Y%m%dT100000")
        stop = day.strftime("%Y%m%dT100027")
        granule = f"S1A_IW_SLC__1SDV_{start}_{stop}_{52000 + index:06d}_064ABC_{index:04x}"
        lines.append(f"https://datapool.asf.alaska.edu/SLC/SA/{granule}.zip")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_prepare_help_shows_gacos_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["prepare", "--help"])
    out = capsys.readouterr().out
    assert "--gacos-plan" in out
    assert "--gacos-buffer" in out
    assert "--gacos-max-dates-per-batch" in out


def test_prepare_without_gacos_plan_has_no_gacos_section(tmp_path: Path) -> None:
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
    assert find_section(data, "GACOS request planning") is None


def test_prepare_with_gacos_plan_adds_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    json_path, md_path = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_gacos(tmp_path)
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "GACOS request planning")
    assert section is not None
    items = " ".join(section["items"])
    assert "Total acquisition dates" in items
    assert "Request batches" in items
    assert "Request bbox" in items
    assert "Output directory" in items
    assert "05_atmosphere" in items
    assert "Expected file patterns" in items
    assert "*.ztd" in items
    assert "Manual submission required" in items
    out = capsys.readouterr().out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_gacos_markdown_has_section_title(tmp_path: Path) -> None:
    _, md_path = report_paths(tmp_path, "shiliushubao")
    _prepare_with_gacos(tmp_path)
    text = md_path.read_text(encoding="utf-8")
    assert "## GACOS request planning" in text


def test_prepare_gacos_batches_dates_into_20_20_5(tmp_path: Path) -> None:
    cart = _write_dated_cart(tmp_path / "many_dates.txt", 45)
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = main(
        [
            "prepare",
            "--cart",
            str(cart),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--gacos-plan",
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            "--gacos-max-dates-per-batch",
            "20",
        ]
    )
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "GACOS request planning")
    assert section is not None
    assert section["summary"]["unique_date_count"] == 45
    assert section["summary"]["batch_count"] == 3
    assert "Batch sizes: [20, 20, 5]" in " ".join(section["items"])


def test_prepare_gacos_plan_requires_bbox(tmp_path: Path) -> None:
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--gacos-plan",
        ]
    )
    assert code != 0


def test_prepare_negative_gacos_buffer_fails(tmp_path: Path) -> None:
    code = _prepare_with_gacos(tmp_path, "--gacos-buffer", "-0.1")
    assert code != 0


def test_prepare_gacos_max_dates_below_one_fails(tmp_path: Path) -> None:
    code = _prepare_with_gacos(tmp_path, "--gacos-max-dates-per-batch", "0")
    assert code != 0


def test_prepare_gacos_plan_creates_no_ztd(tmp_path: Path) -> None:
    code = _prepare_with_gacos(tmp_path)
    assert code == 0
    assert not list(tmp_path.rglob("*.ztd"))
    assert not list(tmp_path.rglob("*.ztd.rsc"))
    assert not (tmp_path / "shiliushubao" / "05_atmosphere").exists()


def test_prepare_dem_and_gacos_share_bbox(tmp_path: Path) -> None:
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--dem-plan",
            "--gacos-plan",
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
        ]
    )
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert find_section(data, "DEM planning") is not None
    assert find_section(data, "GACOS request planning") is not None


# Scene dates in urls.txt (S1A 2024-01-01, S1B 2024-01-13) define the expected
# GACOS acquisition dates the import checker looks for.
_GACOS_IMPORT_DATES = ("20240101", "20240113")


def _write_gacos_products(directory: Path, dates: tuple[str, ...]) -> Path:
    """Write placeholder GACOS ``.ztd``/``.ztd.rsc`` files (non-empty; never parsed)."""
    directory.mkdir(parents=True, exist_ok=True)
    for stamp in dates:
        (directory / f"{stamp}.ztd").write_text("ztd\n", encoding="utf-8")
        (directory / f"{stamp}.ztd.rsc").write_text("WIDTH 10\n", encoding="utf-8")
    return directory


def _import_codes(section: dict) -> str:
    return " ".join(issue["code"] for issue in section["issues"])


def _prepare_with_gacos_import(tmp_path: Path, import_dir: Path, *extra: str) -> int:
    return main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--gacos-import-dir",
            str(import_dir),
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            *extra,
        ]
    )


def test_prepare_help_shows_gacos_import_dir(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["prepare", "--help"])
    assert "--gacos-import-dir" in capsys.readouterr().out


def test_prepare_without_gacos_import_dir_has_no_import_section(tmp_path: Path) -> None:
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
    assert find_section(data, "GACOS import check") is None


def test_prepare_with_complete_gacos_import_adds_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import_dir = _write_gacos_products(tmp_path / "gacos_products", _GACOS_IMPORT_DATES)
    json_path, md_path = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_gacos_import(tmp_path, import_dir)
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "GACOS import check")
    assert section is not None
    assert section["summary"]["expected_date_count"] == 2
    assert section["summary"]["found_date_count"] == 2
    assert section["summary"]["missing_date_count"] == 0
    assert "GACOS_IMPORT_READY" in _import_codes(section)
    assert data["has_errors"] is False
    out = capsys.readouterr().out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_gacos_import_markdown_has_section_title(tmp_path: Path) -> None:
    import_dir = _write_gacos_products(tmp_path / "gacos_products", _GACOS_IMPORT_DATES)
    _, md_path = report_paths(tmp_path, "shiliushubao")
    _prepare_with_gacos_import(tmp_path, import_dir)
    assert "## GACOS import check" in md_path.read_text(encoding="utf-8")


def test_prepare_gacos_import_missing_products_flag_errors(tmp_path: Path) -> None:
    # Only the first date is present; the second expected date is missing entirely.
    import_dir = _write_gacos_products(tmp_path / "gacos_products", ("20240101",))
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_gacos_import(tmp_path, import_dir)
    assert code == 0
    text = json_path.read_text(encoding="utf-8")
    assert "GACOS_ZTD_MISSING" in text
    assert "GACOS_RSC_MISSING" in text
    data = json.loads(text)
    assert data["has_errors"] is True
    section = find_section(data, "GACOS import check")
    assert section["summary"]["missing_date_count"] == 1


def test_prepare_gacos_import_extra_date_is_warning(tmp_path: Path) -> None:
    import_dir = _write_gacos_products(
        tmp_path / "gacos_products", (*_GACOS_IMPORT_DATES, "20240201")
    )
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_gacos_import(tmp_path, import_dir)
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    section = find_section(data, "GACOS import check")
    assert section["summary"]["extra_date_count"] == 1
    assert "GACOS_EXTRA_DATE" in _import_codes(section)


def test_prepare_gacos_import_dir_requires_bbox(tmp_path: Path) -> None:
    import_dir = _write_gacos_products(tmp_path / "gacos_products", _GACOS_IMPORT_DATES)
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            "shiliushubao",
            "--output-root",
            str(tmp_path),
            "--gacos-import-dir",
            str(import_dir),
        ]
    )
    assert code != 0


def test_prepare_gacos_import_missing_dir_fails(tmp_path: Path) -> None:
    code = _prepare_with_gacos_import(tmp_path, tmp_path / "no_gacos_here")
    assert code != 0


def test_prepare_gacos_import_with_plan_has_both_sections(tmp_path: Path) -> None:
    import_dir = _write_gacos_products(tmp_path / "gacos_products", _GACOS_IMPORT_DATES)
    json_path, _ = report_paths(tmp_path, "shiliushubao")
    code = _prepare_with_gacos_import(tmp_path, import_dir, "--gacos-plan")
    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert find_section(data, "GACOS request planning") is not None
    assert find_section(data, "GACOS import check") is not None


def test_prepare_gacos_import_is_read_only(tmp_path: Path) -> None:
    import_dir = _write_gacos_products(tmp_path / "gacos_products", _GACOS_IMPORT_DATES)
    before = {entry.name: entry.stat().st_size for entry in import_dir.iterdir()}
    code = _prepare_with_gacos_import(tmp_path, import_dir)
    assert code == 0
    after = {entry.name: entry.stat().st_size for entry in import_dir.iterdir()}
    assert before == after
    # Import checking alone must not create the GACOS requests output tree.
    assert not (tmp_path / "shiliushubao" / "05_atmosphere").exists()
