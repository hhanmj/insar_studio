"""Data structures for Sentinel-1 orbit parsing and matching (Task 009).

All models are JSON-serializable via the shared pydantic base model.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from insar_prep.core.enums import Platform
from insar_prep.core.models import InsarBaseModel
from insar_prep.quality.types import CheckSeverity


class OrbitType(StrEnum):
    """Sentinel-1 auxiliary orbit product types (manual section 13.1)."""

    POEORB = "POEORB"
    MOEORB = "MOEORB"
    RESORB = "RESORB"
    UNKNOWN = "UNKNOWN"


class OrbitFile(InsarBaseModel):
    """A parsed Sentinel-1 orbit (EOF) file."""

    file_name: str
    platform: Platform
    orbit_type: OrbitType
    creation_datetime: datetime
    validity_start: datetime
    validity_stop: datetime
    path: Path | None = None


class OrbitMatchIssue(InsarBaseModel):
    """A single orbit-matching finding."""

    code: str
    severity: CheckSeverity
    message: str
    scene_id: str | None = None
    orbit_file: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class OrbitMatchResult(InsarBaseModel):
    """The orbit-matching outcome for a single scene."""

    scene_id: str
    matched_orbit: OrbitFile | None = None
    candidate_orbits: list[OrbitFile] = Field(default_factory=list)
    issues: list[OrbitMatchIssue] = Field(default_factory=list)
    is_matched: bool = False


class OrbitMatchReport(InsarBaseModel):
    """The orbit-matching outcome for a collection of scenes."""

    total_scenes: int
    matched_scenes: int
    unmatched_scenes: int
    results: list[OrbitMatchResult] = Field(default_factory=list)
    issues: list[OrbitMatchIssue] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
