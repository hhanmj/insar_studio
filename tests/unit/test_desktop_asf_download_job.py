from __future__ import annotations

import time
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import pytest

from insar_prep.core.models import Scene
from insar_prep.desktop import download_job
from insar_prep.desktop.api import Api
from insar_prep.desktop.download_job import AsfDownloadJob, AsfDownloadManager
from insar_prep.providers.asf.downloader import DownloadOutcome, DownloadResult


def _wait_for_idle(job: AsfDownloadJob) -> dict:
    deadline = time.monotonic() + 3
    status = job.get_status()
    while status["state"] in {"running", "paused"} and time.monotonic() < deadline:
        time.sleep(0.01)
        status = job.get_status()
    return status


def test_asf_download_job_can_retry_only_failed_scenes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    init_kwargs: list[dict[str, object]] = []
    outcomes = {
        "S1A_ok": [DownloadOutcome.SUCCESS],
        "S1A_bad": [DownloadOutcome.FAILED, DownloadOutcome.FAILED, DownloadOutcome.SUCCESS],
    }

    class FakeDownloader:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.append(kwargs)

        def download(self, request: object) -> DownloadResult:
            scene_id = str(request.scene_id)
            calls.append(scene_id)
            outcome = outcomes[scene_id].pop(0)
            return DownloadResult(
                scene_id=scene_id,
                outcome=outcome,
                path=getattr(request, "destination", None)
                if outcome is DownloadOutcome.SUCCESS
                else None,
                bytes_written=5 if outcome is DownloadOutcome.SUCCESS else 0,
                message="ok" if outcome is DownloadOutcome.SUCCESS else "network failed",
                error_code=None if outcome is DownloadOutcome.SUCCESS else "DL005",
            )

    monkeypatch.setattr(download_job, "resolve_credentials", lambda source: object())
    monkeypatch.setattr(download_job, "RealAsfDownloader", FakeDownloader)

    job = AsfDownloadJob()
    started = job.start(
        [
            Scene(
                scene_id="S1A_ok",
                url="https://datapool.asf.alaska.edu/SLC/ok.zip",
                path=12,
                frame=34,
            ),
            Scene(scene_id="S1A_bad", url="https://datapool.asf.alaska.edu/SLC/bad.zip"),
        ],
        tmp_path,
        proxy_url="http://127.0.0.1:7897",
        ssl_verify=False,
        trust_env=True,
    )
    assert started == {"ok": True}

    status = _wait_for_idle(job)
    assert status["state"] == "finished"
    assert status["failed"] == 1
    assert status["retry_supported"] is True
    assert "network failed" in "\n".join(item["detail"] for item in status["log"])
    assert status["has_failures"] is True
    assert status["snapshot_scenes"][0]["scene_id"] == "S1A_ok"
    assert status["snapshot_scenes"][0]["path"] == 12
    assert status["snapshot_scenes"][0]["frame"] == 34
    assert init_kwargs[0]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[0]["ssl_verify"] is False
    assert init_kwargs[0]["trust_env"] is True

    retried = job.retry_failed()
    assert retried == {"ok": True}

    status = _wait_for_idle(job)
    assert status["state"] == "finished"
    assert status["failed"] == 0
    assert calls == ["S1A_ok", "S1A_bad", "S1A_bad", "S1A_bad"]
    assert init_kwargs[-1]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[-1]["ssl_verify"] is False
    assert init_kwargs[-1]["trust_env"] is True


def test_asf_download_job_reports_pause_request_immediately_without_pausing_queue() -> None:
    job = AsfDownloadJob()
    with job._lock:
        job._status.state = "running"
        job._known_scene_ids = {"S1A_active", "S1A_waiting"}
        job._status.active_downloads = {
            "S1A_active": {
                "scene_id": "S1A_active",
                "bytes": 10,
                "expected_size": 100,
            }
        }

    result = job.pause_scenes(["S1A_waiting", "S1A_active"])
    status = job.get_status()

    assert result["ok"] is True
    assert result["paused"] == 1
    assert result["not_found"] == ["S1A_waiting"]
    assert status["paused_scene_ids"] == ["S1A_active"]
    assert status["active_scene_ids"] == []
    assert status["queued_scene_ids"] == ["S1A_waiting"]


