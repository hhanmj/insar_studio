"""Background ASF Sentinel-1 download for the pywebview desktop UI.

Mirrors :class:`insar_prep.gui.widgets.download_panel.DownloadWorker` without Qt:
the frontend polls :meth:`AsfDownloadJob.get_status` while a daemon thread runs
:func:`~insar_prep.providers.asf.download_runner.run_asf_download`'s per-scene loop
with pause/cancel support and resumable ``.part`` transfers.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.providers.asf.credentials import CredentialSource, resolve_credentials
from insar_prep.providers.asf.download_plan import SLC_SUBDIR
from insar_prep.providers.asf.download_runner import write_download_results_csv
from insar_prep.providers.asf.downloader import (
    DownloadOutcome,
    DownloadResult,
    RealAsfDownloader,
    download_requests_from_scenes,
)
from insar_prep.providers.asf.scene_parser import deduplicate_scenes

if TYPE_CHECKING:
    from collections.abc import Iterable

    from insar_prep.desktop.activity_log import ActivityLog


@dataclass
class _JobState:
    state: str = "idle"
    total: int = 0
    done: int = 0
    concurrency: int = 1
    current_scene: str = ""
    total_bytes: int | None = None
    done_bytes: int = 0
    current_bytes: int = 0
    current_expected_size: int | None = None
    bytes_per_second: float = 0.0
    started_at: float | None = None
    updated_at: float | None = None
    cancelled: bool = False
    paused: bool = False
    error: str | None = None
    summary_line: str = ""
    results_path: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)


class AsfDownloadJob:
    """Single-flight ASF download runner (thread-safe status for JS polling)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = _JobState()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._activity: ActivityLog | None = None

    def _update_progress(
        self, scene_id: str, bytes_written: int, expected_size: int | None
    ) -> None:
        now = time.monotonic()
        with self._lock:
            s = self._status
            s.current_scene = mask_text(scene_id)
            s.current_bytes = max(0, int(bytes_written))
            s.current_expected_size = expected_size
            s.updated_at = now
            if s.started_at is not None:
                elapsed = max(0.001, now - s.started_at)
                s.bytes_per_second = (s.done_bytes + s.current_bytes) / elapsed

    def get_status(self) -> dict:
        with self._lock:
            s = self._status
            return {
                "ok": True,
                "state": s.state,
                "total": s.total,
                "done": s.done,
                "concurrency": s.concurrency,
                "current_scene": s.current_scene,
                "total_bytes": s.total_bytes,
                "done_bytes": s.done_bytes,
                "current_bytes": s.current_bytes,
                "current_expected_size": s.current_expected_size,
                "bytes_per_second": s.bytes_per_second,
                "elapsed_seconds": (
                    max(0.0, (s.updated_at or time.monotonic()) - s.started_at)
                    if s.started_at is not None
                    else 0.0
                ),
                "paused": s.paused,
                "cancelled": s.cancelled,
                "error": s.error,
                "summary_line": s.summary_line,
                "results_path": s.results_path,
                "resume_supported": True,
                "resume_hint": "暂停或强制结束会保留 .part；再次开始同一输出目录会断点续传。",
                "log": list(s.log[-80:]),
            }

    def start(
        self,
        scenes: Iterable[object],
        output_dir: str | Path,
        *,
        credential_source: CredentialSource = CredentialSource.AUTO,
        max_retries: int = 3,
        max_concurrent: int = 1,
        activity: ActivityLog | None = None,
    ) -> dict:
        with self._lock:
            if self._status.state in ("running", "paused"):
                return {"ok": False, "error": "已有下载任务在进行", "code": "GUI004"}
        self._cancel.clear()
        self._pause.clear()
        self._activity = activity
        with self._lock:
            now = time.monotonic()
            self._status = _JobState(
                state="running",
                concurrency=max(1, min(int(max_concurrent or 1), 8)),
                started_at=now,
                updated_at=now,
            )
        self._thread = threading.Thread(
            target=self._run,
            args=(list(scenes), Path(output_dir), credential_source, max_retries, max_concurrent),
            daemon=True,
        )
        self._thread.start()
        return {"ok": True}

    def pause(self) -> dict:
        with self._lock:
            if self._status.state != "running":
                return {"ok": False, "error": "当前没有进行中的下载", "code": "GUI004"}
        self._pause.set()
        with self._lock:
            self._status.paused = True
            self._status.state = "paused"
        return {"ok": True}

    def resume(self) -> dict:
        with self._lock:
            if self._status.state != "paused":
                return {"ok": False, "error": "下载未处于暂停状态", "code": "GUI004"}
        self._pause.clear()
        with self._lock:
            self._status.paused = False
            self._status.state = "running"
        return {"ok": True}

    def stop(self) -> dict:
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有进行中的下载", "code": "GUI004"}
        self._cancel.set()
        self._pause.clear()
        return {"ok": True}

    def _append_log(self, result: DownloadResult) -> None:
        suffix = f" [{result.error_code}]" if result.error_code else ""
        entry = {
            "scene_id": mask_text(result.scene_id),
            "outcome": result.outcome.value,
            "bytes_written": result.bytes_written,
            "message": mask_text(result.message) if result.message else "",
            "detail": f"{result.outcome.value} ({result.bytes_written} bytes){suffix}",
        }
        with self._lock:
            self._status.log.append(entry)
            self._status.done += 1
            self._status.done_bytes += int(result.bytes_written or 0)
            self._status.current_bytes = 0
            self._status.current_expected_size = None
            self._status.updated_at = time.monotonic()
            self._status.current_scene = ""
        if self._activity is not None:
            self._activity.add(
                f"ASF {entry['scene_id']}: {result.outcome.value}",
                kind="download",
            )

    def _run(
        self,
        scenes: list[object],
        output_path: Path,
        credential_source: CredentialSource,
        max_retries: int,
        max_concurrent: int,
    ) -> None:
        try:
            unique_scenes, _ = deduplicate_scenes(scenes)
            requests = download_requests_from_scenes(
                unique_scenes, slc_dir=output_path / SLC_SUBDIR
            )
            if not requests:
                raise InsarPrepError(
                    "no scenes with a download URL; import an ASF cart that includes download URLs",
                    code=ErrorCode.ASF003,
                )
            resolved = resolve_credentials(credential_source)
            workers = max(1, min(int(max_concurrent or 1), 8))
            with self._lock:
                self._status.total = len(requests)
                self._status.concurrency = workers
                known_sizes = [
                    int(req.expected_size)
                    for req in requests
                    if req.expected_size is not None
                ]
                self._status.total_bytes = sum(known_sizes) if known_sizes else None

            results: list[DownloadResult] = []
            results_lock = threading.Lock()

            def run_one(request: object) -> bool:
                while self._pause.is_set() and not self._cancel.is_set():
                    time.sleep(0.25)
                if self._cancel.is_set():
                    return False
                scene_id = getattr(request, "scene_id", "")
                expected_size = getattr(request, "expected_size", None)
                with self._lock:
                    self._status.current_scene = mask_text(str(scene_id))
                    self._status.current_bytes = 0
                    self._status.current_expected_size = expected_size
                    self._status.updated_at = time.monotonic()
                downloader = RealAsfDownloader(
                    resolved=resolved,
                    max_retries=max_retries,
                    cancel_event=self._cancel,
                    pause_event=self._pause,
                    progress_callback=self._update_progress,
                )
                result = downloader.download(request)
                with results_lock:
                    results.append(result)
                self._append_log(result)
                if result.outcome is DownloadOutcome.INTERRUPTED:
                    self._cancel.set()
                    return False
                return True

            cancelled = False
            if workers <= 1:
                for request in requests:
                    if self._cancel.is_set():
                        cancelled = True
                        break
                    if not run_one(request):
                        cancelled = self._cancel.is_set()
                        break
            else:
                pending: Queue[object] = Queue()
                for request in requests:
                    pending.put(request)

                def worker() -> None:
                    while not self._cancel.is_set():
                        try:
                            request = pending.get_nowait()
                        except Empty:
                            return
                        try:
                            run_one(request)
                        finally:
                            pending.task_done()

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(worker) for _ in range(workers)]
                    wait(futures)
                    for future in futures:
                        future.result()
                cancelled = self._cancel.is_set()

            results_path = write_download_results_csv(output_path, results) if results else None
            counts = {outcome: 0 for outcome in DownloadOutcome}
            for result in results:
                counts[result.outcome] += 1
            summary_line = (
                f"{counts.get(DownloadOutcome.SUCCESS, 0)} 已下载, "
                f"{counts.get(DownloadOutcome.SKIPPED, 0)} 跳过, "
                f"{counts.get(DownloadOutcome.FAILED, 0)} 失败, "
                f"{counts.get(DownloadOutcome.INTERRUPTED, 0)} 中断"
            )
            final_state = "cancelled" if cancelled else "finished"
            with self._lock:
                self._status.state = final_state
                self._status.cancelled = cancelled
                self._status.paused = False
                self._status.summary_line = summary_line
                self._status.results_path = str(results_path) if results_path else ""
                self._status.current_scene = ""
                self._status.current_bytes = 0
                self._status.current_expected_size = None
                self._status.updated_at = time.monotonic()
            if self._activity is not None:
                prefix = "下载已取消" if cancelled else "下载完成"
                self._activity.add(f"{prefix}：{summary_line}", kind="download")
        except InsarPrepError as exc:
            with self._lock:
                self._status.state = "failed"
                self._status.error = str(exc)
                self._status.updated_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status.state = "failed"
                self._status.error = mask_text(f"{type(exc).__name__}: {exc}")
                self._status.updated_at = time.monotonic()


