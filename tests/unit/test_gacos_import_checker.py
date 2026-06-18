"""Tests for the GACOS product import checker (Task 013)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from insar_prep.core.exceptions import AtmosphereProductError
from insar_prep.core.models import Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.providers.gacos.import_checker import (
    GACOS_EMPTY_FILE,
    GACOS_EXTRA_DATE,
    GACOS_FILENAME_INVALID,
    GACOS_IMPORT_READY,
    GACOS_RSC_MISSING,
    GACOS_ZTD_MISSING,
    check_gacos_products,
    scan_gacos_product_directory,
)
from insar_prep.providers.gacos.planner import create_gacos_request_plan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "gacos"
PRODUCTS_OK = FIXTURES / "products_ok"


def plan_for_dates(tmp_path: Path, dates: list[date]):
    scenes = [Scene(acquisition_datetime=datetime(d.year, d.month, d.day, 12)) for d in dates]
    return create_gacos_request_plan(
        region_id="r1",
        region_safe_name="shiliushubao",
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        scenes=scenes,
        output_root=tmp_path,
    )


def write_product(directory: Path, name: str, content: bytes = b"data") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(content)
    return target


def test_all_products_present_passes(tmp_path: Path) -> None:
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1), date(2023, 1, 13)])
    report = check_gacos_products(request_plan=plan, product_directory=PRODUCTS_OK)
    assert not report.has_errors
    assert report.missing_dates == []
    assert report.extra_dates == []
    assert set(report.found_dates) == {date(2023, 1, 1), date(2023, 1, 13)}
    assert any(issue.code == GACOS_IMPORT_READY for issue in report.issues)


def test_missing_ztd_is_error(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd.rsc")
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert report.has_errors
    assert any(issue.code == GACOS_ZTD_MISSING for issue in report.issues)


def test_missing_rsc_is_error(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd")
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert report.has_errors
    assert any(issue.code == GACOS_RSC_MISSING for issue in report.issues)


def test_extra_date_is_warning(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd")
    write_product(products, "20230101.ztd.rsc")
    write_product(products, "20230225.ztd")
    write_product(products, "20230225.ztd.rsc")
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert report.has_warnings
    assert date(2023, 2, 25) in report.extra_dates
    assert any(issue.code == GACOS_EXTRA_DATE for issue in report.issues)


def test_invalid_filename_is_warning(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd")
    write_product(products, "20230101.ztd.rsc")
    write_product(products, "2023.ztd")  # not YYYYMMDD
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert any(issue.code == GACOS_FILENAME_INVALID for issue in report.issues)
    assert report.has_warnings


def test_empty_file_is_error(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd", content=b"")  # empty
    write_product(products, "20230101.ztd.rsc", content=b"WIDTH 10\n")
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert report.has_errors
    assert any(issue.code == GACOS_EMPTY_FILE for issue in report.issues)


def test_missing_directory_raises(tmp_path: Path) -> None:
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    with pytest.raises(AtmosphereProductError):
        check_gacos_products(request_plan=plan, product_directory=tmp_path / "nope")


def test_missing_dates_are_listed(tmp_path: Path) -> None:
    products = tmp_path / "products"
    write_product(products, "20230101.ztd")
    write_product(products, "20230101.ztd.rsc")
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1), date(2023, 1, 13)])
    report = check_gacos_products(request_plan=plan, product_directory=products)
    assert date(2023, 1, 13) in report.missing_dates
    assert report.has_errors


def test_report_is_json_serializable(tmp_path: Path) -> None:
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1), date(2023, 1, 13)])
    report = check_gacos_products(request_plan=plan, product_directory=PRODUCTS_OK)
    encoded = json.dumps(report.to_dict())
    assert isinstance(encoded, str)
    assert "2023-01-01" in encoded


def test_scan_groups_pairs_by_date() -> None:
    products = scan_gacos_product_directory(PRODUCTS_OK)
    assert [product.date for product in products] == [date(2023, 1, 1), date(2023, 1, 13)]
    assert all(product.has_ztd and product.has_rsc for product in products)
    assert all((product.ztd_size_bytes or 0) > 0 for product in products)


def test_scan_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(AtmosphereProductError):
        scan_gacos_product_directory(tmp_path / "missing")


def test_check_does_not_modify_files(tmp_path: Path) -> None:
    products = tmp_path / "products"
    ztd = write_product(products, "20230101.ztd", content=b"abc")
    rsc = write_product(products, "20230101.ztd.rsc", content=b"WIDTH 10\n")
    before = {entry.name: entry.stat().st_size for entry in products.iterdir()}
    plan = plan_for_dates(tmp_path, [date(2023, 1, 1)])
    check_gacos_products(request_plan=plan, product_directory=products)
    after = {entry.name: entry.stat().st_size for entry in products.iterdir()}
    assert before == after
    assert ztd.exists()
    assert rsc.exists()
