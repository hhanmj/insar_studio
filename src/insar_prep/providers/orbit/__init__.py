"""Sentinel-1 orbit file parsing and matching (local only).

No network access, no orbit downloads, no credentials.
"""

from __future__ import annotations

from insar_prep.providers.orbit.orbit_matcher import (
    match_orbit_for_scene,
    match_orbits_for_scenes,
)
from insar_prep.providers.orbit.orbit_parser import parse_orbit_filename, scan_orbit_directory
from insar_prep.providers.orbit.downloader import (
    OrbitDownloadOutcome,
    OrbitDownloadResult,
    OrbitDownloadSummary,
    download_orbit_for_scene,
    download_orbits_for_scenes,
    poeorb_directory,
)
from insar_prep.providers.orbit.types import (
    OrbitFile,
    OrbitMatchIssue,
    OrbitMatchReport,
    OrbitMatchResult,
    OrbitType,
)

__all__ = [
    "OrbitFile",
    "OrbitDownloadOutcome",
    "OrbitDownloadResult",
    "OrbitDownloadSummary",
    "OrbitMatchIssue",
    "OrbitMatchReport",
    "OrbitMatchResult",
    "OrbitType",
    "match_orbit_for_scene",
    "match_orbits_for_scenes",
    "parse_orbit_filename",
    "scan_orbit_directory",
    "download_orbit_for_scene",
    "download_orbits_for_scenes",
    "poeorb_directory",
]