def test_scene_resumed_during_cancel_transition_is_requeued() -> None:
    job = AsfDownloadJob()
    request = SimpleNamespace(scene_id="S1A_transition")
    result = DownloadResult(
        scene_id="S1A_transition",
        outcome=DownloadOutcome.INTERRUPTED,
        path=None,
        bytes_written=10,
        message="paused",
    )
    with job._lock:
        job._status.state = "running"
        job._pending = Queue()
        job._known_scene_ids = {"S1A_transition"}
        job._paused_scene_ids = set()

    job._mark_scene_paused(request, result)

    assert job._pending.qsize() == 1
    assert job.get_status()["paused_scene_ids"] == []


def test_pause_status_counts_are_mutually_exclusive() -> None:
    job = AsfDownloadJob()
    with job._lock:
        job._status.state = "running"
        job._known_scene_ids = {"S1A_one", "S1A_two", "S1A_waiting"}
        job._status.active_downloads = {
            "S1A_one": {"scene_id": "S1A_one", "bytes": 10, "expected_size": 100},
            "S1A_two": {"scene_id": "S1A_two", "bytes": 20, "expected_size": 100},
        }

    paused = job.pause_scenes(["S1A_one", "S1A_two"])
    status = job.get_status()

    assert paused["paused"] == 2
    assert status["active_scene_ids"] == []
    assert status["paused_scene_ids"] == ["S1A_one", "S1A_two"]
    assert status["queued_scene_ids"] == ["S1A_waiting"]


def test_resume_scene_does_not_increase_configured_concurrency() -> None:
    job = AsfDownloadJob()
    request = SimpleNamespace(scene_id="S1A_paused")
    with job._lock:
        job._status.state = "paused"
        job._status.paused = True
        job._status.concurrency = 2
        job._pending = Queue()
        job._paused_scene_ids = {"S1A_paused"}
        job._paused_requests = {"S1A_paused": request}
        job._worker_threads = []

    started: list[int] = []
    job._start_workers = lambda count: started.append(count)  # type: ignore[method-assign]

    result = job.resume_scenes(["S1A_paused"])

    assert result == {"ok": True, "resumed": 1}
    assert started == [2]
    assert job.get_status()["concurrency"] == 2


def test_resume_scene_rejects_whole_task_pause() -> None:
    job = AsfDownloadJob()
    with job._lock:
        job._status.state = "paused"
        job._status.paused = True
        job._pending = Queue()
        job._paused_scene_ids = {"S1A_paused"}
    job._pause.set()

    result = job.resume_scenes(["S1A_paused"])

    assert result["ok"] is False
    assert result["code"] == "GUI004"
    assert "整个任务" in result["error"]


def test_asf_download_manager_allows_second_task_while_first_paused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowDownloader:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def download(self, request: object) -> DownloadResult:
            time.sleep(0.2)
            return DownloadResult(
                scene_id=str(request.scene_id),
                outcome=DownloadOutcome.SUCCESS,
                path=getattr(request, "destination", None),
                bytes_written=1,
                message="ok",
            )

    monkeypatch.setattr(download_job, "resolve_credentials", lambda source: object())
    monkeypatch.setattr(download_job, "RealAsfDownloader", SlowDownloader)

    manager = AsfDownloadManager()
    first = manager.start(
        [Scene(scene_id="S1A_first", url="https://datapool.asf.alaska.edu/SLC/first.zip")],
        tmp_path / "first",
    )
    assert first["ok"] is True
    paused = manager.pause(str(first["task_id"]))
    assert paused["ok"] is True

    second = manager.start(
        [Scene(scene_id="S1A_second", url="https://datapool.asf.alaska.edu/SLC/second.zip")],
        tmp_path / "second",
    )

    assert second["ok"] is True
    assert second["task_id"] != first["task_id"]
    status = manager.get_status()
    assert len(status["asf_tasks"]) >= 2
    manager.shutdown(timeout=1.0)


