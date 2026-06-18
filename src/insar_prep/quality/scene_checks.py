"""Scene consistency checks (Task 007).

Quality checks operate purely on already-parsed ``Scene`` lists and AOI data
structures. No SAFE reading, no network, no downloads, no orbit matching, and no
report export. Results are returned as a serializable :class:`SceneCheckReport`.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from insar_prep.core.enums import BeamMode, Polarization, ProductType
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import Aoi, Scene
from insar_prep.quality.types import CheckIssue, CheckSeverity, SceneCheckReport

logger = get_logger("quality.scene_checks")

SCENE_EMPTY = "SCENE_EMPTY"
SCENE_DUPLICATE_ID = "SCENE_DUPLICATE_ID"
SCENE_DUPLICATE_TIME = "SCENE_DUPLICATE_TIME"
SCENE_PRODUCT_MISMATCH = "SCENE_PRODUCT_MISMATCH"
SCENE_BEAM_MISMATCH = "SCENE_BEAM_MISMATCH"
SCENE_POLARIZATION_MISMATCH = "SCENE_POLARIZATION_MISMATCH"
SCENE_POLARIZATION_MIXED = "SCENE_POLARIZATION_MIXED"
SCENE_URL_MISSING = "SCENE_URL_MISSING"
SCENE_NO_SOURCE = "SCENE_NO_SOURCE"
SCENE_PLATFORM_MIXED = "SCENE_PLATFORM_MIXED"
SCENE_COVERAGE_NOT_CHECKED = "SCENE_COVERAGE_NOT_CHECKED"


def _check_duplicate_ids(scenes: list[Scene]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for scene_id, count in Counter(scene.scene_id for scene in scenes).items():
        if count > 1:
            issues.append(
                CheckIssue(
                    code=SCENE_DUPLICATE_ID,
                    severity=CheckSeverity.ERROR,
                    message=f"scene_id appears {count} times",
                    scene_id=scene_id,
                    details={"count": count},
                )
            )
    return issues


def _check_duplicate_times(scenes: list[Scene]) -> list[CheckIssue]:
    groups: dict[str, list[str]] = defaultdict(list)
    for scene in scenes:
        if scene.acquisition_datetime is not None:
            groups[scene.acquisition_datetime.isoformat()].append(scene.scene_id)
    issues: list[CheckIssue] = []
    for timestamp, scene_ids in groups.items():
        if len(scene_ids) > 1:
            issues.append(
                CheckIssue(
                    code=SCENE_DUPLICATE_TIME,
                    severity=CheckSeverity.WARNING,
                    message=f"{len(scene_ids)} scenes share an acquisition time",
                    details={"acquisition_datetime": timestamp, "scene_ids": scene_ids},
                )
            )
    return issues


def _check_single_scene(
    scene: Scene,
    *,
    require_urls: bool,
    expected_product_type: ProductType | None,
    expected_beam_mode: BeamMode | None,
    expected_polarization: Polarization | None,
    invalid: set[str],
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if expected_product_type is not None and scene.product_type != expected_product_type:
        issues.append(
            CheckIssue(
                code=SCENE_PRODUCT_MISMATCH,
                severity=CheckSeverity.ERROR,
                message=f"product_type {scene.product_type.value} != {expected_product_type.value}",
                scene_id=scene.scene_id,
                field="product_type",
                details={
                    "expected": expected_product_type.value,
                    "actual": scene.product_type.value,
                },
            )
        )
        invalid.add(scene.scene_id)
    if expected_beam_mode is not None and scene.beam_mode != expected_beam_mode:
        issues.append(
            CheckIssue(
                code=SCENE_BEAM_MISMATCH,
                severity=CheckSeverity.ERROR,
                message=f"beam_mode {scene.beam_mode.value} != {expected_beam_mode.value}",
                scene_id=scene.scene_id,
                field="beam_mode",
                details={"expected": expected_beam_mode.value, "actual": scene.beam_mode.value},
            )
        )
        invalid.add(scene.scene_id)
    if expected_polarization is not None and scene.polarization != expected_polarization:
        issues.append(
            CheckIssue(
                code=SCENE_POLARIZATION_MISMATCH,
                severity=CheckSeverity.ERROR,
                message=f"polarization {scene.polarization.value} != {expected_polarization.value}",
                scene_id=scene.scene_id,
                field="polarization",
                details={
                    "expected": expected_polarization.value,
                    "actual": scene.polarization.value,
                },
            )
        )
        invalid.add(scene.scene_id)
    if not scene.url:
        severity = CheckSeverity.ERROR if require_urls else CheckSeverity.WARNING
        issues.append(
            CheckIssue(
                code=SCENE_URL_MISSING,
                severity=severity,
                message="scene has no download URL",
                scene_id=scene.scene_id,
                field="url",
            )
        )
        if require_urls:
            invalid.add(scene.scene_id)
    if not scene.url and not scene.local_path:
        issues.append(
            CheckIssue(
                code=SCENE_NO_SOURCE,
                severity=CheckSeverity.WARNING,
                message="scene has neither a url nor a local_path",
                scene_id=scene.scene_id,
            )
        )
    return issues


def _check_polarization_mix(scenes: list[Scene]) -> list[CheckIssue]:
    polarizations = {scene.polarization for scene in scenes}
    if Polarization.DH in polarizations and Polarization.DV in polarizations:
        return [
            CheckIssue(
                code=SCENE_POLARIZATION_MIXED,
                severity=CheckSeverity.WARNING,
                message="stack mixes DH and DV polarization; InSAR usually needs one",
                details={"polarizations": sorted(p.value for p in polarizations)},
            )
        ]
    return []


def _check_platform_mix(scenes: list[Scene]) -> list[CheckIssue]:
    platforms = {scene.platform for scene in scenes}
    if len(platforms) > 1:
        return [
            CheckIssue(
                code=SCENE_PLATFORM_MIXED,
                severity=CheckSeverity.WARNING,
                message="stack mixes Sentinel-1 platforms",
                details={"platforms": sorted(p.value for p in platforms)},
            )
        ]
    return []


def _build_summary(scenes: list[Scene]) -> dict[str, object]:
    times = [scene.acquisition_datetime for scene in scenes if scene.acquisition_datetime]
    return {
        "scene_count": len(scenes),
        "with_url": sum(1 for scene in scenes if scene.url),
        "platforms": sorted({scene.platform.value for scene in scenes}),
        "polarizations": sorted({scene.polarization.value for scene in scenes}),
        "product_types": sorted({scene.product_type.value for scene in scenes}),
        "beam_modes": sorted({scene.beam_mode.value for scene in scenes}),
        "start": min(times).isoformat() if times else None,
        "end": max(times).isoformat() if times else None,
    }


def _build_report(
    total: int, valid: int, issues: list[CheckIssue], summary: dict[str, object]
) -> SceneCheckReport:
    return SceneCheckReport(
        total_scenes=total,
        valid_scenes=valid,
        issues=issues,
        has_errors=any(issue.severity is CheckSeverity.ERROR for issue in issues),
        has_warnings=any(issue.severity is CheckSeverity.WARNING for issue in issues),
        summary=summary,
    )


def check_scene_collection(
    scenes: list[Scene],
    processing_aoi: Aoi | None = None,
    *,
    require_urls: bool = False,
    expected_product_type: ProductType | None = ProductType.SLC,
    expected_beam_mode: BeamMode | None = BeamMode.IW,
    expected_polarization: Polarization | None = None,
) -> SceneCheckReport:
    """Run consistency checks over a collection of scenes."""
    if not isinstance(scenes, list):
        raise InputValidationError("scenes must be a list of Scene objects", code=ErrorCode.ASF001)

    total = len(scenes)
    if total == 0:
        empty_issue = CheckIssue(
            code=SCENE_EMPTY,
            severity=CheckSeverity.ERROR,
            message="scene collection is empty",
        )
        return _build_report(0, 0, [empty_issue], {"scene_count": 0})

    logger.debug("checking %d scenes", total)
    issues: list[CheckIssue] = []
    invalid: set[str] = set()
    issues.extend(_check_duplicate_ids(scenes))
    issues.extend(_check_duplicate_times(scenes))
    for scene in scenes:
        issues.extend(
            _check_single_scene(
                scene,
                require_urls=require_urls,
                expected_product_type=expected_product_type,
                expected_beam_mode=expected_beam_mode,
                expected_polarization=expected_polarization,
                invalid=invalid,
            )
        )
    issues.extend(_check_polarization_mix(scenes))
    issues.extend(_check_platform_mix(scenes))
    if processing_aoi is not None:
        issues.append(
            CheckIssue(
                code=SCENE_COVERAGE_NOT_CHECKED,
                severity=CheckSeverity.INFO,
                message="scene footprints unavailable; AOI coverage not checked",
                details={"scene_count": total},
            )
        )

    report = _build_report(total, total - len(invalid), issues, _build_summary(scenes))
    log_event(
        logger,
        EventType.SCENE_VALIDATION_FINISHED,
        f"checked {total} scenes with {len(issues)} issues",
        module="quality",
        payload={"total": total, "issues": len(issues), "has_errors": report.has_errors},
    )
    return report
