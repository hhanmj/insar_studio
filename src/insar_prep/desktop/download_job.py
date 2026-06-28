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
    active_downloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_bytes: int | None = None
    done_bytes: int = 0
    current_bytes: int = 0
    current_expected_size: int | None = None
    bytes_per_second: float = 0.0
    started_at: float | None = None
    updated_at: float | None = None
    paused_started_at: float | None = None
    paused_total: float = 0.0
    cancelled: bool = False
    paused: bool = False
    error: str | None = None
    summary_line: str = ""
    results_path: str = ""
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    interrupted: int = 0
    has_failures: bool = False
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
        self._last_scenes: list[object] = []
        self._last_output_dir: Path | None = None
        self._last_credential_source: CredentialSource = CredentialSource.AUTO
        self._last_max_retries: int = 3
        self._last_max_concurrent: int = 1
        self._last_proxy_url: str = ""
        self._last_ssl_verify: bool = True
        self._last_trust_env: bool = False
        self._last_failed_scene_ids: set[str] = set()

    def _update_progress(
        self, scene_id: str, bytes_written: int, expected_size: int | None
    ) -> None:
        now = time.monotonic()
        with self._lock:
            s = self._status
            item = s.active_downloads.setdefault(
                scene_id,
                {
                    "scene_id": mask_text(scene_id),
                    "bytes": 0,
                    "expected_size": expected_size,
                    "started_at": now,
                },
            )
            item["bytes"] = max(0, int(bytes_written))
            item["expected_size"] = expected_size
            item["updated_at"] = now
            active = list(s.active_downloads.values())
            s.current_scene = ", ".join(str(item["scene_id"]) for item in active)
            s.current_bytes = sum(int(item.get("bytes") or 0) for item in active)
            known_expected = [
                int(item["expected_size"])
                for item in active
                if item.get("expected_size") is not None
            ]
            s.current_expected_size = sum(known_expected) if known_expected else None
            s.updated_at = now
            if s.started_at is not None:
                elapsed = max(0.001, now - s.started_at - s.paused_total)
                s.bytes_per_second = (s.done_bytes + s.current_bytes) / elapsed

    @staticmethod
    def _elapsed_seconds(s: _JobState) -> float:
        if s.started_at is None:
            return 0.0
        reference = s.paused_started_at if s.paused and s.paused_started_at else (s.updated_at or time.monotonic())
        return max(0.0, reference - s.started_at - s.paused_total)

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
                "active_downloads": list(s.active_downloads.values()),
                "total_bytes": s.total_bytes,
                "done_bytes": s.done_bytes,
                "current_bytes": s.current_bytes,
                "current_expected_size": s.current_expected_size,
                "bytes_per_second": s.bytes_per_second,
                "elapsed_seconds": self._elapsed_seconds(s),
                "paused": s.paused,
                "cancelled": s.cancelled,
                "error": s.error,
                "summary_line": s.summary_line,
                "results_path": s.results_path,
                "output_dir": str(self._last_output_dir) if self._last_output_dir else "",
                "succeeded": s.succeeded,
                "skipped": s.skipped,
                "failed": s.failed,
                "interrupted": s.interrupted,
                "has_failures": s.has_failures,
                "resume_supported": True,
                "resume_hint": "暂停或强制结束会保留 .part；再次开始同一输出目录会断点续传。",
                "retry_supported": bool(
                    s.has_failures
                    and self._last_failed_scene_ids
                    and s.state not in ("running", "paused")
                ),
                "retry_hint": "只重试失败/中断的场景；已完成文件会跳过，.part 文件会继续续传。",
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
        proxy_url: str = "",
        ssl_verify: bool = True,
        trust_env: bool = False,
        activity: ActivityLog | None = None,
    ) -> dict:
        scene_list = list(scenes)
        output_path = Path(output_dir)
        with self._lock:
            if self._status.state in ("running", "paused"):
                return {"ok": False, "error": "已有下载任务在进行", "code": "GUI004"}
        self._cancel.clear()
        self._pause.clear()
        self._activity = activity
        workers = max(1, min(int(max_concurrent or 1), 8))
        with self._lock:
            self._last_scenes = scene_list
            self._last_output_dir = output_path
            self._last_credential_source = credential_source
            self._last_max_retries = max_retries
            self._last_max_concurrent = workers
            self._last_proxy_url = str(proxy_url or "").strip()
            self._last_ssl_verify = bool(ssl_verify)
            self._last_trust_env = bool(trust_env)
            self._last_failed_scene_ids = set()
            now = time.monotonic()
            self._status = _JobState(
                state="running",
                concurrency=workers,
                started_at=now,
                updated_at=now,
            )
        self._thread = threading.Thread(
            target=self._run,
            args=(
                scene_list,
                output_path,
                credential_source,
                max_retries,
                workers,
                str(proxy_url or "").strip(),
                bool(ssl_verify),
                bool(trust_env),
            ),
            daemon=True,
        )
        self._thread.start()
        return {"ok": True}

    def pause(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if self._status.state != "running":
                return {"ok": False, "error": "当前没有进行中的下载", "code": "GUI004"}
            self._status.paused_started_at = now
            self._status.updated_at = now
            self._status.paused = True
            self._status.state = "paused"
            self._status.log.append(
                {
                    "scene_id": "",
                    "outcome": "paused",
                    "bytes_written": 0,
                    "message": "用户已暂停下载",
                    "detail": "已暂停：当前 .part 文件保留，可继续或结束后断点续传。",
                }
            )
        self._pause.set()
        return {"ok": True}

    def resume(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if self._status.state != "paused":
                return {"ok": False, "error": "下载未处于暂停状态", "code": "GUI004"}
            if self._status.paused_started_at is not None:
                self._status.paused_total += max(0.0, now - self._status.paused_started_at)
            self._status.paused_started_at = None
            self._status.updated_at = now
            self._status.paused = False
            self._status.state = "running"
            self._status.log.append(
                {
                    "scene_id": "",
                    "outcome": "resumed",
                    "bytes_written": 0,
                    "message": "用户已继续下载",
                    "detail": "已继续：从暂停位置恢复队列。",
                }
            )
        self._pause.clear()
        return {"ok": True}

    def stop(self) -> dict:
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有进行中的下载", "code": "GUI004"}
        self._cancel.set()
        self._pause.clear()
        return {"ok": True}

    @staticmethod
    def _normalise_scene_id(value: object) -> str:
        text = str(value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
        if text.lower().endswith(".zip"):
            text = text[:-4]
        for suffix in ("-SLC", "-GRD", "-RAW", "-OCN"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        return text

    def retry_failed(self, *, activity: ActivityLog | None = None) -> dict:
        """Restart only scenes that failed/interrupted in the previous ASF task."""
        with self._lock:
            if self._status.state in ("running", "paused"):
                return {"ok": False, "error": "请先等待当前下载结束，或先结束当前任务", "code": "GUI004"}
            if not self._last_scenes or self._last_output_dir is None:
                return {"ok": False, "error": "没有可重试的 ASF 下载任务", "code": "GUI004"}
            failed_ids = {self._normalise_scene_id(item) for item in self._last_failed_scene_ids}
            if not failed_ids:
                return {"ok": False, "error": "当前没有失败或中断的 ASF 场景可重试", "code": "GUI004"}
            scenes = list(self._last_scenes)
            output_dir = self._last_output_dir
            credential_source = self._last_credential_source
            max_retries = self._last_max_retries
            max_concurrent = self._last_max_concurrent
            proxy_url = self._last_proxy_url
            ssl_verify = self._last_ssl_verify
            trust_env = self._last_trust_env

        retry_scenes = [
            scene
            for scene in scenes
            if self._normalise_scene_id(getattr(scene, "scene_id", "")) in failed_ids
        ]
        if not retry_scenes:
            return {"ok": False, "error": "没有匹配到可重试的失败场景", "code": "GUI004"}
        return self.start(
            retry_scenes,
            output_dir,
            credential_source=credential_source,
            max_retries=max_retries,
            max_concurrent=max_concurrent,
            proxy_url=proxy_url,
            ssl_verify=ssl_verify,
            trust_env=trust_env,
            activity=activity or self._activity,
        )

    def _append_log(self, result: DownloadResult) -> None:
        suffix = f" [{result.error_code}]" if result.error_code else ""
        message = mask_text(result.message) if result.message else ""
        detail = f"{result.outcome.value} ({result.bytes_written} bytes){suffix}"
        if message:
            detail = f"{detail}: {message}"
        entry = {
            "scene_id": mask_text(result.scene_id),
            "outcome": result.outcome.value,
            "bytes_written": result.bytes_written,
            "message": message,
            "detail": detail,
        }
        with self._lock:
            s = self._status
            self._status.log.append(entry)
            s.done += 1
            s.done_bytes += int(result.bytes_written or 0)
            if result.outcome is DownloadOutcome.SUCCESS:
                s.succeeded += 1
            elif result.outcome is DownloadOutcome.SKIPPED:
                s.skipped += 1
            elif result.outcome is DownloadOutcome.FAILED:
                s.failed += 1
                s.has_failures = True
                s.error = message or suffix.strip() or "下载失败"
            elif result.outcome is DownloadOutcome.INTERRUPTED:
                s.interrupted += 1
                s.has_failures = True
                s.error = message or suffix.strip() or "下载中断"
            s.active_downloads.pop(result.scene_id, None)
            active = list(s.active_downloads.values())
            s.current_bytes = sum(int(item.get("bytes") or 0) for item in active)
            known_expected = [
                int(item["expected_size"])
                for item in active
                if item.get("expected_size") is not None
            ]
            s.current_expected_size = sum(known_expected) if known_expected else None
            s.updated_at = time.monotonic()
            s.current_scene = ", ".join(str(item["scene_id"]) for item in active)
            if s.total:
                s.summary_line = (
                    f"{s.succeeded} 已下载, {s.skipped} 跳过, "
                    f"{s.failed} 失败, {s.interrupted} 中断"
                )
            if result.outcome in {DownloadOutcome.FAILED, DownloadOutcome.INTERRUPTED}:
                self._last_failed_scene_ids.add(result.scene_id)
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
        proxy_url: str,
        ssl_verify: bool,
        trust_env: bool,
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
                    now = time.monotonic()
                    self._status.active_downloads[str(scene_id)] = {
                        "scene_id": mask_text(str(scene_id)),
                        "bytes": 0,
                        "expected_size": expected_size,
                        "started_at": now,
                        "updated_at": now,
                    }
                    active = list(self._status.active_downloads.values())
                    self._status.current_scene = ", ".join(str(item["scene_id"]) for item in active)
                    self._status.current_bytes = sum(int(item.get("bytes") or 0) for item in active)
                    known_expected = [
                        int(item["expected_size"])
                        for item in active
                        if item.get("expected_size") is not None
                    ]
                    self._status.current_expected_size = sum(known_expected) if known_expected else None
                    self._status.updated_at = now
                downloader = RealAsfDownloader(
                    resolved=resolved,
                    max_retries=max_retries,
                    proxy_url=proxy_url,
                    ssl_verify=ssl_verify,
                    trust_env=trust_env,
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
            succeeded = counts.get(DownloadOutcome.SUCCESS, 0)
            skipped = counts.get(DownloadOutcome.SKIPPED, 0)
            failed = counts.get(DownloadOutcome.FAILED, 0)
            interrupted = counts.get(DownloadOutcome.INTERRUPTED, 0)
            has_failures = failed > 0 or interrupted > 0
            if cancelled:
                final_state = "cancelled"
            elif has_failures and (succeeded + skipped) == 0:
                final_state = "failed"
            else:
                final_state = "finished"
            with self._lock:
                self._status.state = final_state
                self._status.cancelled = cancelled
                self._status.paused = False
                self._status.paused_started_at = None
                self._status.summary_line = summary_line
                self._status.results_path = str(results_path) if results_path else ""
                self._status.succeeded = succeeded
                self._status.skipped = skipped
                self._status.failed = failed
                self._status.interrupted = interrupted
                self._status.has_failures = has_failures
                self._status.current_scene = ""
                self._status.active_downloads = {}
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
    paused_started_at: float | None = None
    paused_total: float = 0.0
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

    @staticmethod
    def _elapsed_seconds(s: _OrbitJobState) -> float:
        if s.started_at is None:
            return 0.0
        reference = s.paused_started_at if s.paused and s.paused_started_at else (s.updated_at or time.monotonic())
        return max(0.0, reference - s.started_at - s.paused_total)

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
                "elapsed_seconds": self._elapsed_seconds(s),
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
        now = time.monotonic()
        with self._lock:
            if self._status.state != "running":
                return {"ok": False, "error": "当前没有进行中的轨道下载", "code": "GUI004"}
            self._status.paused = True
            self._status.state = "paused"
            self._status.paused_started_at = now
            self._status.updated_at = now
            self._status.log.append(
                {"scene_id": "", "outcome": "paused", "detail": "已暂停：等待当前 EOF 请求结束后停在队列。"}
            )
        self._pause.set()
        return {"ok": True}

    def resume(self) -> dict:
        now = time.monotonic()
        with self._lock:
            if self._status.state != "paused":
                return {"ok": False, "error": "轨道下载未处于暂停状态", "code": "GUI004"}
            if self._status.paused_started_at is not None:
                self._status.paused_total += max(0.0, now - self._status.paused_started_at)
            self._status.paused_started_at = None
            self._status.paused = False
            self._status.state = "running"
            self._status.updated_at = now
            self._status.log.append(
                {"scene_id": "", "outcome": "resumed", "detail": "已继续：恢复精密轨道队列。"}
            )
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
        outcome = str(data.get("outcome", ""))
        scene_id = mask_text(str(data.get("scene_id", "")))
        orbit_file = mask_text(str(data.get("orbit_file", "")))
        message = mask_text(str(data.get("message", "")))
        outcome_label = {
            "success": "成功",
            "skipped": "已存在/复用",
            "unavailable": "未发布/不可用",
            "failed": "失败",
        }.get(outcome, outcome or "未知")
        details = [f"{scene_id}: {outcome_label}"]
        if orbit_file:
            details.append(f"EOF {orbit_file}")
        if outcome in {"unavailable", "failed"} and message:
            details.append(message)
        entry = {
            "scene_id": scene_id,
            "outcome": outcome,
            "detail": "；".join(details),
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
            report = None
            verification_line = "总体核对：未能扫描轨道目录。"
            try:
                orbit_files = scan_orbit_directory(orbit_dir, recursive=True)
                report = match_orbits_for_scenes(unique_scenes, orbit_files).model_dump(mode="json")
                matched = int(report.get("matched_scenes") or 0)
                total = int(report.get("total_scenes") or len(unique_scenes))
                verification_line = f"总体核对：匹配 {matched}/{total} 景。"
            except Exception:  # noqa: BLE001 - a download result is still useful
                report = None
            summary_line = (
                f"单景结果：成功 {succeeded}，已存在/复用 {skipped}，"
                f"未发布/不可用 {unavailable}，失败 {failed}；{verification_line}"
            )
            cancelled = self._cancel.is_set()
            with self._lock:
                self._status.state = "cancelled" if cancelled else "finished"
                self._status.cancelled = cancelled
                self._status.paused = False
                self._status.paused_started_at = None
                self._status.succeeded = succeeded
                self._status.skipped = skipped
                self._status.unavailable = unavailable
                self._status.failed = failed
                self._status.has_failures = failed > 0
                self._status.summary_line = summary_line
                self._status.report = report
                self._status.log.append(
                    {"scene_id": "", "outcome": "verified", "detail": verification_line}
                )
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
