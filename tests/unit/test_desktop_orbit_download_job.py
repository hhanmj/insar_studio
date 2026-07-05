from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from insar_prep.core.models import Scene
from insar_prep.desktop.download_job import OrbitDownloadJob
from insar_prep.providers.orbit.downloader import OrbitDownloadOutcome, OrbitDownloadResult


def _wait_for_idle(job: OrbitDownloadJob) -> dict:
    deadline = time.monotonic() + 3
    status = job.get_status()
    while status["state"] in {"running", "paused"} and time.monotonic() < deadline:
        time.sleep(0.01)
        status = job.get_status()
    return status


def test_orbit_download_job_uses_default_ten_workers_and_reports_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_download(scene: Scene, orbit_dir: Path) -> OrbitDownloadResult:
        calls.append(scene.scene_id)
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.SUCCESS,
            orbit_file=f"{scene.scene_id}.EOF",
            orbit_type="POEORB",
            path=orbit_dir / f"{scene.scene_id}.EOF",
            bytes_written=1024,
            message="ok",
        )

    monkeypatch.setattr("insar_prep.providers.orbit.download_orbit_for_scene", fake_download)
    monkeypatch.setattr("insar_prep.providers.orbit.scan_orbit_directory", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "insar_prep.providers.orbit.match_orbits_for_scenes",
        lambda scenes, _files: type(
            "Report",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "matched_scenes": len(list(scenes)),
                    "total_scenes": len(list(scenes)),
                }
            },
        )(),
    )

    job = OrbitDownloadJob()
    started = job.start([Scene(scene_id=f"S1A_{idx}") for idx in range(12)], tmp_path)

    assert started == {"ok": True}
    status = _wait_for_idle(job)
    assert status["state"] == "finished"
    assert status["concurrency"] == 10
    assert status["bytes_per_second"] > 0
    assert status["done_bytes"] == 12 * 1024
    assert set(calls) == {f"S1A_{idx}" for idx in range(12)}


def test_orbit_download_job_updates_live_counts_and_active_scenes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()

    def fake_download(scene: Scene, orbit_dir: Path) -> OrbitDownloadResult:
        suffix = scene.scene_id.rsplit("_", 1)[-1]
        if suffix != "0":
            release.wait(timeout=2)
        if suffix == "1":
            outcome = OrbitDownloadOutcome.SKIPPED
            bytes_written = 0
        elif suffix == "2":
            outcome = OrbitDownloadOutcome.UNAVAILABLE
            bytes_written = 0
        elif suffix == "3":
            outcome = OrbitDownloadOutcome.FAILED
            bytes_written = 0
        else:
            outcome = OrbitDownloadOutcome.SUCCESS
            bytes_written = 2048
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=outcome,
            orbit_file=f"{scene.scene_id}.EOF",
            orbit_type="POEORB",
            path=orbit_dir / f"{scene.scene_id}.EOF",
            bytes_written=bytes_written,
            message=outcome.value,
        )

    monkeypatch.setattr("insar_prep.providers.orbit.download_orbit_for_scene", fake_download)
    monkeypatch.setattr("insar_prep.providers.orbit.scan_orbit_directory", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "insar_prep.providers.orbit.match_orbits_for_scenes",
        lambda scenes, _files: type(
            "Report",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "matched_scenes": 0,
                    "total_scenes": len(list(scenes)),
                }
            },
        )(),
    )

    job = OrbitDownloadJob()
    started = job.start([Scene(scene_id=f"S1A_{idx}") for idx in range(4)], tmp_path, max_concurrent=4)
    assert started == {"ok": True}

    deadline = time.monotonic() + 3
    status = job.get_status()
    while (
        status["state"] == "running"
        and (status["done"] < 1 or len(status["active_scenes"]) < 1)
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        status = job.get_status()

    try:
        assert status["state"] == "running"
        assert status["concurrency"] == 4
        assert status["succeeded"] == 1
        assert status["done"] == 1
        assert len(status["active_scenes"]) >= 1
    finally:
        release.set()

    final = _wait_for_idle(job)
    assert final["state"] == "finished"
    assert final["succeeded"] == 1
    assert final["skipped"] == 1
    assert final["unavailable"] == 1
    assert final["failed"] == 1
    assert final["has_failures"] is True
    assert final["active_scenes"] == []
