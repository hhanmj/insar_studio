"""EGM96 geoid-undulation grid loader and bilinear interpolation (Task 053).

The real DEM vertical-datum converter turns orthometric (EGM96/EGM2008) DEM
heights into WGS84 *ellipsoidal* heights using the geoid undulation

    N = ellipsoidal_height - orthometric_height        (so  h = H + N).

This module loads the small bundled EGM96 15-arc-minute grid
(``insar_prep/data/egm96_15.npz``, derived from the public-domain GeographicLib
``egm96-15`` grid; see ``THIRD_PARTY_REFERENCES.md``) and interpolates ``N`` at
arbitrary lon/lat. Only :mod:`numpy` is required (already present transitively via
shapely); rasterio is **not** needed here, so the grid can be queried in offline
unit tests without the ``convert`` extra.

The bundled grid runs north->south (row 0 = +90 deg lat) and west->east over
``lon = 0 .. 360`` with the wrap column omitted, so longitude is interpolated
with wraparound and latitude is clamped to the poles.
"""

from __future__ import annotations

import importlib.resources as resources
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import DemProcessingError
from insar_prep.core.logging import get_logger

logger = get_logger("providers.dem.geoid")

_DATA_PACKAGE = "insar_prep"
# Geoid model name -> path parts under the package data directory.
_BUNDLED_GEOIDS: dict[str, tuple[str, ...]] = {"EGM96": ("data", "egm96_15.npz")}


@dataclass(frozen=True, eq=False)
class GeoidGrid:
    """A regular lon/lat grid of geoid-undulation values (metres)."""

    undulation: np.ndarray  # shape (height, width); float
    lat0: float  # latitude of row 0 (degrees)
    lon0: float  # longitude of column 0 (degrees)
    dlat: float  # latitude step per row (negative: north -> south)
    dlon: float  # longitude step per column (positive)
    model: str

    @property
    def shape(self) -> tuple[int, int]:
        return self.undulation.shape  # type: ignore[return-value]

    def undulation_at(self, lat: np.ndarray | float, lon: np.ndarray | float) -> np.ndarray:
        """Bilinearly interpolate undulation N at ``lat``/``lon`` (degrees).

        ``lat`` and ``lon`` may be scalars or broadcastable arrays; the result has
        the broadcast shape. Longitude wraps at 360 deg; latitude is clamped to
        ``[-90, 90]``.
        """
        lat_arr = np.asarray(lat, dtype=np.float64)
        lon_arr = np.asarray(lon, dtype=np.float64)
        height, width = self.undulation.shape

        frow = (np.clip(lat_arr, -90.0, 90.0) - self.lat0) / self.dlat
        frow = np.clip(frow, 0.0, height - 1)
        row0 = np.floor(frow).astype(np.intp)
        row1 = np.minimum(row0 + 1, height - 1)
        wrow = frow - row0

        fcol = np.mod(lon_arr - self.lon0, 360.0) / self.dlon
        col0 = np.floor(fcol).astype(np.intp)
        wcol = fcol - col0
        col0 = np.mod(col0, width)
        col1 = np.mod(col0 + 1, width)

        grid = self.undulation
        top = grid[row0, col0] * (1.0 - wcol) + grid[row0, col1] * wcol
        bottom = grid[row1, col0] * (1.0 - wcol) + grid[row1, col1] * wcol
        return top * (1.0 - wrow) + bottom * wrow


def load_geoid_file(path: Path | str, *, model: str | None = None) -> GeoidGrid:
    """Load a geoid grid from a ``.npz`` produced by ``scripts/build_geoid_npz.py``."""
    with np.load(path, allow_pickle=False) as data:
        stored_model = str(data["model"]) if "model" in data.files else None
        return GeoidGrid(
            undulation=np.asarray(data["undulation"], dtype=np.float32),
            lat0=float(data["lat0"]),
            lon0=float(data["lon0"]),
            dlat=float(data["dlat"]),
            dlon=float(data["dlon"]),
            model=stored_model or model or "CUSTOM",
        )


@lru_cache(maxsize=4)
def load_bundled_geoid(model: str = "EGM96") -> GeoidGrid:
    """Load a bundled geoid grid by model name (cached). Raises on unknown model."""
    key = model.upper()
    parts = _BUNDLED_GEOIDS.get(key)
    if parts is None:
        available = ", ".join(sorted(_BUNDLED_GEOIDS))
        raise DemProcessingError(
            f"no bundled geoid grid for model {model!r}; available: {available}",
            code=ErrorCode.DEM003,
        )
    resource = resources.files(_DATA_PACKAGE).joinpath(*parts)
    with resources.as_file(resource) as grid_path:
        if not grid_path.is_file():  # pragma: no cover - packaging guard
            raise DemProcessingError(
                f"bundled geoid grid is missing: {grid_path}", code=ErrorCode.DEM003
            )
        logger.debug("loaded bundled geoid grid %s from %s", key, grid_path)
        return load_geoid_file(grid_path, model=key)
