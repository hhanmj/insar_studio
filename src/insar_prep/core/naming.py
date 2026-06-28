"""SARscape-safe naming utilities (Task 003).

Pure string/path helpers only: no DEM download, no DEM conversion, and no
SARscape execution. The canonical safe-name pattern is kept in sync with
``insar_prep.core.models.SAFE_NAME_PATTERN``.
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical SARscape-safe snake_case pattern: lowercase letters/digits with
# single underscores between groups; no leading/trailing/double underscores.
# Must stay in sync with insar_prep.core.models.SAFE_NAME_PATTERN.
SAFE_NAME_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"

# The SARscape-ready output directory name (manual section 5.4).
SARSCAPE_READY_DIR = "06_sarscape_ready"

_SAFE_NAME_RE = re.compile(SAFE_NAME_PATTERN)
_NON_SAFE_RUN_RE = re.compile(r"[^a-z0-9]+")
_ALLOWED_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.]+$")


def sarscape_safe_name(value: str) -> str:
    """Convert an arbitrary string into a SARscape-safe snake_case name.

    Lowercases the input, replaces every run of disallowed characters (spaces,
    hyphens, punctuation, symbols, CJK characters, etc.) with a single
    underscore, and strips leading/trailing underscores. Raises ``ValueError``
    if no safe name can be derived (e.g. empty or all-symbol input).
    """
    lowered = value.lower()
    replaced = _NON_SAFE_RUN_RE.sub("_", lowered)
    cleaned = replaced.strip("_")
    if not cleaned:
        msg = f"cannot derive a SARscape-safe name from {value!r}"
        raise ValueError(msg)
    if not _SAFE_NAME_RE.fullmatch(cleaned):  # safety net; should not happen
        msg = f"derived name {cleaned!r} is not SARscape-safe"
        raise ValueError(msg)
    return cleaned


def is_sarscape_safe_name(value: str) -> bool:
    """Return True if ``value`` is already a SARscape-safe snake_case name."""
    return _SAFE_NAME_RE.fullmatch(value) is not None


def validate_sarscape_ready_path(path: str | Path) -> None:
    """Validate that a SARscape-ready path uses only safe components.

    Each relevant component must not contain whitespace, hyphens, or special
    symbols (only letters, digits, underscores, and dots are allowed). When the
    path contains the ``06_sarscape_ready`` segment, only that segment onward is
    checked (parent directories outside the SARscape-ready tree are ignored);
    otherwise every component is checked. The drive/root anchor is always
    ignored. Raises ``ValueError`` on the first offending component.
    """
    p = Path(path)
    parts = list(p.parts)
    if p.anchor and parts and parts[0] == p.anchor:
        parts = parts[1:]
    if SARSCAPE_READY_DIR in parts:
        parts = parts[parts.index(SARSCAPE_READY_DIR) :]
    else:
        parts = parts[-1:]
    for part in parts:
        if any(ch.isspace() for ch in part):
            msg = f"SARscape-ready path component {part!r} must not contain whitespace"
            raise ValueError(msg)
        if "-" in part:
            msg = f"SARscape-ready path component {part!r} must not contain hyphens"
            raise ValueError(msg)
        if not _ALLOWED_PATH_COMPONENT_RE.fullmatch(part):
            msg = f"SARscape-ready path component {part!r} has illegal characters"
            raise ValueError(msg)
