"""Burst planning contracts and helpers for the ASF provider."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import Field

from insar_prep.core.enums import OrbitDirection, Provider, TaskStatus, TaskType
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.models import BBox, DownloadTask, InsarBaseModel, Scene, generate_id
from insar_prep.providers.capabilities import ProviderCapability, provider_capability


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class BurstSwath(StrEnum):
    """Sentinel-1 TOPS swath identifier."""

    IW1 = "IW1"
    IW2 = "IW2"
    IW3 = "IW3"


class BurstPlanStatus(StrEnum):
    """High-level planning outcome."""

    READY = "READY"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"


class BurstError(InsarBaseModel):
    """Structured error payload."""

    code: ErrorCode
    message: str


class BurstObservability(InsarBaseModel):
    """Observable counters emitted by planning paths."""

    elapsed_ms: float = 0.0
    cache_hits: int = 0
    retry_count: int = 0
    failure_reason_counts: dict[str, int] = Field(default_factory=dict)
    per_scene_elapsed_ms: dict[str, float] = Field(default_factory=dict)


class BurstCatalogEntry(InsarBaseModel):
    """One burst descriptor from external metadata."""

    scene_id: str
    swath: BurstSwath
    burst_index: int = Field(ge=0)
    acquisition_datetime: datetime | None = None
    relative_orbit: int | None = None
    orbit_direction: OrbitDirection | None = None

    @property
    def burst_id(self) -> str:
        return f"{self.scene_id}:{self.swath.value}:{self.burst_index}"


class SearchBurstRequest(InsarBaseModel):
    """Search contract sent to the sidecar."""

    request_id: str = Field(default_factory=lambda: generate_id("req"))
    protocol_version: str = "1.0"
    app_version: str = ""
    aoi_bbox: BBox | None = None
    orbit_direction: OrbitDirection | None = None
    relative_orbit: int | None = None
    swath: BurstSwath | None = None
    burst_indices: list[int] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    cache_hit: bool = False


class BurstSearchItem(InsarBaseModel):
    """Normalized burst record returned to callers."""

    burst_id: str
    scene_id: str
    swath: BurstSwath
    burst_index: int
    acquisition_datetime: datetime | None = None
    relative_orbit: int | None = None
    orbit_direction: OrbitDirection | None = None


class SearchBurstResponse(InsarBaseModel):
    """Response contract for burst search requests."""

    request_id: str
    protocol_version: str = "1.0"
    success: bool
    status: BurstPlanStatus
    errors: list[BurstError] = Field(default_factory=list)
    capabilities: ProviderCapability
    bursts: list[BurstSearchItem] = Field(default_factory=list)
    grouped_by_date: dict[str, list[str]] = Field(default_factory=dict)
    fallback_scene_ids: list[str] = Field(default_factory=list)
    observability: BurstObservability = Field(default_factory=BurstObservability)


class DownloadBurstRequest(InsarBaseModel):
    """Download-planning contract for selected bursts."""

    request_id: str = Field(default_factory=lambda: generate_id("req"))
    protocol_version: str = "1.0"
    app_version: str = ""
    output_dir: Path
    max_retries: int = Field(default=3, ge=0)
    rate_limit_per_sec: float = Field(default=2.0, gt=0.0)
    resume_partial: bool = True
    search_response: SearchBurstResponse


class BurstDownloadItem(InsarBaseModel):
    """One planned burst (or scene fallback) download item."""

    task: DownloadTask
    destination: Path
    retry_limit: int = Field(ge=0)
    rate_limit_per_sec: float = Field(gt=0.0)
    resume_partial: bool = True


class DownloadBurstResponse(InsarBaseModel):
    """Response contract for burst download planning."""

    request_id: str
    protocol_version: str = "1.0"
    success: bool
    status: BurstPlanStatus
    errors: list[BurstError] = Field(default_factory=list)
    used_scene_fallback: bool = False
    items: list[BurstDownloadItem] = Field(default_factory=list)
    observability: BurstObservability = Field(default_factory=BurstObservability)


class ShadowFieldDiff(InsarBaseModel):
    """One differing field between Python and Rust sidecar outputs."""

    path: str
    python_value: str
    rust_value: str


class ShadowComparison(InsarBaseModel):
    """Result of one Python-vs-Rust shadow comparison."""

    request_id: str
    matches: bool
    diffs: list[ShadowFieldDiff] = Field(default_factory=list)
    compared_at: datetime = Field(default_factory=_utcnow)


class ShadowCutoverDecision(InsarBaseModel):
    """Decision gate for enabling Rust output in production."""

    allow_cutover: bool
    sample_count: int
    match_rate: float
    consecutive_matches: int
    reason: str


def _scene_match(scene: Scene, request: SearchBurstRequest) -> bool:
    if request.orbit_direction and scene.orbit_direction is not request.orbit_direction:
        return False
    if request.relative_orbit and scene.relative_orbit != request.relative_orbit:
        return False
    acquisition = scene.acquisition_datetime
    if request.start_date and acquisition and acquisition.date() < request.start_date:
        return False
    if request.end_date and acquisition and acquisition.date() > request.end_date:
        return False
    return True


def _entries_from_scenes(
    scenes: Iterable[Scene],
    request: SearchBurstRequest,
    burst_catalog: Iterable[BurstCatalogEntry] | None,
) -> tuple[list[BurstSearchItem], list[str]]:
    fallback_scenes: list[str] = []
    if burst_catalog is not None:
        items = [
            BurstSearchItem(
                burst_id=entry.burst_id,
                scene_id=entry.scene_id,
                swath=entry.swath,
                burst_index=entry.burst_index,
                acquisition_datetime=entry.acquisition_datetime,
                relative_orbit=entry.relative_orbit,
                orbit_direction=entry.orbit_direction,
            )
            for entry in burst_catalog
        ]
    else:
        items = []
        for scene in scenes:
            if not _scene_match(scene, request):
                continue
            fallback_scenes.append(scene.scene_id)
    return items, fallback_scenes


def _filter_bursts(
    items: list[BurstSearchItem],
    request: SearchBurstRequest,
) -> list[BurstSearchItem]:
    filtered = items
    if request.orbit_direction is not None:
        filtered = [item for item in filtered if item.orbit_direction == request.orbit_direction]
    if request.relative_orbit is not None:
        filtered = [item for item in filtered if item.relative_orbit == request.relative_orbit]
    if request.swath is not None:
        filtered = [item for item in filtered if item.swath == request.swath]
    if request.burst_indices:
        wanted = set(request.burst_indices)
        filtered = [item for item in filtered if item.burst_index in wanted]
    if request.start_date is not None:
        filtered = [
            item
            for item in filtered
            if (
                item.acquisition_datetime is None
                or item.acquisition_datetime.date() >= request.start_date
            )
        ]
    if request.end_date is not None:
        filtered = [
            item
            for item in filtered
            if (
                item.acquisition_datetime is None
                or item.acquisition_datetime.date() <= request.end_date
            )
        ]
    unique: dict[str, BurstSearchItem] = {}
    for item in filtered:
        unique[item.burst_id] = item
    return sorted(unique.values(), key=lambda item: item.burst_id)


def _group_by_date(items: Iterable[BurstSearchItem]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        key = "unknown"
        if item.acquisition_datetime is not None:
            key = item.acquisition_datetime.date().isoformat()
        grouped.setdefault(key, []).append(item.burst_id)
    for values in grouped.values():
        values.sort()
    return grouped


def plan_burst_search(
    request: SearchBurstRequest,
    scenes: Iterable[Scene],
    *,
    burst_catalog: Iterable[BurstCatalogEntry] | None = None,
    provider: str = Provider.ASF.value,
) -> SearchBurstResponse:
    """Plan burst search with direct+fallback behavior and observability data."""
    start = perf_counter()
    capability = provider_capability(provider)
    items, fallback_scene_ids = _entries_from_scenes(scenes, request, burst_catalog)
    errors: list[BurstError] = []

    filtered = _filter_bursts(items, request) if capability.supports_burst_direct else []
    status = BurstPlanStatus.READY
    success = True

    if not filtered:
        if capability.supports_scene_fallback and fallback_scene_ids:
            status = BurstPlanStatus.FALLBACK
        else:
            status = BurstPlanStatus.FAILED
            success = False
            errors.append(
                BurstError(
                    code=ErrorCode.ASF002,
                    message="no matching burst metadata and no fallback scene available",
                )
            )

    elapsed_ms = round((perf_counter() - start) * 1000.0, 3)
    observability = BurstObservability(
        elapsed_ms=elapsed_ms,
        cache_hits=1 if request.cache_hit else 0,
        failure_reason_counts={"no_match": 1} if not filtered and not fallback_scene_ids else {},
        per_scene_elapsed_ms={scene_id: 0.0 for scene_id in fallback_scene_ids},
    )
    return SearchBurstResponse(
        request_id=request.request_id,
        protocol_version=request.protocol_version,
        success=success,
        status=status,
        errors=errors,
        capabilities=capability,
        bursts=filtered,
        grouped_by_date=_group_by_date(filtered),
        fallback_scene_ids=sorted(set(fallback_scene_ids)),
        observability=observability,
    )


def _burst_destination(output_dir: Path, item: BurstSearchItem) -> Path:
    return output_dir / "SAR_Data" / "Bursts" / f"{item.burst_id.replace(':', '_')}.zip"


def _scene_destination(output_dir: Path, scene_id: str) -> Path:
    return output_dir / "SAR_Data" / "SLC" / f"{scene_id}.zip"


def plan_burst_download(request: DownloadBurstRequest) -> DownloadBurstResponse:
    """Create planned burst download tasks with direct and fallback paths."""
    start = perf_counter()
    items: list[BurstDownloadItem] = []
    errors: list[BurstError] = []
    used_scene_fallback = False

    if request.search_response.bursts:
        for burst in request.search_response.bursts:
            task = DownloadTask(
                job_id="",
                region_id="",
                provider=Provider.ASF,
                task_type=TaskType.DOWNLOAD_BURST,
                status=TaskStatus.PENDING,
                local_path=_burst_destination(request.output_dir, burst),
                input={
                    "scene_id": burst.scene_id,
                    "swath": burst.swath.value,
                    "burst_index": burst.burst_index,
                    "request_id": request.request_id,
                },
            )
            items.append(
                BurstDownloadItem(
                    task=task,
                    destination=task.local_path or Path(),
                    retry_limit=request.max_retries,
                    rate_limit_per_sec=request.rate_limit_per_sec,
                    resume_partial=request.resume_partial,
                )
            )
        status = BurstPlanStatus.READY
        success = True
    elif request.search_response.fallback_scene_ids:
        used_scene_fallback = True
        for scene_id in sorted(set(request.search_response.fallback_scene_ids)):
            task = DownloadTask(
                job_id="",
                region_id="",
                provider=Provider.ASF,
                task_type=TaskType.DOWNLOAD_SLC,
                status=TaskStatus.PENDING,
                local_path=_scene_destination(request.output_dir, scene_id),
                input={"scene_id": scene_id, "request_id": request.request_id},
            )
            items.append(
                BurstDownloadItem(
                    task=task,
                    destination=task.local_path or Path(),
                    retry_limit=request.max_retries,
                    rate_limit_per_sec=request.rate_limit_per_sec,
                    resume_partial=request.resume_partial,
                )
            )
        status = BurstPlanStatus.FALLBACK
        success = True
    else:
        status = BurstPlanStatus.FAILED
        success = False
        errors.append(
            BurstError(
                code=ErrorCode.ASF003,
                message="no burst or fallback scene to download",
            )
        )

    elapsed_ms = round((perf_counter() - start) * 1000.0, 3)
    observability = BurstObservability(
        elapsed_ms=elapsed_ms,
        cache_hits=request.search_response.observability.cache_hits,
        retry_count=sum(item.retry_limit for item in items),
        failure_reason_counts={"empty_plan": 1} if not items else {},
    )
    return DownloadBurstResponse(
        request_id=request.request_id,
        protocol_version=request.protocol_version,
        success=success,
        status=status,
        errors=errors,
        used_scene_fallback=used_scene_fallback,
        items=items,
        observability=observability,
    )


def _flatten_payload(payload: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(payload, dict):
        flattened: dict[str, str] = {}
        for key in sorted(payload):
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_payload(payload[key], child))
        return flattened
    if isinstance(payload, list):
        flattened = {}
        for idx, value in enumerate(payload):
            child = f"{prefix}[{idx}]"
            flattened.update(_flatten_payload(value, child))
        return flattened
    return {prefix or "$": repr(payload)}


def compare_shadow_outputs(
    request_id: str,
    python_output: dict[str, Any],
    rust_output: dict[str, Any],
) -> ShadowComparison:
    """Compare Python and Rust outputs field-by-field for shadow mode."""
    flat_python = _flatten_payload(python_output)
    flat_rust = _flatten_payload(rust_output)
    keys = sorted(set(flat_python) | set(flat_rust))
    diffs = [
        ShadowFieldDiff(
            path=key,
            python_value=flat_python.get(key, "<missing>"),
            rust_value=flat_rust.get(key, "<missing>"),
        )
        for key in keys
        if flat_python.get(key) != flat_rust.get(key)
    ]
    return ShadowComparison(request_id=request_id, matches=not diffs, diffs=diffs)


def evaluate_shadow_cutover(
    history: list[ShadowComparison],
    *,
    min_samples: int = 20,
    min_consecutive_matches: int = 10,
    max_failure_rate: float = 0.02,
) -> ShadowCutoverDecision:
    """Evaluate whether Rust can become the default provider output."""
    if len(history) < min_samples:
        return ShadowCutoverDecision(
            allow_cutover=False,
            sample_count=len(history),
            match_rate=0.0,
            consecutive_matches=0,
            reason="insufficient sample count",
        )

    ordered = sorted(history, key=lambda item: item.compared_at)
    matches = sum(1 for item in ordered if item.matches)
    match_rate = matches / len(ordered)
    consecutive = 0
    for item in reversed(ordered):
        if item.matches:
            consecutive += 1
        else:
            break

    failure_rate = 1.0 - match_rate
    allow = failure_rate <= max_failure_rate and consecutive >= min_consecutive_matches
    reason = "ready for cutover" if allow else "shadow mismatch rate too high"
    return ShadowCutoverDecision(
        allow_cutover=allow,
        sample_count=len(ordered),
        match_rate=round(match_rate, 4),
        consecutive_matches=consecutive,
        reason=reason,
    )


def sidecar_handshake(
    request: SearchBurstRequest | DownloadBurstRequest,
    *,
    app_version: str,
    protocol_version: Literal["1.0"] = "1.0",
) -> dict[str, str]:
    """Build a minimal versioned sidecar handshake payload."""
    return {
        "request_id": request.request_id,
        "protocol_version": protocol_version,
        "app_version": app_version,
    }