def test_asf_download_manager_reuses_restored_task_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDownloader:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def download(self, request: object) -> DownloadResult:
            return DownloadResult(
                scene_id=str(request.scene_id),
                outcome=DownloadOutcome.SUCCESS,
                path=getattr(request, "destination", None),
                bytes_written=1,
                message="ok",
            )

    monkeypatch.setattr(download_job, "resolve_credentials", lambda source: object())
    monkeypatch.setattr(download_job, "RealAsfDownloader", FakeDownloader)
    manager = AsfDownloadManager()

    started = manager.start(
        [Scene(scene_id="S1A_restored", url="https://example.test/restored.zip")],
        tmp_path,
        task_id="asf-restored",
    )

    assert started["task_id"] == "asf-restored"
    manager.shutdown(timeout=1.0)


def test_asf_download_manager_status_preserves_task_aoi_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDownloader:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def download(self, request: object) -> DownloadResult:
            return DownloadResult(
                scene_id=str(request.scene_id),
                outcome=DownloadOutcome.SUCCESS,
                path=getattr(request, "destination", None),
                bytes_written=1,
                message="ok",
            )

    monkeypatch.setattr(download_job, "resolve_credentials", lambda source: object())
    monkeypatch.setattr(download_job, "RealAsfDownloader", FakeDownloader)

    manager = AsfDownloadManager()
    started = manager.start(
        [Scene(scene_id="S1A_aoi", url="https://datapool.asf.alaska.edu/SLC/aoi.zip")],
        tmp_path / "aoi",
        aoi_name="全国",
    )
    assert started["ok"] is True

    deadline = time.monotonic() + 3
    status = manager.get_status()
    while status["state"] in {"running", "paused"} and time.monotonic() < deadline:
        time.sleep(0.01)
        status = manager.get_status()

    task_id = started["task_id"]
    task_status = next(item for item in status["asf_tasks"] if item["task_id"] == task_id)
    assert task_status["aoi_name"] == "全国"
    assert status["aoi_name"] == "全国"


def test_api_persists_paused_asf_archive_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    api._archive_asf_status(
        {
            "state": "paused",
            "total": 30,
            "done": 2,
            "concurrency": 2,
            "output_dir": str(tmp_path / "out"),
            "summary_line": "已暂停：2/30",
            "snapshot_scenes": [
                {
                    "scene_id": "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
                    "path": 88,
                    "frame": 456,
                    "download_url": "https://datapool.asf.alaska.edu/SLC/test.zip",
                }
            ],
            "log": [{"detail": "已暂停：当前 .part 文件保留，可继续或结束后断点续传。"}],
        }
    )

    restarted = Api()
    archive = restarted.get_download_archive()["items"]
    assert archive
    assert archive[0]["status"] == "paused"
    assert "Sentinel-1" in archive[0]["name"]
    assert archive[0]["kind"] == "asf"
    assert archive[0]["snapshot"][0]["path"] == 88
    assert archive[0]["snapshot"][0]["frame"] == 456
    assert archive[0]["scene_ids"] == [
        "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
    ]
    assert "已暂停" in archive[0]["logs"][-1]


