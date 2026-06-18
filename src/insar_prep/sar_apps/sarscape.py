"""SARscape adapter helpers (Task 003).

Naming and path helpers for SARscape-ready outputs only: no DEM download, no DEM
vertical-datum conversion, and no SARscape execution. ISCE/MintPy adapters are
intentionally not implemented here.
"""

from __future__ import annotations

from pathlib import Path

from insar_prep.core.naming import (
    SARSCAPE_READY_DIR,
    is_sarscape_safe_name,
    validate_sarscape_ready_path,
)

# SARscape only recognizes ellipsoid-converted DEMs whose names end with _dem.
SARSCAPE_DEM_SUFFIX = "_dem"
# Category subdirectory for DEMs inside the SARscape-ready tree (manual 5.4).
SARSCAPE_DEM_SUBDIR = "DEM"


def ensure_sarscape_dem_name(region_safe_name: str, suffix: str = ".tif") -> str:
    """Return the SARscape-ready DEM filename for a region.

    ``shiliushubao`` -> ``shiliushubao_dem.tif`` and ``guangdong_2024`` ->
    ``guangdong_2024_dem.tif``. The input must already be a SARscape-safe name.
    The result always ends with ``_dem<suffix>`` and is never an ``*_ellipsoid``
    file. Raises ``ValueError`` on unsafe input or an invalid suffix.
    """
    if not is_sarscape_safe_name(region_safe_name):
        msg = f"{region_safe_name!r} is not SARscape-safe; use sarscape_safe_name() first"
        raise ValueError(msg)
    if not suffix.startswith("."):
        msg = f"suffix {suffix!r} must start with '.'"
        raise ValueError(msg)
    name = f"{region_safe_name}{SARSCAPE_DEM_SUFFIX}{suffix}"
    if name.endswith("_ellipsoid.tif"):
        msg = "SARscape-ready DEM must not be an *_ellipsoid.tif file"
        raise ValueError(msg)
    return name


def sarscape_ready_dem_path(
    region_safe_name: str,
    base_dir: str | Path = SARSCAPE_READY_DIR,
) -> Path:
    """Build and validate the SARscape-ready DEM path for a region."""
    dem_name = ensure_sarscape_dem_name(region_safe_name)
    path = Path(base_dir) / SARSCAPE_DEM_SUBDIR / dem_name
    validate_sarscape_ready_path(path)
    return path
