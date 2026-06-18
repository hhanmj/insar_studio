"""Data structures for data-preparation reports (Task 014).

All models are JSON-serializable via the shared pydantic base model. The report
backend is offline and output-format agnostic: it produces structured data plus
Markdown only (no GUI, no PDF, no HTML, no network).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from insar_prep.core.models import InsarBaseModel, generate_id
from insar_prep.quality.types import CheckSeverity


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class ReportStatus(StrEnum):
    """Overall / per-section readiness state."""

    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    BLOCKED = "blocked"
    NOT_AVAILABLE = "not_available"


class ReportIssue(InsarBaseModel):
    """A single issue surfaced in a report, normalized across modules."""

    section: str = ""
    code: str
    severity: CheckSeverity
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ReportSection(InsarBaseModel):
    """One section of a data-preparation report (one module's outcome)."""

    title: str
    status: ReportStatus = ReportStatus.NOT_AVAILABLE
    summary: dict[str, Any] = Field(default_factory=dict)
    items: list[str] = Field(default_factory=list)
    issues: list[ReportIssue] = Field(default_factory=list)


class DataPreparationReport(InsarBaseModel):
    """A consolidated, offline data-preparation report for one region."""

    report_id: str = Field(default_factory=lambda: generate_id("report"))
    workspace_id: str | None = None
    project_id: str | None = None
    region_id: str
    region_safe_name: str
    created_at: datetime = Field(default_factory=_utcnow)
    title: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)


class ReportOutput(InsarBaseModel):
    """Paths written by :func:`save_report`."""

    json_path: Path
    markdown_path: Path
    written_files: list[Path] = Field(default_factory=list)
