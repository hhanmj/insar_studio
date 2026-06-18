"""Tests for Sentinel-1 SLC scene-name parsing (Task 006)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from insar_prep.core.enums import BeamMode, Platform, Polarization, ProductType, TaskStatus
from insar_prep.core.exceptions import InputValidationError
from insar_prep.providers.asf.scene_parser import (
    deduplicate_scenes,
    parse_scene_name,
    polarization_code_to_channels,
)

S1A_NAME = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
S1A_URL = f"https://datapool.asf.alaska.edu/SLC/SA/{S1A_NAME}.zip"


def test_parse_scene_basic_fields() -> None:
    scene = parse_scene_name(S1A_NAME)
    assert scene.scene_id == S1A_NAME
    assert scene.platform is Platform.S1A
    assert scene.product_type is ProductType.SLC
    assert scene.beam_mode is BeamMode.IW
    assert scene.polarization is Polarization.DV
    assert scene.acquisition_datetime == datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    assert scene.absolute_orbit == 52000
    assert scene.url is None
    assert scene.download_status is TaskStatus.PENDING


def test_parse_scene_from_url_sets_url() -> None:
    scene = parse_scene_name(S1A_URL)
    assert scene.url == S1A_URL
    assert scene.scene_id == S1A_NAME


def test_platform_and_polarization_detection() -> None:
    s1b = parse_scene_name("S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064DEF_5678")
    assert s1b.platform is Platform.S1B
    s1c = parse_scene_name("S1C_IW_SLC__1SSV_20240113T100000_20240113T100027_052100_064DEF_5678")
    assert s1c.platform is Platform.S1C
    assert s1c.polarization is Polarization.SV


def test_polarization_codes_are_preserved() -> None:
    base = "S1A_IW_SLC__1{code}_20240101T100000_20240101T100027_052000_064ABC_1234"
    assert parse_scene_name(base.format(code="SSH")).polarization is Polarization.SH
    assert parse_scene_name(base.format(code="SSV")).polarization is Polarization.SV
    dh = parse_scene_name(base.format(code="SDH")).polarization
    dv = parse_scene_name(base.format(code="SDV")).polarization
    assert dh is Polarization.DH
    assert dh is not Polarization.HH
    assert dv is Polarization.DV
    assert dv is not Polarization.VV


def test_polarization_code_to_channels() -> None:
    assert polarization_code_to_channels(Polarization.SH) == ("HH",)
    assert polarization_code_to_channels(Polarization.SV) == ("VV",)
    assert polarization_code_to_channels(Polarization.DH) == ("HH", "HV")
    assert polarization_code_to_channels(Polarization.DV) == ("VV", "VH")
    assert polarization_code_to_channels("DV") == ("VV", "VH")


def test_non_slc_raises() -> None:
    with pytest.raises(InputValidationError):
        parse_scene_name("S1A_IW_GRDH_1SDV_20240101T100000_20240101T100027_052000_064ABC_1234")


def test_non_sentinel_raises() -> None:
    with pytest.raises(InputValidationError):
        parse_scene_name("LC08_L1TP_120038_20240101_20240101_02_T1")


def test_safe_extension_is_stripped() -> None:
    scene = parse_scene_name(f"{S1A_NAME}.SAFE")
    assert scene.scene_id == S1A_NAME


def test_deduplicate_scenes() -> None:
    first = parse_scene_name(S1A_NAME)
    second = parse_scene_name(S1A_URL)
    unique, duplicates = deduplicate_scenes([first, second])
    assert len(unique) == 1
    assert duplicates == [S1A_NAME]
