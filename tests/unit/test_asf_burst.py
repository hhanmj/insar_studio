from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from insar_prep.core.enums import TaskType
from insar_prep.providers.asf.burst import (
    BurstCatalogEntry,
    BurstPlanStatus,
    BurstSwath,
    DownloadBurstRequest,
    SearchBurstRequest,
    compare_shadow_outputs,
    evaluate_shadow_cutover,
    plan_burst_download,
    plan_burst_search,
    sidecar_handshake,
)
from insar_prep.providers.asf.metadata import parse_scene_name


def _scene(scene_id: str):
    return parse_scene_name(scene_id)


def test_plan_burst_search_filters_and_groups() -> None:
    scenes = [
        _scene("S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052001_064ABC_0001"),
        _scene("S1A_IW_SLC__1SDV_20240113T100000_20240113T100027_052002_064ABC_0002"),
    ]
    request = SearchBurstRequest(swath=BurstSwath.IW2)
    catalog = [
        BurstCatalogEntry(
            scene_id=scenes[0].scene_id,
            swath=BurstSwath.IW2,
            burst_index=12,
            acquisition_datetime=scenes[0].acquisition_datetime,
            relative_orbit=scenes[0].relative_orbit,
            orbit_direction=scenes[0].orbit_direction,
        ),
        BurstCatalogEntry(
            scene_id=scenes[1].scene_id,
            swath=BurstSwath.IW1,
            burst_index=12,
            acquisition_datetime=scenes[1].acquisition_datetime,
            relative_orbit=scenes[1].relative_orbit,
            orbit_direction=scenes[1].orbit_direction,
        ),
    ]
    response = plan_burst_search(request, scenes, burst_catalog=catalog)

    assert response.success is True
    assert response.status is BurstPlanStatus.READY
    assert len(response.bursts) == 1
    assert response.bursts[0].swath is BurstSwath.IW2
    assert "2024-01-01" in response.grouped_by_date


def test_plan_burst_search_uses_scene_fallback_without_catalog() -> None:
    scenes = [_scene("S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052001_064ABC_0001")]
    request = SearchBurstRequest()
    response = plan_burst_search(request, scenes, burst_catalog=None)

    assert response.success is True
    assert response.status is BurstPlanStatus.FALLBACK
    assert response.fallback_scene_ids == [scenes[0].scene_id]


def test_plan_burst_download_builds_burst_tasks() -> None:
    scenes = [_scene("S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052001_064ABC_0001")]
    request = SearchBurstRequest()
    catalog = [
        BurstCatalogEntry(
            scene_id=scenes[0].scene_id,
            swath=BurstSwath.IW3,
            burst_index=7,
            acquisition_datetime=scenes[0].acquisition_datetime,
            relative_orbit=scenes[0].relative_orbit,
            orbit_direction=scenes[0].orbit_direction,
        )
    ]
    search = plan_burst_search(request, scenes, burst_catalog=catalog)
    download = plan_burst_download(
        DownloadBurstRequest(output_dir=Path("/tmp/out"), search_response=search)
    )

    assert download.success is True
    assert download.status is BurstPlanStatus.READY
    assert download.items[0].task.task_type is TaskType.DOWNLOAD_BURST


def test_plan_burst_download_uses_scene_fallback_tasks() -> None:
    scenes = [_scene("S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052001_064ABC_0001")]
    search = plan_burst_search(SearchBurstRequest(), scenes, burst_catalog=None)
    download = plan_burst_download(
        DownloadBurstRequest(output_dir=Path("/tmp/out"), search_response=search)
    )

    assert download.success is True
    assert download.used_scene_fallback is True
    assert download.items[0].task.task_type is TaskType.DOWNLOAD_SLC


def test_shadow_comparison_and_cutover_gate() -> None:
    history = []
    now = datetime.now(tz=UTC)
    for idx in range(20):
        comparison = compare_shadow_outputs(
            request_id=f"req-{idx}",
            python_output={"a": idx, "b": {"ok": True}},
            rust_output={"a": idx, "b": {"ok": True}},
        )
        comparison.compared_at = now + timedelta(seconds=idx)
        history.append(comparison)
    decision = evaluate_shadow_cutover(history)

    assert decision.allow_cutover is True
    assert decision.sample_count == 20
    assert decision.consecutive_matches == 20


def test_sidecar_handshake_returns_versioned_payload() -> None:
    request = SearchBurstRequest()
    payload = sidecar_handshake(request, app_version="3.0.0")
    assert payload["request_id"] == request.request_id
    assert payload["protocol_version"] == "1.0"
    assert payload["app_version"] == "3.0.0"
