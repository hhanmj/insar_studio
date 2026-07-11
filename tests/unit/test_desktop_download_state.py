from pathlib import Path
from types import SimpleNamespace

import pytest

from insar_prep.core.exceptions import InputValidationError
from insar_prep.desktop import api as desktop_api
from insar_prep.providers.asf import metadata
from insar_prep.providers.asf.downloader import download_requests_from_scenes
from insar_prep.providers.orbit import downloader as orbit_downloader


def test_deleted_archive_tombstone_filters_legacy_variants() -> None:
    deleted = desktop_api._clean_download_archive(
        [
            {
                "id": r"asf:C:\InSAR\run_a:3",
                "name": "Sentinel-1 download task",
                "status": "cancelled",
                "detail": "deleted by user",
                "ts": 1,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
            }
        ]
    )[0]
    stale_variant = desktop_api._clean_download_archive(
        [
            {
                "id": r"asf:C:\InSAR\run_a\asf_download_results.txt:3",
                "name": "Sentinel-1 download task",
                "status": "interrupted",
                "detail": "old local cache row",
                "ts": 2,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
            }
        ]
    )

    deleted_keys = desktop_api._download_archive_identity_candidates(
        deleted,
        include_legacy=True,
    )

    assert desktop_api._filter_deleted_download_archive(stale_variant, deleted_keys) == []


def test_archive_dedupe_collapses_repeated_interrupted_records() -> None:
    items = desktop_api._clean_download_archive(
        [
            {
                "id": r"asf:C:\InSAR\run_a:2",
                "name": "Sentinel-1 download task",
                "status": "interrupted",
                "detail": "older interruption",
                "ts": 10,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
            },
            {
                "id": r"asf:C:\InSAR\run_a:2",
                "name": "Sentinel-1 download task",
                "status": "interrupted",
                "detail": "newer interruption",
                "ts": 20,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
            },
        ]
    )

    deduped = desktop_api._dedupe_download_archive(items)

    assert len(deduped) == 1
    assert deduped[0]["detail"] == "newer interruption"


def test_archive_identity_keeps_flat_and_subdir_downloads_separate() -> None:
    flat, subdir = desktop_api._clean_download_archive(
        [
            {
                "id": r"asf:C:\InSAR\run_a:2",
                "name": "Sentinel-1 download task",
                "status": "interrupted",
                "detail": "flat",
                "ts": 10,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
                "use_product_subdirs": False,
            },
            {
                "id": r"asf:C:\InSAR\run_a:2",
                "name": "Sentinel-1 download task",
                "status": "interrupted",
                "detail": "subdir",
                "ts": 20,
                "kind": "asf",
                "output_dir": r"C:\InSAR\run_a",
                "use_product_subdirs": True,
            },
        ]
    )

    assert desktop_api._download_archive_identity(flat) != desktop_api._download_archive_identity(
        subdir
    )


def test_archive_identity_keeps_same_directory_task_ids_separate() -> None:
    first, second = desktop_api._clean_download_archive(
        [
            {
                "id": "asf-task:asf-first",
                "task_id": "asf-first",
                "name": "Sentinel-1 download",
                "status": "paused",
                "detail": "first",
                "kind": "asf",
                "output_dir": r"D:\shared",
            },
            {
                "id": "asf-task:asf-second",
                "task_id": "asf-second",
                "name": "Sentinel-1 download",
                "status": "paused",
                "detail": "second",
                "kind": "asf",
                "output_dir": r"D:\shared",
            },
        ]
    )

    assert desktop_api._download_archive_identity(first) != desktop_api._download_archive_identity(second)
    first_keys = desktop_api._download_archive_identity_candidates(first, include_legacy=True)
    second_keys = desktop_api._download_archive_identity_candidates(second, include_legacy=True)
    assert first_keys.isdisjoint(second_keys)


def _scene(scene_id: str, product: str = "SLC") -> SimpleNamespace:
    return SimpleNamespace(
        scene_id=scene_id,
        url=f"https://example.test/{scene_id}.zip",
        product_type=SimpleNamespace(value=product),
        file_size_remote=123,
    )


def test_asf_download_requests_can_target_selected_directory_directly() -> None:
    requests = download_requests_from_scenes(
        [_scene("S1A_TEST")],
        slc_dir=Path(r"D:\downloads"),
        use_product_subdirs=False,
    )

    assert requests[0].destination == Path(r"D:\downloads") / "S1A_TEST.zip"


def test_asf_download_requests_use_optional_product_subdirectories() -> None:
    requests = download_requests_from_scenes(
        [_scene("S1A_SLC", "SLC"), _scene("S1A_GRD", "GRD")],
        slc_dir=Path(r"D:\downloads"),
        use_product_subdirs=True,
        product_subdir_base=Path(r"D:\downloads"),
    )

    assert requests[0].destination == Path(r"D:\downloads") / "SLC" / "S1A_SLC.zip"
    assert requests[1].destination == Path(r"D:\downloads") / "GRD" / "S1A_GRD.zip"


def test_orbit_download_summary_uses_requested_directory_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download_one(
        scene: SimpleNamespace, orbit_dir: Path
    ) -> orbit_downloader.OrbitDownloadResult:
        return orbit_downloader.OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=orbit_downloader.OrbitDownloadOutcome.SKIPPED,
            orbit_file="orbit.EOF",
            orbit_type="POEORB",
            path=Path(orbit_dir) / "orbit.EOF",
        )

    monkeypatch.setattr(orbit_downloader, "_download_one", fake_download_one)

    flat = orbit_downloader.download_orbits_for_scenes(
        [_scene("S1A_TEST")],
        Path(r"D:\orbits"),
        use_orbit_subdir=False,
    )
    subdir = orbit_downloader.download_orbits_for_scenes(
        [_scene("S1A_TEST")],
        Path(r"D:\orbits"),
        use_orbit_subdir=True,
    )

    assert flat.orbit_dir == Path(r"D:\orbits")
    assert subdir.orbit_dir == Path(r"D:\orbits") / "Sentinel_Orbit" / "AUX_POEORB"


def test_asf_search_accepts_path_and_frame_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_geojson(params: dict[str, str]) -> dict[str, list]:
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_geojson)

    scenes = metadata.search_scenes_from_asf(
        relative_orbit="11-13",
        frame="460-470",
        max_results=5,
    )

    assert scenes == []
    assert captured["relativeOrbit"] == "11-13"
    assert captured["frame"] == "460-470"


def test_asf_search_rejects_invalid_path_range() -> None:
    with pytest.raises(InputValidationError):
        metadata.search_scenes_from_asf(relative_orbit="11..13", max_results=5)
