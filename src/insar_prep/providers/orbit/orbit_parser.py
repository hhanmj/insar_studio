"""Sentinel-1 orbit (EOF) filename parsing and directory scanning (Task 009).

Parses orbit EOF filenames locally; it never downloads orbits or reads file
contents. Invalid single filenames raise ``OrbitMatchingError``; directory scans
skip invalid files and log a warning instead of failing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from insar_prep.core.enums import Platform
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import OrbitMatchingError
from insar_prep.core.logging import get_logger
from insar_prep.providers.orbit.types import OrbitFile, OrbitType

logger = get_logger("providers.orbit.parser")

# e.g. S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T225942_20240103T005942.EOF
_ORBIT_RE = re.compile(
    r"^S1(?P<sat>[ABCD])_OPER_AUX_(?P<otype>POEORB|MOEORB|RESORB)_\w+_"
    r"(?P<creation>\d{8}T\d{6})_V(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})\.[Ee][Oo][Ff]$"
)


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)


def parse_orbit_filename(path: str | Path) -> OrbitFile:
    """Parse a Sentinel-1 orbit EOF filename into an :class:`OrbitFile`."""
    file_path = Path(path)
    name = file_path.name
    match = _ORBIT_RE.match(name)
    if match is None:
        raise OrbitMatchingError(f"invalid orbit filename: {name!r}", code=ErrorCode.ORB001)
    start = _parse_dt(match["start"])
    stop = _parse_dt(match["stop"])
    if stop <= start:
        raise OrbitMatchingError(
            f"orbit validity stop is not after start: {name!r}", code=ErrorCode.ORB001
        )
    return OrbitFile(
        file_name=name,
        platform=Platform(f"S1{match['sat']}"),
        orbit_type=OrbitType(match["otype"]),
        creation_datetime=_parse_dt(match["creation"]),
        validity_start=start,
        validity_stop=stop,
        path=file_path,
    )


def scan_orbit_directory(path: str | Path, recursive: bool = True) -> list[OrbitFile]:
    """Scan a directory for orbit EOF files, skipping invalid ones."""
    directory = Path(path)
    if not directory.exists():
        raise OrbitMatchingError(f"orbit directory not found: {directory}", code=ErrorCode.ORB001)
    pattern = "**/*" if recursive else "*"
    orbit_files: list[OrbitFile] = []
    for entry in sorted(directory.glob(pattern)):
        if entry.is_file() and entry.suffix.upper() == ".EOF":
            try:
                orbit_files.append(parse_orbit_filename(entry))
            except OrbitMatchingError:
                logger.warning("skipping invalid orbit file: %s", entry.name)
    logger.debug("scanned %s, found %d orbit files", directory, len(orbit_files))
    return orbit_files
