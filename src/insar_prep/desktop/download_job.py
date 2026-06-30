"""Background ASF Sentinel-1 download for the pywebview desktop UI.

Mirrors :class:`insar_prep.gui.widgets.download_panel.DownloadWorker` without Qt:
the frontend polls :meth:`AsfDownloadJob.get_status` while a daemon thread runs
:func:`~insar_prep.providers.asf.download_runner.run_asf_download`'s per-scene loop
with pause/cancel support and resumable ``.part`` transfers.
"""

from __future__ import annotations

import threading
import time
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


class _CombinedEvent:
    """Tiny Event-like adapter that is set when any wrapped event is set."""

    def __init__(self, *events: threading.Event) -> None:
        self._events = events

    def is_set(self) -> bool:
        return any(event.is_set() for event in self._events)


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
        self._pending: Queue[object] | None = None
        self._worker_context: dict[str, Any] | None = None
        self._worker_threads: list[threading.Thread] = []
        self._results: list[DownloadResult] = []
        self._results_lock = threading.Lock()
        self._known_scene_ids: set[str] = set()
        self._completed_scene_ids: set[str] = set()
        self._paused_scene_ids: set[str] = set()
        self._paused_requests: dict[str, object] = {}
        self._scene_cancel_events: dict[str, threading.Event] = {}

    def _update_progress(
        self, scene_id: str, bytes_written: int, expected_size: int | None
    ) -> None:
        now = time.monotonic()
        scene_key = self._normalise_scene_id(scene_id)
        with self._lock:
            s = self._status
            item = s.active_downloads.setdefault(
                scene_key,
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
                "paused_scene_ids": sorted(self._paused_scene_ids),
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
            self._completed_scene_ids = set()
            self._paused_scene_ids = set()
            self._paused_requests = {}
            self._scene_cancel_events = {}
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
                    "ts": int(time.time() * 1000),
                }
            )
        self._pause.set()
        return {"ok": True}

    def resume(self) -> dict:
        now = time.monotonic()
        with self._lock:
            scene_paused_only = (
                self._status.state == "paused"
                and not self._pause.is_set()
                and bool(self._paused_scene_ids)
            )
            scene_ids = list(self._paused_scene_ids) if scene_paused_only else []
        if scene_paused_only:
            return self.resume_scenes(scene_ids)
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
                    "ts": int(time.time() * 1000),
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

    def shutdown(self, timeout: float = 2.0) -> dict:
        """Best-effort cleanup when the desktop window is closing."""
        with self._lock:
            state = self._status.state
            should_stop = state in ("running", "paused")
            if should_stop:
                self._status.updated_at = time.monotonic()
                self._status.log.append(
                    {
                        "scene_id": "",
                        "outcome": "app_shutdown",
                        "bytes_written": 0,
                        "message": "软件正在退出",
                        "detail": "软件正在退出：已保存当前下载状态，未完成的 .part 文件可用于下次续传。",
                        "ts": int(time.time() * 1000),
                    }
                )
                if state == "running":
                    self._status.state = "interrupted"
                    self._status.error = "软件关闭，下载已中断，可从历史记录恢复。"
                for event in self._scene_cancel_events.values():
                    event.set()
            thread = self._thread
            workers = list(self._worker_threads)
        if not should_stop:
            return {"ok": True, "stopped": False}
        self._cancel.set()
        self._pause.clear()
        deadline = time.monotonic() + max(0.1, float(timeout or 0.1))
        for item in [thread, *workers]:
            if item is None or not item.is_alive():
                continue
            remaining = max(0.05, deadline - time.monotonic())
            item.join(timeout=remaining)
            if time.monotonic() >= deadline:
                break
        return {"ok": True, "stopped": True}

    def append(
        self,
        scenes: Iterable[object],
        output_dir: str | Path | None = None,
        *,
        max_extra_workers: int = 1,
    ) -> dict:
        """Append selected scenes to the active ASF queue.

        This keeps the running task bound to its original output directory. It is
        intentionally queue-level control; full per-scene pause/cancel requires
        a deeper downloader event model.
        """
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有进行中的 ASF 下载任务，请直接开始下载", "code": "GUI004"}
            if self._pending is None or self._worker_context is None:
                return {"ok": False, "error": "当前下载队列尚未准备好，请稍后再试", "code": "GUI004"}
            bound_output = self._last_output_dir
        if bound_output is None:
            return {"ok": False, "error": "当前任务没有绑定输出目录，无法追加影像", "code": "GUI003"}
        requested_output = Path(output_dir) if output_dir else bound_output
        if requested_output != bound_output:
            return {
                "ok": False,
                "error": f"当前下载任务已绑定到 {bound_output}，追加影像会继续写入该目录",
                "code": "GUI003",
            }

        unique_scenes, _ = deduplicate_scenes(list(scenes))
        requests = download_requests_from_scenes(unique_scenes, slc_dir=bound_output / SLC_SUBDIR)
        if not requests:
            return {"ok": False, "error": "所选影像没有 ASF 下载 URL，请先重新检索或导入 ASF 官方文件。", "code": "ASF003"}

        new_requests: list[object] = []
        new_scene_ids: set[str] = set()
        with self._lock:
            if self._pending is None:
                return {"ok": False, "error": "当前下载队列已结束，请重新开始下载", "code": "GUI004"}
            live_workers = sum(1 for thread in self._worker_threads if thread.is_alive())
            if live_workers == 0 and not self._status.active_downloads:
                return {"ok": False, "error": "当前下载任务已进入收尾阶段，请重新开始下载所选影像", "code": "GUI004"}
            for request in requests:
                scene_id = self._normalise_scene_id(getattr(request, "scene_id", ""))
                if not scene_id or scene_id in self._known_scene_ids:
                    continue
                self._known_scene_ids.add(scene_id)
                new_scene_ids.add(scene_id)
                new_requests.append(request)
            if not new_requests:
                self._status.log.append(
                    {
                        "scene_id": "",
                        "outcome": "append_skipped",
                        "bytes_written": 0,
                        "message": "所选影像已在当前下载任务中",
                        "detail": "所选影像已在当前下载任务中，无需重复追加。",
                        "ts": int(time.time() * 1000),
                    }
                )
                self._status.updated_at = time.monotonic()
                return {"ok": True, "appended": 0, "skipped": len(requests), "concurrency": self._status.concurrency}
            for request in new_requests:
                self._pending.put(request)
            self._last_scenes.extend(
                scene
                for scene in unique_scenes
                if self._normalise_scene_id(getattr(scene, "scene_id", "")) in new_scene_ids
            )
            self._status.total += len(new_requests)
            new_sizes = [
                int(getattr(request, "expected_size"))
                for request in new_requests
                if getattr(request, "expected_size", None) is not None
            ]
            if new_sizes:
                self._status.total_bytes = int(self._status.total_bytes or 0) + sum(new_sizes)
            self._status.log.append(
                {
                    "scene_id": "",
                    "outcome": "appended",
                    "bytes_written": 0,
                    "message": f"已追加 {len(new_requests)} 景到当前 ASF 下载任务",
                    "detail": f"已追加 {len(new_requests)} 景到当前 ASF 下载任务。",
                    "ts": int(time.time() * 1000),
                }
            )
            self._status.updated_at = time.monotonic()

        extra = min(len(new_requests), max(0, 8 - live_workers), max(1, int(max_extra_workers or 1)))
        if extra > 0:
            self._start_workers(extra)
        return {
            "ok": True,
            "appended": len(new_requests),
            "skipped": max(0, len(requests) - len(new_requests)),
            "concurrency": self._live_worker_count(),
        }

    def pause_scenes(self, scene_ids: Iterable[str]) -> dict:
        requested = {self._normalise_scene_id(item) for item in scene_ids if self._normalise_scene_id(item)}
        if not requested:
            return {"ok": False, "error": "请先选择要暂停的影像", "code": "GUI003"}
        paused: list[str] = []
        not_found: list[str] = []
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有可管理的 ASF 下载任务", "code": "GUI004"}
            for scene_id in requested:
                if scene_id in self._completed_scene_ids:
                    not_found.append(scene_id)
                    continue
                if scene_id not in self._known_scene_ids:
                    not_found.append(scene_id)
                    continue
                self._paused_scene_ids.add(scene_id)
                event = self._scene_cancel_events.get(scene_id)
                if event is not None:
                    event.set()
                paused.append(scene_id)
            if paused:
                self._status.log.append(
                    {
                        "scene_id": ", ".join(paused),
                        "outcome": "scene_pause_requested",
                        "bytes_written": 0,
                        "message": f"请求暂停 {len(paused)} 景",
                        "detail": f"已请求暂停 {len(paused)} 景；正在传输的影像会保留 .part，用于继续下载。",
                        "ts": int(time.time() * 1000),
                    }
                )
                self._status.updated_at = time.monotonic()
        return {"ok": True, "paused": len(paused), "not_found": not_found}

    def resume_scenes(self, scene_ids: Iterable[str] | None = None) -> dict:
        requested = {self._normalise_scene_id(item) for item in (scene_ids or []) if self._normalise_scene_id(item)}
        resumed = 0
        with self._lock:
            if self._status.state not in ("running", "paused"):
                return {"ok": False, "error": "当前没有可继续的 ASF 下载任务", "code": "GUI004"}
            if self._pending is None:
                return {"ok": False, "error": "当前下载队列已结束，请重新开始下载", "code": "GUI004"}
            targets = requested or set(self._paused_scene_ids)
            for scene_id in list(targets):
                request = self._paused_requests.pop(scene_id, None)
                if request is None and scene_id in self._paused_scene_ids:
                    # The scene may still be inside the pending queue and will be
                    # allowed to start when a worker picks it up.
                    resumed += 1
                elif request is not None:
                    self._pending.put(request)
                    resumed += 1
                self._paused_scene_ids.discard(scene_id)
            if resumed:
                self._status.state = "running"
                self._status.paused = False
                self._status.log.append(
                    {
                        "scene_id": ", ".join(sorted(targets)),
                        "outcome": "scene_resumed",
                        "bytes_written": 0,
                        "message": f"已继续 {resumed} 景",
                        "detail": f"已继续 {resumed} 景；如存在 .part 文件会断点续传。",
                        "ts": int(time.time() * 1000),
                    }
                )
                self._status.updated_at = time.monotonic()
        if resumed:
            self._start_workers(max(1, min(resumed, 8)))
        return {"ok": True, "resumed": resumed}

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
            "ts": int(time.time() * 1000),
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
            result_key = self._normalise_scene_id(result.scene_id)
            self._completed_scene_ids.add(result_key)
            s.active_downloads.pop(result_key, None)
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
                self._last_failed_scene_ids.add(result_key)
        if self._activity is not None:
            self._activity.add(
                f"ASF {entry['scene_id']}: {result.outcome.value}",
                kind="download",
            )

    def _live_worker_count(self) -> int:
        with self._lock:
            return sum(1 for thread in self._worker_threads if thread.is_alive())

    def _start_workers(self, count: int) -> None:
        threads: list[threading.Thread] = []
        with self._lock:
            for _ in range(max(0, int(count or 0))):
                thread = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker_threads.append(thread)
                threads.append(thread)
            self._status.concurrency = max(
                self._status.concurrency,
                sum(1 for thread in self._worker_threads if thread.is_alive()) + len(threads),
            )
            if not self._pause.is_set() and self._status.state == "paused":
                self._status.state = "running"
                self._status.paused = False
            self._status.updated_at = time.monotonic()
        for thread in threads:
            thread.start()

    def _worker_loop(self) -> None:
        downloader = self._worker_downloader()
        while not self._cancel.is_set():
            while self._pause.is_set() and not self._cancel.is_set():
                time.sleep(0.25)
            if self._cancel.is_set():
                return
            pending = self._pending
            if pending is None:
                return
            try:
                request = pending.get(timeout=0.35)
            except Empty:
                with self._lock:
                    no_active = not self._status.active_downloads
                    queue_empty = self._pending is None or self._pending.empty()
                    no_scene_paused = not self._paused_requests and not self._paused_scene_ids
                if no_active and queue_empty and no_scene_paused:
                    return
                continue
            scene_id = self._normalise_scene_id(getattr(request, "scene_id", ""))
            try:
                with self._lock:
                    if scene_id in self._paused_scene_ids:
                        self._paused_requests[scene_id] = request
                        self._status.log.append(
                            {
                                "scene_id": scene_id,
                                "outcome": "scene_paused",
                                "bytes_written": 0,
                                "message": "单景已暂停",
                                "detail": f"{scene_id} 已暂停在等待队列中。",
                                "ts": int(time.time() * 1000),
                            }
                        )
                        self._status.updated_at = time.monotonic()
                        continue
                if not self._run_one(request, downloader):
                    return
            finally:
                pending.task_done()

    def _worker_downloader(self) -> RealAsfDownloader | None:
        context = self._worker_context
        if context is None:
            return None
        return RealAsfDownloader(
            resolved=context["resolved"],
            max_retries=context["max_retries"],
            proxy_url=context["proxy_url"],
            ssl_verify=context["ssl_verify"],
            trust_env=context["trust_env"],
            pause_event=self._pause,
            progress_callback=self._update_progress,
        )

    def _run_one(self, request: object, downloader: RealAsfDownloader | None) -> bool:
        while self._pause.is_set() and not self._cancel.is_set():
            time.sleep(0.25)
        if self._cancel.is_set():
            return False
        if downloader is None:
            return False
        scene_id = str(getattr(request, "scene_id", ""))
        scene_key = self._normalise_scene_id(scene_id)
        expected_size = getattr(request, "expected_size", None)
        scene_cancel = threading.Event()
        with self._lock:
            now = time.monotonic()
            self._scene_cancel_events[scene_key] = scene_cancel
            self._status.active_downloads[scene_key] = {
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
        downloader.cancel_event = _CombinedEvent(self._cancel, scene_cancel)
        result = downloader.download(request)
        with self._lock:
            self._scene_cancel_events.pop(scene_key, None)
        if scene_cancel.is_set() and not self._cancel.is_set():
            self._mark_scene_paused(request, result)
            return True
        with self._results_lock:
            self._results.append(result)
        self._append_log(result)
        if result.error_code == ErrorCode.DL004.value:
            with self._lock:
                self._status.error = "Earthdata/ASF 凭据被拒绝，已停止后续下载以保护账号。"
                self._status.log.append(
                    {
                        "scene_id": scene_id,
                        "outcome": "credential_rejected",
                        "bytes_written": result.bytes_written,
                        "message": "凭据被拒绝",
                        "detail": "Earthdata/ASF 凭据被拒绝，已停止后续下载；请检查 Token、用户名或密码。",
                        "ts": int(time.time() * 1000),
                    }
                )
            self._cancel.set()
            return False
        if result.outcome is DownloadOutcome.INTERRUPTED:
            self._cancel.set()
            return False
        return True

    def _mark_scene_paused(self, request: object, result: DownloadResult) -> None:
        scene_id = str(getattr(request, "scene_id", result.scene_id))
        scene_key = self._normalise_scene_id(scene_id)
        with self._lock:
            self._paused_scene_ids.add(scene_key)
            self._paused_requests[scene_key] = request
            self._status.active_downloads.pop(scene_key, None)
            active = list(self._status.active_downloads.values())
            self._status.current_scene = ", ".join(str(item["scene_id"]) for item in active)
            self._status.current_bytes = sum(int(item.get("bytes") or 0) for item in active)
            known_expected = [
                int(item["expected_size"])
                for item in active
                if item.get("expected_size") is not None
            ]
            self._status.current_expected_size = sum(known_expected) if known_expected else None
            if not active and (self._pending is None or self._pending.empty()):
                self._status.state = "paused"
                self._status.paused = True
            self._status.log.append(
                {
                    "scene_id": scene_id,
                    "outcome": "scene_paused",
                    "bytes_written": result.bytes_written,
                    "message": "单景已暂停",
                    "detail": f"{scene_id} 已暂停，已保留 .part，可在工作台继续。",
                    "ts": int(time.time() * 1000),
                }
            )
            self._status.updated_at = time.monotonic()

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
            pending: Queue[object] = Queue()
            for request in requests:
                pending.put(request)
            with self._lock:
                self._status.total = len(requests)
                self._status.concurrency = workers
                known_sizes = [
                    int(req.expected_size)
                    for req in requests
                    if req.expected_size is not None
                ]
                self._status.total_bytes = sum(known_sizes) if known_sizes else None
                self._pending = pending
                self._worker_context = {
                    "resolved": resolved,
                    "max_retries": max_retries,
                    "proxy_url": proxy_url,
                    "ssl_verify": ssl_verify,
                    "trust_env": trust_env,
                }
                self._worker_threads = []
                self._results = []
                self._known_scene_ids = {
                    self._normalise_scene_id(getattr(request, "scene_id", ""))
                    for request in requests
                    if getattr(request, "scene_id", "")
                }

            self._start_workers(workers)
            joined: set[threading.Thread] = set()
            while True:
                with self._lock:
                    threads = list(self._worker_threads)
                for thread in threads:
                    if thread not in joined:
                        thread.join()
                        joined.add(thread)
                with self._lock:
                    workers_idle = all(not thread.is_alive() for thread in self._worker_threads)
                    queue_empty = self._pending is None or self._pending.empty()
                    no_active = not self._status.active_downloads
                    no_scene_paused = not self._paused_requests and not self._paused_scene_ids
                    if self._cancel.is_set() or (workers_idle and queue_empty and no_active and no_scene_paused):
                        break
                time.sleep(0.2)
            cancelled = self._cancel.is_set()
            with self._results_lock:
                results = list(self._results)

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
                self._paused_scene_ids = set()
                self._paused_requests = {}
                self._scene_cancel_events = {}
            if self._activity is not None:
                prefix = "下载已取消" if cancelled else "下载完成"
                self._activity.add(f"{prefix}：{summary_line}", kind="download")
            with self._lock:
                self._pending = None
                self._worker_context = None
                self._worker_threads = []
        except InsarPrepError as exc:
            with self._lock:
                self._status.state = "failed"
                self._status.error = str(exc)
                self._status.updated_at = time.monotonic()
                self._pending = None
                self._worker_context = None
                self._worker_threads = []
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status.state = "failed"
                self._status.error = mask_text(f"{type(exc).__name__}: {exc}")
                self._status.updated_at = time.monotonic()
                self._pending = None
                self._worker_context = None
                self._worker_threads = []


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
                {
                    "scene_id": "",
                    "outcome": "paused",
                    "detail": "已暂停：等待当前 EOF 请求结束后停在队列。",
                    "ts": int(time.time() * 1000),
                }
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
                {
                    "scene_id": "",
                    "outcome": "resumed",
                    "detail": "已继续：恢复精密轨道队列。",
                    "ts": int(time.time() * 1000),
                }
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

    def shutdown(self, timeout: float = 2.0) -> dict:
        """Best-effort cleanup when the desktop window is closing."""
        with self._lock:
            state = self._status.state
            should_stop = state in ("running", "paused")
            if should_stop:
                self._status.updated_at = time.monotonic()
                self._status.log.append(
                    {
                        "scene_id": "",
                        "outcome": "app_shutdown",
                        "detail": "软件正在退出：已保存当前轨道下载状态，未完成任务可稍后重试。",
                        "ts": int(time.time() * 1000),
                    }
                )
                if state == "running":
                    self._status.state = "interrupted"
                    self._status.error = "软件关闭，精密轨道下载已中断，可从历史记录恢复。"
            thread = self._thread
        if not should_stop:
            return {"ok": True, "stopped": False}
        self._cancel.set()
        self._pause.clear()
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.1, float(timeout or 0.1)))
        return {"ok": True, "stopped": True}

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
            "ts": int(time.time() * 1000),
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
                    {
                        "scene_id": "",
                        "outcome": "verified",
                        "detail": verification_line,
                        "ts": int(time.time() * 1000),
                    }
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
