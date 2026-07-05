"""Tests for Sentinel-1 orbit filename parsing and scanning (Task 009)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from insar_prep.core.enums import Platform
from insar_prep.core.exceptions import OrbitMatchingError
from insar_prep.providers.orbit.orbit_parser import parse_orbit_filename, scan_orbit_directory
from insar_prep.providers.orbit.types import OrbitType

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "orbits"
POEORB = "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T225942_20240103T005942.EOF"
RESORB = "S1A_OPER_AUX_RESORB_OPOD_20240101T130000_V20240101T095942_20240101T131242.EOF"
MOEORB = "S1A_OPER_AUX_MOEORB_OPOD_20240102T120000_V20240101T225942_20240103T005942.EOF"


def test_parse_poeorb_fields() -> None:
    orbit = parse_orbit_filename(POEORB)
    assert orbit.file_name == POEORB
    assert orbit.platform is Platform.S1A
    assert orbit.orbit_type is OrbitType.POEORB
    assert orbit.creation_datetime == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)
    assert orbit.validity_start == datetime(2024, 1, 1, 22, 59, 42, tzinfo=UTC)
    assert orbit.validity_stop == datetime(2024, 1, 3, 0, 59, 42, tzinfo=UTC)


def test_parse_resorb() -> None:
    assert parse_orbit_filename(RESORB).orbit_type is OrbitType.RESORB


def test_parse_moeorb() -> None:
    assert parse_orbit_filename(MOEORB).orbit_type is OrbitType.MOEORB


def test_invalid_filename_raises() -> None:
    with pytest.raises(OrbitMatchingError):
        parse_orbit_filename("not_an_orbit_file.txt")


def test_validity_stop_before_start_raises() -> None:
    bad = "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240103T005942_20240101T225942.EOF"
    with pytest.raises(OrbitMatchingError):
        parse_orbit_filename(bad)


def test_scan_recursive_finds_all_eof() -> None:
    orbits = scan_orbit_directory(FIXTURES, recursive=True)
    assert len(orbits) == 3
    assert any("S1B" in orbit.file_name for orbit in orbits)


def test_scan_non_recursive_top_level_only() -> None:
    orbits = scan_orbit_directory(FIXTURES, recursive=False)
    assert len(orbits) == 2


def test_scan_skips_non_eof_files() -> None:
    orbits = scan_orbit_directory(FIXTURES, recursive=True)
    assert all(orbit.file_name.upper().endswith(".EOF") for orbit in orbits)


def test_scan_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(OrbitMatchingError):
        scan_orbit_directory(tmp_path / "does_not_exist")