def test_api_persists_all_paused_asf_manager_tasks_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    api._archive_asf_status(
        {
            "state": "paused",
            "task_id": "asf-primary",
            "total": 2,
            "done": 0,
            "output_dir": str(tmp_path / "primary"),
            "summary_line": "已暂停：0/2",
            "asf_tasks": [
                {
                    "state": "paused",
                    "task_id": "asf-first",
                    "total": 3,
                    "done": 1,
                    "output_dir": str(tmp_path / "first"),
                    "summary_line": "已暂停：1/3",
                    "log": [{"detail": "第一批已暂停"}],
                },
                {
                    "state": "paused",
                    "task_id": "asf-second",
                    "total": 4,
                    "done": 2,
                    "output_dir": str(tmp_path / "second"),
                    "summary_line": "已暂停：2/4",
                    "log": [{"detail": "第二批已暂停"}],
                },
            ],
        }
    )

    restarted = Api()
    archive = restarted.get_download_archive()["items"]
    paused_dirs = {Path(item["output_dir"]).name for item in archive if item["kind"] == "asf"}

    assert {"first", "second"}.issubset(paused_dirs)
    assert all(
        item["status"] == "paused"
        for item in archive
        if Path(item["output_dir"]).name in {"first", "second"}
    )


def test_api_keeps_two_asf_tasks_in_same_directory_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    output_dir = str(tmp_path / "shared")
    for task_id, scene_id, aoi_name in (
        ("asf-first", "S1A_FIRST", "全国"),
        ("asf-second", "S1A_SECOND", "上海市 / 长宁区"),
    ):
        api._archive_asf_status(
            {
                "state": "paused",
                "task_id": task_id,
                "total": 1,
                "done": 0,
                "output_dir": output_dir,
                "aoi_name": aoi_name,
                "snapshot_scenes": [
                    {
                        "scene_id": scene_id,
                        "download_url": f"https://example.test/{scene_id}.zip",
                    }
                ],
            }
        )

    archive = Api().get_download_archive()["items"]
    asf_items = [item for item in archive if item["kind"] == "asf"]

    assert {item["task_id"] for item in asf_items} == {"asf-first", "asf-second"}
    assert {item["snapshot"][0]["scene_id"] for item in asf_items} == {
        "S1A_FIRST",
        "S1A_SECOND",
    }


def test_api_marks_running_archive_interrupted_on_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    api._archive_asf_status(
        {
            "state": "running",
            "total": 30,
            "done": 1,
            "concurrency": 2,
            "output_dir": str(tmp_path / "out"),
            "summary_line": "正在下载：1/30",
            "log": [{"detail": "开始下载"}],
        }
    )

    restarted = Api()
    archive = restarted.get_download_archive()["items"]
    assert archive[0]["status"] == "interrupted"
    assert "上次关闭" in archive[0]["detail"]


def test_api_empty_ui_archive_does_not_clear_backend_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    api._archive_asf_status(
        {
            "state": "paused",
            "total": 2,
            "done": 1,
            "output_dir": str(tmp_path / "out"),
            "summary_line": "已暂停：1/2",
            "log": [{"detail": "暂停前已写入本地状态。"}],
        }
    )

    saved = api.save_download_archive([])

    assert saved["items"]
    restarted = Api()
    archive = restarted.get_download_archive()["items"]
    assert archive
    assert archive[0]["status"] == "paused"
    assert "暂停" in archive[0]["detail"]


def test_api_ui_archive_merges_instead_of_dropping_backend_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    api._archive_asf_status(
        {
            "state": "finished",
            "total": 1,
            "done": 1,
            "output_dir": str(tmp_path / "asf"),
            "summary_line": "全部完成",
            "log": [{"detail": "ASF 完成"}],
        }
    )

    saved = api.save_download_archive(
        [
            {
                "id": "dem:demo",
                "name": "DEM 下载与转换",
                "status": "finished",
                "detail": "DEM 完成",
                "ts": 123,
                "logs": ["DEM 完成"],
            }
        ]
    )

    ids = {item["id"] for item in saved["items"]}
    assert "dem:demo" in ids
    assert any(item_id.startswith("asf:") for item_id in ids)


def test_api_credential_status_detects_env_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import insar_prep.providers.asf.credentials as credentials

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv(credentials.EARTHDATA_TOKEN_ENV, "dummy-token")
    monkeypatch.setattr(credentials, "stored_credential_status", lambda: "none")

    status = Api().get_credential_status()
    assert status["earthdata"] == "env-token"
