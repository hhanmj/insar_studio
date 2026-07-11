"""Download history/archive state management for the desktop API."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

ArchiveGetter = Callable[[], list[dict[str, Any]]]
ArchiveSetter = Callable[[list[dict[str, Any]]], None]
DeletedGetter = Callable[[], set[str]]
DeletedSetter = Callable[[set[str]], None]
SaveCallback = Callable[[], None]


class DownloadArchiveService:
    """Own download archive mutations while keeping legacy helper behavior."""

    def __init__(
        self,
        *,
        get_items: ArchiveGetter,
        set_items: ArchiveSetter,
        get_deleted_keys: DeletedGetter,
        set_deleted_keys: DeletedSetter,
        save_state: SaveCallback,
        helpers: dict[str, Callable[..., Any]],
    ) -> None:
        self._get_items = get_items
        self._set_items = set_items
        self._get_deleted_keys = get_deleted_keys
        self._set_deleted_keys = set_deleted_keys
        self._save_state = save_state
        self._helpers = helpers

    def get_archive(self) -> dict[str, Any]:
        """Return persisted download/task history across app restarts."""
        return {
            "ok": True,
            "items": self._dedupe(
                self._filter_deleted(
                    self._clean(self._get_items()),
                    self._get_deleted_keys(),
                )
            ),
        }

    def upsert(self, item: dict[str, Any]) -> None:
        """Insert or replace one archive item, preserving tombstones."""
        cleaned = self._clean([item])
        if not cleaned:
            return
        next_item = cleaned[0]
        next_keys = self._identity_candidates(next_item)
        if next_keys & self._get_deleted_keys():
            return
        previous = next(
            (old for old in self._get_items() if self._identity_candidates(old) & next_keys),
            None,
        )
        if previous is not None:
            same = all(
                previous.get(key) == next_item.get(key)
                for key in (
                    "name",
                    "status",
                    "detail",
                    "logs",
                    "snapshot",
                    "scene_ids",
                    "aoi_name",
                    "elapsed_seconds",
                )
            )
            if same:
                return
            if previous.get("status") == "paused" and next_item.get("status") == "paused":
                next_item["ts"] = previous.get("ts") or next_item["ts"]
        self._set_items(
            self._dedupe(
                [
                    next_item,
                    *(
                        old
                        for old in self._get_items()
                        if not (self._identity_candidates(old) & next_keys)
                    ),
                ]
            )
        )
        self._save_state()

    def forget_deleted_key(
        self,
        kind: str,
        output_dir: str,
        *,
        use_product_subdirs: bool = False,
        use_orbit_subdir: bool = False,
    ) -> None:
        """Allow an explicitly started new task to reuse a deleted archive slot."""
        cleaned = self._clean(
            [
                {
                    "id": f"{kind}:{output_dir}:0",
                    "name": kind,
                    "status": "running",
                    "detail": "new task",
                    "ts": int(time.time() * 1000),
                    "kind": kind,
                    "output_dir": output_dir,
                    "use_product_subdirs": use_product_subdirs,
                    "use_orbit_subdir": use_orbit_subdir,
                }
            ]
        )
        if not cleaned:
            return
        keys = self._identity_candidates(cleaned[0], include_legacy=True)
        stable_path = self._normalise_path(output_dir)
        stable_prefixes = {f"{kind}:{stable_path}"} if stable_path else set()
        deleted = set(self._get_deleted_keys())
        deleted.difference_update(keys)
        for prefix in stable_prefixes:
            deleted = {
                key
                for key in deleted
                if key != prefix
                and not key.startswith(f"{prefix}:")
                and not key.startswith(f"{prefix}\\")
            }
        self._set_deleted_keys(deleted)

    def archive_asf_status(self, status: dict[str, Any]) -> None:
        """Archive one ASF status snapshot."""
        tasks = status.get("asf_tasks")
        if isinstance(tasks, list) and tasks:
            for task in tasks:
                if isinstance(task, dict):
                    self.archive_asf_status(task)
            return
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "paused", "finished", "failed", "cancelled", "interrupted"}:
            return
        active = status.get("active_downloads")
        active_names = ""
        if isinstance(active, list):
            active_names = "；".join(
                str(item.get("scene_id") or "")
                for item in active[: int(status.get("concurrency") or 1)]
                if isinstance(item, dict) and item.get("scene_id")
            )
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or (f"正在下载：{active_names}" if active_names else "")
            or f"{int(status.get('done') or 0)}/{int(status.get('total') or 0)}"
        )
        logs = self._status_logs(status)
        snapshot = self._clean_scene_rows(status.get("snapshot_scenes"))
        raw_selected = status.get("selected_scene_ids")
        scene_ids = (
            [str(item).strip() for item in raw_selected if str(item).strip()]
            if isinstance(raw_selected, list)
            else [str(row.get("scene_id") or "") for row in snapshot if row.get("scene_id")]
        )
        task_id = str(status.get("task_id") or "").strip()
        archive_key = status.get("results_path") or status.get("output_dir") or "active"
        try:
            elapsed_seconds = float(status.get("elapsed_seconds") or 0)
        except (TypeError, ValueError):
            elapsed_seconds = 0.0
        self.upsert(
            {
                "id": f"asf-task:{task_id}" if task_id else f"asf:{archive_key}:{int(status.get('total') or 0)}",
                "task_id": task_id,
                "name": "Sentinel-1 下载任务",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "asf",
                "output_dir": str(status.get("output_dir") or ""),
                "total": int(status.get("total") or 0),
                "concurrency": int(status.get("concurrency") or 0),
                "use_product_subdirs": self._coerce_bool(status.get("use_product_subdirs"), False),
                "download_layout": str(status.get("download_layout") or "flat"),
                "snapshot": snapshot,
                "scene_ids": scene_ids,
                "aoi_name": str(status.get("aoi_name") or "").strip(),
                "elapsed_seconds": max(0.0, elapsed_seconds),
                "logs": logs,
            }
        )

    def archive_orbit_status(self, status: dict[str, Any]) -> None:
        """Archive one orbit status snapshot."""
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "paused", "finished", "failed", "cancelled", "interrupted"}:
            return
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or (f"正在处理：{status.get('current_scene')}" if status.get("current_scene") else "")
            or f"{int(status.get('done') or 0)}/{int(status.get('total') or 0)}"
        )
        snapshot = self._clean_scene_rows(status.get("snapshot_scenes"))
        scene_ids = [str(row.get("scene_id") or "") for row in snapshot if row.get("scene_id")]
        try:
            elapsed_seconds = float(status.get("elapsed_seconds") or 0)
        except (TypeError, ValueError):
            elapsed_seconds = 0.0
        archive_output_dir = str(status.get("output_dir") or status.get("orbit_dir") or "")
        archive_key = archive_output_dir or status.get("orbit_dir") or "active"
        self.upsert(
            {
                "id": f"orbit:{archive_key}:{int(status.get('total') or 0)}",
                "name": "Sentinel-1 精密轨道下载",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "orbit",
                "output_dir": archive_output_dir,
                "total": int(status.get("total") or 0),
                "use_orbit_subdir": self._coerce_bool(status.get("use_orbit_subdir"), False),
                "download_layout": str(status.get("download_layout") or "flat"),
                "snapshot": snapshot,
                "scene_ids": scene_ids,
                "aoi_name": str(status.get("aoi_name") or "").strip(),
                "elapsed_seconds": max(0.0, elapsed_seconds),
                "logs": self._status_logs(status),
            }
        )

    def archive_dem_status(self, status: dict[str, Any]) -> None:
        """Archive one DEM status snapshot."""
        state = str(status.get("state") or "")
        if bool(status.get("cancelled")):
            state = "cancelled"
        if state not in {"running", "finished", "failed", "cancelled", "interrupted"}:
            return
        output_dir = str(status.get("output_dir") or "").strip()
        dataset = str(status.get("dataset") or "DEM").strip()
        detail = (
            str(status.get("error") or "")
            or str(status.get("summary_line") or "")
            or f"正在下载：{dataset}"
        )
        self.upsert(
            {
                "id": (
                    f"dem:{output_dir or status.get('results_path') or dataset}:"
                    f"{int(status.get('total') or 1)}:{dataset}"
                ),
                "name": "DEM 下载并转换椭球高" if bool(status.get("convert")) else "DEM 下载",
                "status": state,
                "detail": detail,
                "ts": int(time.time() * 1000),
                "kind": "dem",
                "output_dir": output_dir,
                "total": int(status.get("total") or 1),
                "concurrency": 1,
                "logs": self._status_logs(status),
            }
        )

    def save_archive(self, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Persist UI-submitted task history without dropping backend rows."""
        incoming = self._filter_deleted(
            self._clean(items or [])[:40],
            self._get_deleted_keys(),
        )
        if not incoming and self._get_items():
            return self.get_archive()
        self._set_items(
            self._merge(
                incoming,
                self._filter_deleted(
                    self._clean(self._get_items()),
                    self._get_deleted_keys(),
                ),
            )
        )
        self._save_state()
        return self.get_archive()

    def delete_archive_item(self, item: dict[str, Any] | None = None) -> dict[str, Any]:
        """Delete one persisted history record without touching output files."""
        cleaned = self._clean([item] if isinstance(item, dict) else [])
        if not cleaned:
            return {"ok": False, "error": "Missing download history item", "code": "GUI003"}
        key = self._identity(cleaned[0])
        if not key:
            return {
                "ok": False,
                "error": "Missing download history item identity",
                "code": "GUI003",
            }
        keys = self._identity_candidates(cleaned[0], include_legacy=True)
        deleted = set(self._get_deleted_keys())
        deleted.update(keys)
        self._set_deleted_keys(deleted)
        self._set_items(
            [row for row in self._get_items() if not (self._identity_candidates(row) & keys)]
        )
        self._save_state()
        return self.get_archive()

    def _status_logs(self, status: dict[str, Any]) -> list[str]:
        formatter = self._helpers["format_status_log_entry"]
        return [
            formatter(entry)
            for entry in (status.get("log") or [])
            if isinstance(entry, dict) and entry.get("detail")
        ]

    def _clean(self, value: Any) -> list[dict[str, Any]]:
        return self._helpers["clean_download_archive"](value)

    def _filter_deleted(
        self,
        items: list[dict[str, Any]],
        deleted_keys: set[str],
    ) -> list[dict[str, Any]]:
        return self._helpers["filter_deleted_download_archive"](items, deleted_keys)

    def _dedupe(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._helpers["dedupe_download_archive"](items)

    def _merge(
        self,
        incoming: list[dict[str, Any]],
        existing: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._helpers["merge_download_archive"](incoming, existing)

    def _identity(self, item: dict[str, Any]) -> str:
        return self._helpers["download_archive_identity"](item)

    def _identity_candidates(
        self,
        item: dict[str, Any],
        *,
        include_legacy: bool = False,
    ) -> set[str]:
        return self._helpers["download_archive_identity_candidates"](
            item,
            include_legacy=include_legacy,
        )

    def _normalise_path(self, value: object) -> str:
        return self._helpers["normalise_download_archive_path"](value)

    def _clean_scene_rows(self, value: Any) -> list[dict[str, Any]]:
        return self._helpers["clean_archive_scene_rows"](value)

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        return self._helpers["coerce_bool"](value, default)