@dataclass
class _OrbitJobState:
    state: str = "idle"
    total: int = 0
    done: int = 0
    current_scene: str = ""
    orbit_dir: str = ""
    started_at: float | None = None
    updated_at: float | None = None
    cancelled: bool = False
    paused: bool = False
    error: str | None = None
    summary_line: str = ""
    succeeded: int = 0
    skipped: int = 0
    unavailable: int = 0
    failed: int = 0
    has_failures: bool = False
    results: list[dict[str, Any]] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] | None = None


class OrbitDownloadJob:
    """Single-flight Sentinel-1 orbit downloader with progress polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = _OrbitJobState()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._activity: ActivityLog | None = None

    def get_status(self) -> dict:
        with self._lock:
            s = self._status
            return {
                "ok": True,
                "state": s.state,
                "total": s.total,
                "done": s.done,
                "current_scene": s.current_scene,
                "orbit_dir": s.orbit_dir,
                "elapsed_seconds": (
                    max(0.0, (s.updated_at or time.monotonic()) - s.started_at)
                    if s.started_at is not None
                    else 0.0
                ),
                "paused": s.paused,
                "cancelled": s.cancelled,
                "error": s.error,
                "summary_line": s.summary_line,
                "succeeded": s.succeeded,
                "skipped": s.skipped,
                "unavailable": s.unavailable,
                "failed": s.failed,
                "has_failures": s.has_failures,
                "results": list(s.results[-120:]),
                "log": list(s.log[-120:]),
                "report": s.report,
                "pause_hint": "轨道文件较小，暂停/结束会在当前 EOF 请求结束后生效。",
            }

    def start(
        self,
        scenes: Iterable[object],
        output_dir: str | Path,
        *,
        activity: ActivityLog | None = None,
    ) -> dict:
        scene_list = list(scenes)
        if not scene_list:
            return {"ok": False, "error": "请先导入 ASF 场景或本地 SLC 目录", "code": "ASF001"}
        with self._lock:
            if self._status.state in ("running", "paused"):
                return {"ok": False, "error": "已有轨道下载任务在进行", "code": "GUI004"}
        self._cancel.clear()
        self._pause.clear()
        self._activity = activity
        with self._lock:
            now = time.monotonic()
            self._status = _OrbitJobState(state="running", started_at=now, updated_at=now)
        self._thread = threading.Thread(
            target=self._run,
            args=(scene_list, Path(output_dir)),
            daemon=True,
        )
        self._thread.start()
        return {"ok": True}

    def pause(self) -> dict:
        with self._lock:
            if self._status.state != "running":
                return {"ok": False, "error": "当前没有进行中的轨道下载", "code": "GUI004"}
            self._status.paused = True
            self._status.state = "paused"
            self._status.updated_at = time.monotonic()
        self._pause.set()
        return {"ok": True}

    def resume(self) -> dict:
        with self._lock:
            if self._status.state != "paused":
                return {"ok": False, "error": "轨道下载未处于暂停状态", "code": "GUI004"}
            self._status.paused = False
            self._status.state = "running"
            self._status.updated_at = time.monotonic()
        self._pause.clear()
        return {"ok": True}

    def stop(self) -> dict:
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有进行中的轨道下载", "code": "GUI004"}
            self._status.cancelled = True
            self._status.updated_at = time.monotonic()
        self._cancel.set()
        self._pause.clear()
        return {"ok": True}

    def _append_result(self, result: object) -> None:
        data = result.to_dict()
        entry = {
            "scene_id": mask_text(str(data.get("scene_id", ""))),
            "outcome": str(data.get("outcome", "")),
            "detail": f"{data.get('outcome', '')}: {mask_text(str(data.get('message', '')))}",
        }
        with self._lock:
            self._status.done += 1
            self._status.results.append(data)
            self._status.log.append(entry)
            self._status.current_scene = ""
            self._status.updated_at = time.monotonic()
        if self._activity is not None:
            self._activity.add(
                f"轨道 {entry['scene_id']}: {entry['outcome']}",
                kind="download",
            )

    def _run(self, scenes: list[object], output_path: Path) -> None:
        try:
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
            from insar_prep.providers.orbit import (
                OrbitDownloadOutcome,
                download_orbit_for_scene,
                match_orbits_for_scenes,
                poeorb_directory,
                scan_orbit_directory,
            )

            unique_scenes, _ = deduplicate_scenes(scenes)
            orbit_dir = poeorb_directory(output_path)
            seen_scene_ids: set[str] = set()
            with self._lock:
                self._status.total = len(unique_scenes)
                self._status.orbit_dir = str(orbit_dir)
                self._status.updated_at = time.monotonic()

            for scene in unique_scenes:
                if getattr(scene, "scene_id", "") in seen_scene_ids:
                    continue
                seen_scene_ids.add(getattr(scene, "scene_id", ""))
                if self._cancel.is_set():
                    break
                while self._pause.is_set() and not self._cancel.is_set():
                    time.sleep(0.25)
                if self._cancel.is_set():
                    break
                with self._lock:
                    self._status.current_scene = mask_text(getattr(scene, "scene_id", ""))
                    self._status.updated_at = time.monotonic()
                result = download_orbit_for_scene(scene, orbit_dir)
                self._append_result(result)

            results = list(self._status.results)
            succeeded = sum(1 for r in results if r.get("outcome") == OrbitDownloadOutcome.SUCCESS.value)
            skipped = sum(1 for r in results if r.get("outcome") == OrbitDownloadOutcome.SKIPPED.value)
            unavailable = sum(
                1 for r in results if r.get("outcome") == OrbitDownloadOutcome.UNAVAILABLE.value
            )
            failed = sum(1 for r in results if r.get("outcome") == OrbitDownloadOutcome.FAILED.value)
            summary_line = (
                f"{succeeded} downloaded, {skipped} skipped, "
                f"{unavailable} unavailable, {failed} failed"
            )
            report = None
            try:
                orbit_files = scan_orbit_directory(orbit_dir, recursive=True)
                report = match_orbits_for_scenes(unique_scenes, orbit_files).model_dump(mode="json")
            except Exception:  # noqa: BLE001 - a download result is still useful
                report = None
            cancelled = self._cancel.is_set()
            with self._lock:
                self._status.state = "cancelled" if cancelled else "finished"
                self._status.cancelled = cancelled
                self._status.paused = False
                self._status.succeeded = succeeded
                self._status.skipped = skipped
                self._status.unavailable = unavailable
                self._status.failed = failed
                self._status.has_failures = failed > 0
                self._status.summary_line = summary_line
                self._status.report = report
                self._status.current_scene = ""
                self._status.updated_at = time.monotonic()
            if self._activity is not None:
                self._activity.add(f"精密轨道下载完成：{summary_line}", kind="download")
        except InsarPrepError as exc:
            with self._lock:
                self._status.state = "failed"
                self._status.error = str(exc)
                self._status.updated_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status.state = "failed"
                self._status.error = mask_text(f"{type(exc).__name__}: {exc}")
                self._status.updated_at = time.monotonic()
