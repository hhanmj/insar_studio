"""Structured logging events (manual sections 17.3 and 17.4).

An :class:`Event` is a machine-readable record serialized as one JSON object per
line in ``events.jsonl``. Timestamps are UTC, ISO 8601 with a trailing ``Z``.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_serializer

from insar_prep.core.models import InsarBaseModel


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def generate_event_id() -> str:
    """Return a unique event identifier such as ``EVT-a1b2c3d4e5f6``."""
    return f"EVT-{secrets.token_hex(6)}"


class EventType(StrEnum):
    """Machine-readable event types (manual section 17.4)."""

    APP_STARTED = "APP_STARTED"
    WORKSPACE_CREATED = "WORKSPACE_CREATED"
    PROJECT_CREATED = "PROJECT_CREATED"
    REGION_CREATED = "REGION_CREATED"
    PROJECT_OPENED = "PROJECT_OPENED"
    AOI_IMPORTED = "AOI_IMPORTED"
    AOI_VALIDATED = "AOI_VALIDATED"
    ASF_CART_IMPORTED = "ASF_CART_IMPORTED"
    ASF_SEARCH_STARTED = "ASF_SEARCH_STARTED"
    ASF_SEARCH_FINISHED = "ASF_SEARCH_FINISHED"
    SCENE_VALIDATION_STARTED = "SCENE_VALIDATION_STARTED"
    SCENE_VALIDATION_FINISHED = "SCENE_VALIDATION_FINISHED"
    DOWNLOAD_STARTED = "DOWNLOAD_STARTED"
    DOWNLOAD_PROGRESS = "DOWNLOAD_PROGRESS"
    DOWNLOAD_FINISHED = "DOWNLOAD_FINISHED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    FILE_CHECK_STARTED = "FILE_CHECK_STARTED"
    FILE_CHECK_FINISHED = "FILE_CHECK_FINISHED"
    ORBIT_MATCH_STARTED = "ORBIT_MATCH_STARTED"
    ORBIT_MATCH_FINISHED = "ORBIT_MATCH_FINISHED"
    DEM_DOWNLOAD_STARTED = "DEM_DOWNLOAD_STARTED"
    DEM_DOWNLOAD_FINISHED = "DEM_DOWNLOAD_FINISHED"
    DEM_VERTICAL_CONVERSION_STARTED = "DEM_VERTICAL_CONVERSION_STARTED"
    DEM_VERTICAL_CONVERSION_FINISHED = "DEM_VERTICAL_CONVERSION_FINISHED"
    SARSCAPE_DEM_RENAMED = "SARSCAPE_DEM_RENAMED"
    GACOS_BATCH_CREATED = "GACOS_BATCH_CREATED"
    GACOS_PRODUCTS_IMPORTED = "GACOS_PRODUCTS_IMPORTED"
    REPORT_GENERATED = "REPORT_GENERATED"
    APP_ERROR = "APP_ERROR"


class Event(InsarBaseModel):
    """A structured log event (one JSON object per line in ``events.jsonl``)."""

    timestamp: datetime = Field(default_factory=_utcnow)
    event_id: str = Field(default_factory=generate_event_id)
    workspace_id: str | None = None
    project_id: str | None = None
    region_id: str | None = None
    module: str = ""
    event_type: EventType
    level: str = "INFO"
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("timestamp")
    def _serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
