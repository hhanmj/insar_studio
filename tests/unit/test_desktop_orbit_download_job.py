from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from insar_prep.core.models import Scene
from insar_prep.desktop.api import Api
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
    monkeypatch.setattr(
        "insar_prep.providers.orbit.scan_orbit_directory", lambda *_args, **_kwargs: []
    )
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

    assert started["ok"] is True
    assert started["task_id"]
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
    monkeypatch.setattr(
        "insar_prep.providers.orbit.scan_orbit_directory", lambda *_args, **_kwargs: []
    )
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
    started = job.start(
        [Scene(scene_id=f"S1A_{idx}") for idx in range(4)], tmp_path, max_concurrent=4
    )
    assert started["ok"] is True
    assert started["task_id"]

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


def test_orbit_download_job_keeps_full_log_and_reports_unmatched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes = [Scene(scene_id=f"S1A_{idx:03d}") for idx in range(130)]

    def fake_download(scene: Scene, orbit_dir: Path) -> OrbitDownloadResult:
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.SUCCESS,
            orbit_file=f"{scene.scene_id}.EOF",
            orbit_type="POEORB",
            path=orbit_dir / f"{scene.scene_id}.EOF",
            bytes_written=512,
            message="ok",
        )

    monkeypatch.setattr("insar_prep.providers.orbit.download_orbit_for_scene", fake_download)
    monkeypatch.setattr(
        "insar_prep.providers.orbit.scan_orbit_directory", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        "insar_prep.providers.orbit.match_orbits_for_scenes",
        lambda scenes, _files: type(
            "Report",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "matched_scenes": 128,
                    "total_scenes": len(list(scenes)),
                    "results": [
                        {
                            "scene_id": "S1A_128",
                            "is_matched": False,
                            "issues": [
                                {"message": "no orbit validity period covers the scene time"}
                            ],
                        },
                        {
                            "scene_id": "S1A_129",
                            "is_matched": False,
                            "issues": [{"message": "no orbit files"}],
                        },
                    ],
                }
            },
        )(),
    )

    job = OrbitDownloadJob()
    started = job.start(scenes, tmp_path, max_concurrent=10)

    assert started["ok"] is True
    assert started["task_id"]
    status = _wait_for_idle(job)
    assert status["state"] == "finished"
    assert status["done"] == 130
    assert len(status["results"]) == 130
    assert len(status["log"]) >= 131
    assert "匹配 128/130 景" in status["summary_line"]
    assert "缺失 2 景" in status["summary_line"]
    assert "S1A_128" in status["summary_line"]
    assert "S1A_129" in status["summary_line"]


def test_api_orbit_download_snapshot_uses_frozen_scenes_not_current_candidates(
    tmp_path: Path,
) -> None:
    api = Api()
    captured: dict[str, object] = {}

    class FakeOrbitDownload:
        def start(
            self,
            scenes,
            output_dir,
            *,
            max_concurrent=10,
            use_orbit_subdir=False,
            aoi_name="",
            activity=None,
        ):
            captured["scene_ids"] = [scene.scene_id for scene in scenes]
            captured["output_dir"] = str(output_dir)
            captured["max_concurrent"] = max_concurrent
            captured["use_orbit_subdir"] = use_orbit_subdir
            captured["aoi_name"] = aoi_name
            return {"ok": True}

        def get_status(self):
            return {
                "ok": True,
                "state": "running",
                "total": len(captured.get("scene_ids", [])),
                "done": 0,
                "concurrency": captured.get("max_concurrent", 10),
                "current_scene": "",
                "orbit_dir": str(tmp_path / "out"),
                "use_orbit_subdir": captured.get("use_orbit_subdir", False),
                "download_layout": "orbit_subdir"
                if captured.get("use_orbit_subdir", False)
                else "flat",
                "cancelled": False,
                "error": None,
                "summary_line": "",
                "log": [],
            }

    api._orbit_download = FakeOrbitDownload()
    api._orbit_candidate_scenes = [Scene(scene_id="S1A_SECOND_BATCH")]

    result = api.start_orbit_download_snapshot(
        str(tmp_path / "out"),
        [
            {"scene_id": "S1A_FIRST_KEEP", "platform": "S1A", "product_type": "SLC"},
            {"scene_id": "S1A_FIRST_DROP", "platform": "S1A", "product_type": "SLC"},
        ],
        ["S1A_FIRST_KEEP"],
        6,
        True,
    )

    assert result["ok"] is True
    assert captured["scene_ids"] == ["S1A_FIRST_KEEP"]
    assert captured["output_dir"] == str(tmp_path / "out")
    assert captured["max_concurrent"] == 6
    assert captured["use_orbit_subdir"] is True
    assert captured["aoi_name"] == "轨道任务快照（选中 1 景）"
