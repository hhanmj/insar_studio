"""Background ASF SLC download for the pywebview desktop UI.

Mirrors :class:`insar_prep.gui.widgets.download_panel.DownloadWorker` without Qt:
the frontend polls :meth:`AsfDownloadJob.get_status` while a daemon thread runs
:func:`~insar_prep.providers.asf.download_runner.run_asf_download`'s per-scene loop
with optional pause-between-scenes and cancel support.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
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


@dataclass
class _JobState:
    state: str = "idle"
    total: int = 0
    done: int = 0
    current_scene: str = ""
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

    def get_status(self) -> dict:
        with self._lock:
            s = self._status
            return {
                "ok": True,
                "state": s.state,
                "total": s.total,
                "done": s.done,
                "current_scene": s.current_scene,
                "paused": s.paused,
                "cancelled": s.cancelled,
                "error": s.error,
                "summary_line": s.summary_line,
                "results_path": s.results_path,
                "log": list(s.log[-80:]),
            }

    def start(
        self,
        scenes: Iterable[object],
        output_dir: str | Path,
        *,
        credential_source: CredentialSource = CredentialSource.AUTO,
        max_retries: int = 3,
    ) -> dict:
        with self._lock:
            if self._status.state in ("running", "paused"):
                return {"ok": False, "error": "已有下载任务在进行", "code": "GUI004"}
        self._cancel.clear()
        self._pause.clear()
        with self._lock:
            self._status = _JobState(state="running")
        self._thread = threading.Thread(
            target=self._run,
            args=(list(scenes), Path(output_dir), credential_source, max_retries),
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
            self._status.current_scene = ""

    def _run(
        self,
        scenes: list[object],
        output_path: Path,
        credential_source: CredentialSource,
        max_retries: int,
    ) -> None:
        try:
            unique_scenes, _ = deduplicate_scenes(scenes)
            requests = download_requests_from_scenes(
                unique_scenes, slc_dir=output_path / SLC_SUBDIR
            )
            if not requests:
                raise InsarPrepError(
                    "no scenes with a download URL; import a cart that includes SLC URLs",
                    code=ErrorCode.ASF003,
                )
            resolved = resolve_credentials(credential_source)
            downloader = RealAsfDownloader(
                resolved=resolved, max_retries=max_retries, cancel_event=self._cancel
            )
            with self._lock:
                self._status.total = len(requests)

            results: list[DownloadResult] = []
            cancelled = False
            for request in requests:
                if self._cancel.is_set():
                    cancelled = True
                    break
                while self._pause.is_set() and not self._cancel.is_set():
                    time.sleep(0.25)
                if self._cancel.is_set():
                    cancelled = True
                    break
                with self._lock:
                    self._status.current_scene = mask_text(request.scene_id)
                result = downloader.download(request)
                results.append(result)
                self._append_log(result)
                if result.outcome is DownloadOutcome.INTERRUPTED:
                    cancelled = True
                    break

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
                self._status.summary_line = summary_line
                self._status.results_path = str(results_path) if results_path else ""
        except InsarPrepError as exc:
            with self._lock:
                self._status.state = "failed"
                self._status.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status.state = "failed"
                self._status.error = mask_text(f"{type(exc).__name__}: {exc}")
