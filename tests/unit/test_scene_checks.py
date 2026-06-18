"""Tests for scene consistency checks (Task 007)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from insar_prep.core.enums import AoiSource, BeamMode, Platform, Polarization, ProductType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi, BBox, Scene
from insar_prep.quality.scene_checks import (
    SCENE_BEAM_MISMATCH,
    SCENE_COVERAGE_NOT_CHECKED,
    SCENE_DUPLICATE_ID,
    SCENE_DUPLICATE_TIME,
    SCENE_EMPTY,
    SCENE_NO_SOURCE,
    SCENE_PLATFORM_MIXED,
    SCENE_POLARIZATION_MIXED,
    SCENE_PRODUCT_MISMATCH,
    SCENE_URL_MISSING,
    check_scene_collection,
)

_T0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
_T1 = datetime(2024, 1, 13, 10, 0, 0, tzinfo=UTC)


def make_scene(
    scene_id: str,
    *,
    platform: Platform = Platform.S1A,
    product_type: ProductType = ProductType.SLC,
    beam_mode: BeamMode = BeamMode.IW,
    polarization: Polarization = Polarization.DV,
    url: str | None = "https://datapool.asf.alaska.edu/SLC/x.zip",
    local_path: str | None = None,
    acquired: datetime = _T0,
) -> Scene:
    return Scene(
        scene_id=scene_id,
        platform=platform,
        product_type=product_type,
        beam_mode=beam_mode,
        polarization=polarization,
        url=url,
        local_path=local_path,
        acquisition_datetime=acquired,
    )


def _codes(report: object) -> set[str]:
    return {issue.code for issue in report.issues}  # type: ignore[attr-defined]


def test_empty_scene_list_produces_error() -> None:
    report = check_scene_collection([])
    assert report.has_errors
    assert SCENE_EMPTY in _codes(report)
    assert report.total_scenes == 0


def test_normal_collection_has_no_errors() -> None:
    scenes = [make_scene("S1A_a", acquired=_T0), make_scene("S1A_b", acquired=_T1)]
    report = check_scene_collection(scenes)
    assert not report.has_errors
    assert report.valid_scenes == 2


def test_duplicate_scene_id_is_error() -> None:
    scenes = [make_scene("dup", acquired=_T0), make_scene("dup", acquired=_T1)]
    report = check_scene_collection(scenes)
    assert SCENE_DUPLICATE_ID in _codes(report)
    assert report.has_errors


def test_duplicate_acquisition_time_is_warning() -> None:
    scenes = [make_scene("a", acquired=_T0), make_scene("b", acquired=_T0)]
    report = check_scene_collection(scenes)
    assert SCENE_DUPLICATE_TIME in _codes(report)


def test_non_slc_is_detected() -> None:
    report = check_scene_collection([make_scene("grd", product_type=ProductType.GRD)])
    assert SCENE_PRODUCT_MISMATCH in _codes(report)
    assert report.has_errors


def test_non_iw_is_detected() -> None:
    report = check_scene_collection([make_scene("ew", beam_mode=BeamMode.EW)])
    assert SCENE_BEAM_MISMATCH in _codes(report)
    assert report.has_errors


def test_mixed_dh_dv_is_warning() -> None:
    scenes = [
        make_scene("dh", polarization=Polarization.DH, acquired=_T0),
        make_scene("dv", polarization=Polarization.DV, acquired=_T1),
    ]
    report = check_scene_collection(scenes)
    assert SCENE_POLARIZATION_MIXED in _codes(report)
    assert report.has_warnings
    assert not report.has_errors


def test_url_missing_is_error_when_required() -> None:
    report = check_scene_collection(
        [make_scene("a", url=None, local_path="C:/x.zip")], require_urls=True
    )
    assert SCENE_URL_MISSING in _codes(report)
    assert report.has_errors


def test_url_missing_is_warning_by_default() -> None:
    report = check_scene_collection([make_scene("a", url=None, local_path="C:/x.zip")])
    assert SCENE_URL_MISSING in _codes(report)
    assert not report.has_errors


def test_missing_source_is_warning() -> None:
    report = check_scene_collection([make_scene("a", url=None, local_path=None)])
    assert SCENE_NO_SOURCE in _codes(report)


def test_platform_mix_does_not_fail() -> None:
    scenes = [
        make_scene("a", platform=Platform.S1A, acquired=_T0),
        make_scene("b", platform=Platform.S1B, acquired=_T1),
    ]
    report = check_scene_collection(scenes)
    assert SCENE_PLATFORM_MIXED in _codes(report)
    assert not report.has_errors


def test_coverage_not_checked_when_aoi_present() -> None:
    aoi = Aoi(
        source=AoiSource.MANUAL_BBOX,
        bbox=BBox(west=109.5, east=117.5, south=20.0, north=25.5),
    )
    report = check_scene_collection([make_scene("a")], processing_aoi=aoi)
    assert SCENE_COVERAGE_NOT_CHECKED in _codes(report)


def test_report_is_json_serializable() -> None:
    scenes = [make_scene("a", acquired=_T0), make_scene("a", acquired=_T1)]
    report = check_scene_collection(scenes)
    assert isinstance(json.dumps(report.to_dict()), str)


def test_invalid_input_type_raises() -> None:
    with pytest.raises(InputValidationError):
        check_scene_collection("not a list")  # type: ignore[arg-type]
