from __future__ import annotations

from collections.abc import Callable
from typing import Any

from insar_prep.desktop import api as desktop_api
from insar_prep.desktop.download_archive_service import DownloadArchiveService


def _service(
    items: list[dict[str, Any]] | None = None,
    deleted: set[str] | None = None,
) -> tuple[
    DownloadArchiveService,
    Callable[[], list[dict[str, Any]]],
    Callable[[], set[str]],
    list[bool],
]:
    archive = list(items or [])
    deleted_keys = set(deleted or set())
    saved: list[bool] = []

    def set_items(next_items: list[dict[str, Any]]) -> None:
        nonlocal archive
        archive = next_items

    def set_deleted(next_deleted: set[str]) -> None:
        nonlocal deleted_keys
        deleted_keys = next_deleted

    service = DownloadArchiveService(
        get_items=lambda: archive,
        set_items=set_items,
        get_deleted_keys=lambda: deleted_keys,
        set_deleted_keys=set_deleted,
        save_state=lambda: saved.append(True),
        helpers={
            "clean_download_archive": desktop_api._clean_download_archive,
            "filter_deleted_download_archive": desktop_api._filter_deleted_download_archive,
            "dedupe_download_archive": desktop_api._dedupe_download_archive,
            "merge_download_archive": desktop_api._merge_download_archive,
            "download_archive_identity": desktop_api._download_archive_identity,
            "download_archive_identity_candidates": (
                desktop_api._download_archive_identity_candidates
            ),
            "normalise_download_archive_path": desktop_api._normalise_download_archive_path,
            "clean_archive_scene_rows": desktop_api._clean_archive_scene_rows,
            "format_status_log_entry": desktop_api._format_status_log_entry,
            "coerce_bool": desktop_api._coerce_bool,
        },
    )
    return service, lambda: archive, lambda: deleted_keys, saved


def test_archive_asf_status_preserves_snapshot_scene_metadata() -> None:
    service, get_archive, _get_deleted, saved = _service()

    service.archive_asf_status(
        {
            "state": "finished",
            "output_dir": r"C:\InSAR\run_a",
            "total": 1,
            "concurrency": 1,
            "snapshot_scenes": [
                {
                    "scene_id": "S1A_TEST",
                    "path": 11,
                    "frame": 460,
                    "download_url": "https://example.test/S1A_TEST.zip",
                    "ignored": "not persisted",
                }
            ],
            "log": [{"detail": "download complete"}],
        }
    )

    item = get_archive()[0]
    assert saved == [True]
    assert item["kind"] == "asf"
    assert "Sentinel-1" in item["name"]
    assert item["scene_ids"] == ["S1A_TEST"]
    assert item["snapshot"] == [
        {
            "scene_id": "S1A_TEST",
            "path": 11,
            "frame": 460,
            "download_url": "https://example.test/S1A_TEST.zip",
        }
    ]


def test_archive_asf_status_preserves_aoi_name_and_elapsed_seconds() -> None:
    service, get_archive, _get_deleted, _saved = _service()

    service.archive_asf_status(
        {
            "state": "finished",
            "output_dir": r"C:\InSAR\run_a",
            "total": 1,
            "concurrency": 1,
            "summary_line": "done",
            "aoi_name": "全国",
            "elapsed_seconds": 3723.5,
        }
    )

    item = get_archive()[0]
    assert item["aoi_name"] == "全国"
    assert item["elapsed_seconds"] == 3723.5


def test_save_archive_empty_input_does_not_clear_backend_rows() -> None:
    service, get_archive, _get_deleted, saved = _service(
        [
            {
                "id": r"asf:C:\InSAR\run_a:1",
                "name": "Sentinel-1 download task",
                "status": "finished",
                "detail": "done",
                "ts": 10,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
            }
        ]
    )

    result = service.save_archive([])

    assert result["ok"] is True
    assert result["items"][0]["output_dir"] == r"C:\InSAR\run_a"
    assert get_archive()[0]["status"] == "finished"
    assert saved == []


def test_delete_archive_item_tombstones_identity_and_removes_stale_rows() -> None:
    item = {
        "id": r"asf:C:\InSAR\run_a:2",
        "name": "Sentinel-1 download task",
        "status": "interrupted",
        "detail": "old run",
        "ts": 20,
        "kind": "asf",
        "output_dir": r"C:\InSAR\run_a",
    }
    service, get_archive, get_deleted, saved = _service([item])

    result = service.delete_archive_item(item)

    assert result == {"ok": True, "items": []}
    assert get_archive() == []
    assert saved == [True]
    assert any(key.startswith(r"asf:c:\insar\run_a") for key in get_deleted())


def test_forget_deleted_key_allows_restarted_task_to_reuse_archive_slot() -> None:
    service, _get_archive, get_deleted, _saved = _service(
        deleted={
            r"asf:c:\insar\run_a",
            r"asf:c:\insar\run_a:flat",
            r"asf:c:\insar\run_a\asf_download_results.txt:flat",
            r"orbit:c:\insar\run_a",
        }
    )

    service.forget_deleted_key("asf", r"C:\InSAR\run_a", use_product_subdirs=False)

    assert get_deleted() == {r"orbit:c:\insar\run_a"}
