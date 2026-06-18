"""Tests for SARscape-safe naming utilities (Task 003)."""

from __future__ import annotations

import pytest

from insar_prep.core.naming import (
    is_sarscape_safe_name,
    sarscape_safe_name,
    validate_sarscape_ready_path,
)


def test_safe_name_conversions() -> None:
    assert sarscape_safe_name("Guangxi-stack-2024") == "guangxi_stack_2024"
    assert sarscape_safe_name("COP30-WGS84-ellipsoid") == "cop30_wgs84_ellipsoid"
    assert sarscape_safe_name("  Shiliushubao test area  ") == "shiliushubao_test_area"


def test_safe_name_collapses_illegal_runs() -> None:
    assert sarscape_safe_name("a---b   c___d") == "a_b_c_d"
    assert sarscape_safe_name("广东@@@guangdong") == "guangdong"


def test_safe_name_empty_raises() -> None:
    with pytest.raises(ValueError):
        sarscape_safe_name("")
    with pytest.raises(ValueError):
        sarscape_safe_name("   ")


def test_safe_name_all_symbols_raises() -> None:
    with pytest.raises(ValueError):
        sarscape_safe_name("***")
    with pytest.raises(ValueError):
        sarscape_safe_name("---")


def test_is_sarscape_safe_name() -> None:
    assert is_sarscape_safe_name("guangdong")
    assert is_sarscape_safe_name("guangdong_2024")
    assert not is_sarscape_safe_name("Guangdong")
    assert not is_sarscape_safe_name("guangdong-2024")
    assert not is_sarscape_safe_name("guangdong__2024")
    assert not is_sarscape_safe_name("_guangdong")
    assert not is_sarscape_safe_name("guangdong_")


def test_safe_name_idempotent() -> None:
    for name in ("guangdong", "guangdong_2024", "south_china_insar_2026"):
        assert sarscape_safe_name(name) == name


def test_validate_path_accepts_clean_path() -> None:
    validate_sarscape_ready_path("06_sarscape_ready/DEM/guangdong_dem.tif")


def test_validate_path_rejects_hyphen() -> None:
    with pytest.raises(ValueError):
        validate_sarscape_ready_path("06_sarscape_ready/DEM/guangxi-stack_dem.tif")


def test_validate_path_rejects_space() -> None:
    with pytest.raises(ValueError):
        validate_sarscape_ready_path("06_sarscape_ready/DEM/guang dong_dem.tif")
