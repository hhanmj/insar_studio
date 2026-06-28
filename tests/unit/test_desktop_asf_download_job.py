from __future__ import annotations

import time
from pathlib import Path

import pytest

from insar_prep.core.models import Scene
from insar_prep.desktop.api import Api
from insar_prep.desktop import download_job
from insar_prep.desktop.download_job import AsfDownloadJob
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
        "S1A_bad": [DownloadOutcome.FAILED, DownloadOutcome.SUCCESS],
    }

    class FakeDownloader:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.append(kwargs)

        def download(self, request: object) -> DownloadResult:
            scene_id = str(getattr(request, "scene_id"))
            calls.append(scene_id)
            outcome = outcomes[scene_id].pop(0)
            return DownloadResult(
                scene_id=scene_id,
                outcome=outcome,
                path=getattr(request, "destination", None) if outcome is DownloadOutcome.SUCCESS else None,
                bytes_written=5 if outcome is DownloadOutcome.SUCCESS else 0,
                message="ok" if outcome is DownloadOutcome.SUCCESS else "network failed",
                error_code=None if outcome is DownloadOutcome.SUCCESS else "DL005",
            )

    monkeypatch.setattr(download_job, "resolve_credentials", lambda source: object())
    monkeypatch.setattr(download_job, "RealAsfDownloader", FakeDownloader)

    job = AsfDownloadJob()
    started = job.start(
        [
            Scene(scene_id="S1A_ok", url="https://datapool.asf.alaska.edu/SLC/ok.zip"),
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
    assert "network failed" in status["log"][-1]["detail"]
    assert status["has_failures"] is True
    assert init_kwargs[0]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[0]["ssl_verify"] is False
    assert init_kwargs[0]["trust_env"] is True

    retried = job.retry_failed()
    assert retried == {"ok": True}

    status = _wait_for_idle(job)
    assert status["state"] == "finished"
    assert status["failed"] == 0
    assert calls == ["S1A_ok", "S1A_bad", "S1A_bad"]
    assert init_kwargs[-1]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[-1]["ssl_verify"] is False
    assert init_kwargs[-1]["trust_env"] is True


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
            "log": [{"detail": "已暂停：当前 .part 文件保留，可继续或结束后断点续传。"}],
        }
    )

    restarted = Api()
    archive = restarted.get_download_archive()["items"]
    assert archive
    assert archive[0]["status"] == "paused"
    assert archive[0]["name"] == "ASF Sentinel-1 数据下载"
    assert "已暂停" in archive[0]["logs"][-1]


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
