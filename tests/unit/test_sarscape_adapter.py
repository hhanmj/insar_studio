"""Tests for the SARscape adapter naming helpers (Task 003)."""

from __future__ import annotations

import pytest

from insar_prep.sar_apps.sarscape import (
    ensure_sarscape_dem_name,
    sarscape_ready_dem_path,
)


def test_ensure_dem_name_basic() -> None:
    assert ensure_sarscape_dem_name("shiliushubao") == "shiliushubao_dem"
    assert ensure_sarscape_dem_name("guangdong_2024") == "guangdong_2024_dem"


def test_ensure_dem_name_ends_with_dem() -> None:
    name = ensure_sarscape_dem_name("guangdong")
    assert name.endswith("_dem")
    assert "-" not in name


def test_ensure_dem_name_allows_legacy_dotted_suffix() -> None:
    assert ensure_sarscape_dem_name("guangdong", ".tif") == "guangdong_dem.tif"


def test_ensure_dem_name_rejects_unsafe_input() -> None:
    with pytest.raises(ValueError):
        ensure_sarscape_dem_name("Guangxi-stack-2024")
    with pytest.raises(ValueError):
        ensure_sarscape_dem_name("guangdong_")


def test_sarscape_ready_dem_path_structure() -> None:
    path = sarscape_ready_dem_path("shiliushubao")
    assert path.parts[-1] == "shiliushubao_dem"
    assert path.parts[-2] == "DEM"
    assert path.parts[-3] == "06_sarscape_ready"


def test_sarscape_ready_dem_path_rejects_unsafe_region() -> None:
    with pytest.raises(ValueError):
        sarscape_ready_dem_path("guang dong")
