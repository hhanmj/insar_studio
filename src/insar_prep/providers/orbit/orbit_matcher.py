"""Sentinel-1 orbit matching (Task 009).

Matches scenes to local orbit files by platform and validity window, preferring
POEORB > MOEORB > RESORB (and the newest creation time within a type). Purely
offline; unmatched scenes produce issues instead of crashing.
"""

from __future__ import annotations

from insar_prep.core.events import EventType
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import Scene
from insar_prep.providers.orbit.types import (
    OrbitFile,
    OrbitMatchIssue,
    OrbitMatchReport,
    OrbitMatchResult,
    OrbitType,
)
from insar_prep.quality.types import CheckSeverity

logger = get_logger("providers.orbit.matcher")

ORBIT_PLATFORM_MISMATCH = "ORBIT_PLATFORM_MISMATCH"
ORBIT_TIME_NOT_COVERED = "ORBIT_TIME_NOT_COVERED"
ORBIT_MISSING = "ORBIT_MISSING"
ORBIT_MULTIPLE_CANDIDATES = "ORBIT_MULTIPLE_CANDIDATES"
ORBIT_SELECTED_POEORB = "ORBIT_SELECTED_POEORB"
ORBIT_SELECTED_MOEORB = "ORBIT_SELECTED_MOEORB"
ORBIT_SELECTED_RESORB = "ORBIT_SELECTED_RESORB"

_PRIORITY = {
    OrbitType.POEORB: 3,
    OrbitType.MOEORB: 2,
    OrbitType.RESORB: 1,
    OrbitType.UNKNOWN: 0,
}
_SELECTED_CODE = {
    OrbitType.POEORB: ORBIT_SELECTED_POEORB,
    OrbitType.MOEORB: ORBIT_SELECTED_MOEORB,
    OrbitType.RESORB: ORBIT_SELECTED_RESORB,
}


def _select_best(candidates: list[OrbitFile]) -> OrbitFile:
    return max(candidates, key=lambda orbit: (_PRIORITY[orbit.orbit_type], orbit.creation_datetime))


def _unmatched(scene: Scene, issues: list[OrbitMatchIssue]) -> OrbitMatchResult:
    return OrbitMatchResult(scene_id=scene.scene_id, issues=issues, is_matched=False)


def match_orbit_for_scene(scene: Scene, orbit_files: list[OrbitFile]) -> OrbitMatchResult:
    """Match a single scene to the best covering orbit file."""
    if scene.acquisition_datetime is None:
        issue = OrbitMatchIssue(
            code=ORBIT_MISSING,
            severity=CheckSeverity.WARNING,
            message="scene has no acquisition_datetime",
            scene_id=scene.scene_id,
        )
        return _unmatched(scene, [issue])

    platform_matches = [orbit for orbit in orbit_files if orbit.platform == scene.platform]
    candidates = [
        orbit
        for orbit in platform_matches
        if orbit.validity_start <= scene.acquisition_datetime <= orbit.validity_stop
    ]
    if not candidates:
        if not platform_matches:
            code = ORBIT_PLATFORM_MISMATCH if orbit_files else ORBIT_MISSING
            message = "no orbit matches the scene platform" if orbit_files else "no orbit files"
        else:
            code = ORBIT_TIME_NOT_COVERED
            message = "no orbit validity period covers the scene time"
        issue = OrbitMatchIssue(
            code=code,
            severity=CheckSeverity.WARNING,
            message=message,
            scene_id=scene.scene_id,
        )
        return _unmatched(scene, [issue])

    best = _select_best(candidates)
    issues: list[OrbitMatchIssue] = []
    if len(candidates) > 1:
        issues.append(
            OrbitMatchIssue(
                code=ORBIT_MULTIPLE_CANDIDATES,
                severity=CheckSeverity.INFO,
                message=f"{len(candidates)} candidate orbits cover the scene",
                scene_id=scene.scene_id,
                details={"count": len(candidates)},
            )
        )
    issues.append(
        OrbitMatchIssue(
            code=_SELECTED_CODE[best.orbit_type],
            severity=CheckSeverity.INFO,
            message=f"selected {best.orbit_type.value} orbit",
            scene_id=scene.scene_id,
            orbit_file=best.file_name,
        )
    )
    return OrbitMatchResult(
        scene_id=scene.scene_id,
        matched_orbit=best,
        candidate_orbits=candidates,
        issues=issues,
        is_matched=True,
    )


def match_orbits_for_scenes(scenes: list[Scene], orbit_files: list[OrbitFile]) -> OrbitMatchReport:
    """Match a collection of scenes to orbit files and build a report."""
    results = [match_orbit_for_scene(scene, orbit_files) for scene in scenes]
    matched = sum(1 for result in results if result.is_matched)
    all_issues = [issue for result in results for issue in result.issues]
    summary = {
        "orbit_files": len(orbit_files),
        "scenes": len(scenes),
        "matched": matched,
        "unmatched": len(scenes) - matched,
        "orbit_types": sorted({orbit.orbit_type.value for orbit in orbit_files}),
    }
    report = OrbitMatchReport(
        total_scenes=len(scenes),
        matched_scenes=matched,
        unmatched_scenes=len(scenes) - matched,
        results=results,
        issues=all_issues,
        summary=summary,
    )
    log_event(
        logger,
        EventType.ORBIT_MATCH_FINISHED,
        f"matched {matched}/{len(scenes)} scenes",
        module="orbit",
        payload={"matched": matched, "total": len(scenes)},
    )
    return report
