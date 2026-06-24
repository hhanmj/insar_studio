"""Tests for the GACOS product importer (Task 053). Offline, stdlib only."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from insar_prep.core.exceptions import AtmosphereProductError
from insar_prep.providers.gacos.importer import (
    GACOS_IMPORT_OK,
    GACOS_NO_PRODUCTS_FOUND,
    GACOS_RSC_MISSING,
    GACOS_SIZE_MISMATCH,
    import_gacos_products,
)


def _write_product(
    directory: Path,
    day: str,
    *,
    width: int = 3,
    length: int = 2,
    ztd_bytes: int | None = None,
) -> None:
    """Write a valid GACOS .ztd + .ztd.rsc pair (.ztd = 4*width*length bytes)."""
    directory.mkdir(parents=True, exist_ok=True)
    rsc = directory / f"{day}.ztd.rsc"
    rsc.write_text(
        f"WIDTH {width}\nFILE_LENGTH {length}\nX_FIRST 10.0\nY_FIRST 46.0\n", encoding="utf-8"
    )
    size = ztd_bytes if ztd_bytes is not None else 4 * width * length
    (directory / f"{day}.ztd").write_bytes(b"\x00" * size)


def test_import_from_directory_valid(tmp_path: Path) -> None:
    src = tmp_path / "downloads"
    _write_product(src, "20230101")
    _write_product(src, "20230113")
    out = tmp_path / "out"

    result = import_gacos_products([src], out)
    assert not result.has_errors
    assert result.summary["product_date_count"] == 2
    assert result.summary["valid_product_count"] == 2
    assert (out / "20230101.ztd").is_file()
    assert (out / "20230101.ztd.rsc").is_file()
    assert any(i.code == GACOS_IMPORT_OK for i in result.issues)
    assert result.found_dates == [date(2023, 1, 1), date(2023, 1, 13)]


def test_import_from_zip_archive(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    _write_product(staging, "20230101")
    archive = tmp_path / "gacos.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(staging / "20230101.ztd", "20230101.ztd")
        zf.write(staging / "20230101.ztd.rsc", "20230101.ztd.rsc")
    out = tmp_path / "out"

    result = import_gacos_products([archive], out)
    assert not result.has_errors
    assert (out / "20230101.ztd").is_file()
    assert archive in result.extracted_archives


def test_size_mismatch_is_error(tmp_path: Path) -> None:
    src = tmp_path / "downloads"
    _write_product(src, "20230101", width=3, length=2, ztd_bytes=10)  # should be 24
    out = tmp_path / "out"

    result = import_gacos_products([src], out)
    assert result.has_errors
    assert any(i.code == GACOS_SIZE_MISMATCH for i in result.issues)
    assert result.summary["valid_product_count"] == 0


def test_missing_rsc_is_error(tmp_path: Path) -> None:
    src = tmp_path / "downloads"
    src.mkdir()
    (src / "20230101.ztd").write_bytes(b"\x00" * 24)
    out = tmp_path / "out"

    result = import_gacos_products([src], out)
    assert result.has_errors
    assert any(i.code == GACOS_RSC_MISSING for i in result.issues)


def test_no_products_found(tmp_path: Path) -> None:
    src = tmp_path / "empty"
    src.mkdir()
    (src / "readme.txt").write_text("nothing here", encoding="utf-8")
    out = tmp_path / "out"

    result = import_gacos_products([src], out)
    assert result.has_errors
    assert any(i.code == GACOS_NO_PRODUCTS_FOUND for i in result.issues)


def test_expected_dates_coverage(tmp_path: Path) -> None:
    src = tmp_path / "downloads"
    _write_product(src, "20230101")
    out = tmp_path / "out"
    expected = [date(2023, 1, 1), date(2023, 1, 13)]

    result = import_gacos_products([src], out, expected_dates=expected)
    assert result.missing_dates == [date(2023, 1, 13)]
    assert result.has_errors  # a missing expected date is an error


def test_move_removes_loose_source(tmp_path: Path) -> None:
    src = tmp_path / "downloads"
    _write_product(src, "20230101")
    out = tmp_path / "out"

    import_gacos_products([src], out, move=True)
    assert not (src / "20230101.ztd").exists()
    assert (out / "20230101.ztd").is_file()


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.ztd", b"\x00" * 24)
    out = tmp_path / "out"
    with pytest.raises(AtmosphereProductError):
        import_gacos_products([archive], out)
