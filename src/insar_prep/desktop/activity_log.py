"""In-session activity feed for the desktop overview (memory-only)."""

from __future__ import annotations

from datetime import UTC, datetime


class ActivityLog:
    """Ring buffer of user-visible actions in the current exe session."""

    def __init__(self, max_entries: int = 40) -> None:
        self._max = max_entries
        self._entries: list[dict] = []

    def add(self, text: str, *, kind: str = "info") -> None:
        self._entries.insert(
            0,
            {
                "ts": datetime.now(UTC).isoformat(),
                "text": text,
                "kind": kind,
            },
        )
        del self._entries[self._max :]

    def list(self, limit: int = 12) -> dict:
        return {"ok": True, "activities": self._entries[: max(1, limit)]}
