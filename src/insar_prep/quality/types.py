"""Data structures for quality checks (Task 007).

All models are JSON-serializable via the shared pydantic base model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from insar_prep.core.models import InsarBaseModel


class CheckSeverity(StrEnum):
    """Severity of a single quality-check issue."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CheckIssue(InsarBaseModel):
    """A single quality-check finding."""

    code: str
    severity: CheckSeverity
    message: str
    scene_id: str | None = None
    field: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SceneCheckReport(InsarBaseModel):
    """The result of checking a collection of scenes."""

    total_scenes: int
    valid_scenes: int
    issues: list[CheckIssue] = Field(default_factory=list)
    has_errors: bool = False
    has_warnings: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
