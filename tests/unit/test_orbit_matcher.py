"""Tests for Sentinel-1 orbit matching (Task 009)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from insar_prep.core.enums import Platform
from insar_prep.core.models import Scene
from insar_prep.providers.orbit.orbit_matcher import (
    ORBIT_PLATFORM_MISMATCH,
    ORBIT_SELECTED_POEORB,
    ORBIT_TIME_NOT_COVERED,
    match_orbit_for_scene,
    match_orbits_for_scenes,
)
from insar_prep.providers.orbit.types import OrbitFile, OrbitType

_SCENE_TIME = datetime(2024, 1, 2, 5, 0, 0, tzinfo=UTC)
_WIN_START = datetime(2024, 1, 1, 22, 0, 0, tzinfo=UTC)
_WIN_STOP = datetime(2024, 1, 3, 0, 0, 0, tzinfo=UTC)
_CREATION = datetime(2024, 1, 4, 0, 0, 0, tzinfo=UTC)


def make_orbit(
    orbit_type: OrbitType,
    *,
    platform: Platform = Platform.S1A,
    start: datetime = _WIN_START,
    stop: datetime = _WIN_STOP,
    creation: datetime = _CREATION,
    name: str = "orbit.EOF",
) -> OrbitFile:
    return OrbitFile(
        file_name=name,
        platform=platform,
        orbit_type=orbit_type,
        creation_datetime=creation,
        validity_start=start,
        validity_stop=stop,
    )


def make_scene(platform: Platform = Platform.S1A, acquired: datetime = _SCENE_TIME) -> Scene:
    return Scene(scene_id="scene1", platform=platform, acquisition_datetime=acquired)


def test_match_within_validity() -> None:
    result = match_orbit_for_scene(make_scene(), [make_orbit(OrbitType.POEORB)])
    assert result.is_matched
    assert result.matched_orbit is not None
    assert result.matched_orbit.orbit_type is OrbitType.POEORB


def test_unmatched_when_time_outside() -> None:
    orbit = make_orbit(
        OrbitType.POEORB,
        start=datetime(2024, 2, 1, tzinfo=UTC),
        stop=datetime(2024, 2, 2, tzinfo=UTC),
    )
    result = match_orbit_for_scene(make_scene(), [orbit])
    assert not result.is_matched
    assert any(issue.code == ORBIT_TIME_NOT_COVERED for issue in result.issues)


def test_platform_mismatch_not_matched() -> None:
    orbit = make_orbit(OrbitType.POEORB, platform=Platform.S1B)
    result = match_orbit_for_scene(make_scene(platform=Platform.S1A), [orbit])
    assert not result.is_matched
    assert any(issue.code == ORBIT_PLATFORM_MISMATCH for issue in result.issues)


def test_poeorb_preferred() -> None:
    orbits = [
        make_orbit(OrbitType.RESORB),
        make_orbit(OrbitType.MOEORB),
        make_orbit(OrbitType.POEORB),
    ]
    result = match_orbit_for_scene(make_scene(), orbits)
    assert result.matched_orbit is not None
    assert result.matched_orbit.orbit_type is OrbitType.POEORB
    assert any(issue.code == ORBIT_SELECTED_POEORB for issue in result.issues)


def test_moeorb_preferred_over_resorb() -> None:
    orbits = [make_orbit(OrbitType.RESORB), make_orbit(OrbitType.MOEORB)]
    result = match_orbit_for_scene(make_scene(), orbits)
    assert result.matched_orbit is not None
    assert result.matched_orbit.orbit_type is OrbitType.MOEORB


def test_newest_creation_within_type() -> None:
    older = make_orbit(
        OrbitType.POEORB, creation=datetime(2024, 1, 4, tzinfo=UTC), name="older.EOF"
    )
    newer = make_orbit(
        OrbitType.POEORB, creation=datetime(2024, 1, 6, tzinfo=UTC), name="newer.EOF"
    )
    result = match_orbit_for_scene(make_scene(), [older, newer])
    assert result.matched_orbit is not None
    assert result.matched_orbit.file_name == "newer.EOF"


def test_batch_report_counts() -> None:
    scenes = [
        make_scene(),
        Scene(scene_id="scene2", platform=Platform.S1B, acquisition_datetime=_SCENE_TIME),
    ]
    report = match_orbits_for_scenes(scenes, [make_orbit(OrbitType.POEORB)])
    assert report.total_scenes == 2
    assert report.matched_scenes == 1
    assert report.unmatched_scenes == 1


def test_report_is_json_serializable() -> None:
    report = match_orbits_for_scenes([make_scene()], [make_orbit(OrbitType.POEORB)])
    assert isinstance(json.dumps(report.to_dict()), str)
