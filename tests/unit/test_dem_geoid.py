"""Tests for the bundled EGM96 geoid grid loader and interpolation (Task 053).

Offline and numpy-only: no rasterio, no network. Validates that the committed
``egm96_15.npz`` is present, correctly georeferenced, and interpolated with
longitude wraparound.
"""

from __future__ import annotations

import numpy as np
import pytest

from insar_prep.core.exceptions import DemProcessingError
from insar_prep.providers.dem.geoid import GeoidGrid, load_bundled_geoid


def test_bundled_egm96_grid_metadata() -> None:
    grid = load_bundled_geoid("EGM96")
    assert grid.model == "EGM96"
    height, width = grid.shape
    assert (height, width) == (721, 1440)
    assert grid.lat0 == pytest.approx(90.0)
    assert grid.lon0 == pytest.approx(0.0)
    assert grid.dlat == pytest.approx(-0.25)
    assert grid.dlon == pytest.approx(0.25)
    # Global EGM96 undulation extrema.
    assert float(grid.undulation.min()) == pytest.approx(-106.99, abs=0.1)
    assert float(grid.undulation.max()) == pytest.approx(85.39, abs=0.1)


def test_grid_node_roundtrips_exactly() -> None:
    grid = load_bundled_geoid("EGM96")
    # The known global minimum sits at lat 4.75, lon 78.75 (Indian Ocean low).
    value = grid.undulation_at(4.75, 78.75)
    assert float(value) == pytest.approx(-106.99, abs=0.05)
    # ...and the maximum near Papua New Guinea.
    assert float(grid.undulation_at(-8.25, 147.25)) == pytest.approx(85.39, abs=0.05)


def test_longitude_wraps_at_360() -> None:
    grid = load_bundled_geoid("EGM96")
    for lat in (-40.0, 0.0, 12.5, 60.0):
        assert float(grid.undulation_at(lat, 0.0)) == pytest.approx(
            float(grid.undulation_at(lat, 360.0)), abs=1e-6
        )
        # Negative longitude normalizes into range.
        assert float(grid.undulation_at(lat, -10.0)) == pytest.approx(
            float(grid.undulation_at(lat, 350.0)), abs=1e-6
        )


def test_undulation_at_accepts_arrays_and_clamps_poles() -> None:
    grid = load_bundled_geoid("EGM96")
    lats = np.array([[10.0, 10.0], [-10.0, -10.0]])
    lons = np.array([[20.0, 200.0], [20.0, 200.0]])
    out = grid.undulation_at(lats, lons)
    assert out.shape == (2, 2)
    assert np.all(np.isfinite(out))
    # Poles must not index out of range.
    assert np.isfinite(float(grid.undulation_at(90.0, 0.0)))
    assert np.isfinite(float(grid.undulation_at(-90.0, 359.999)))


def test_load_bundled_geoid_unknown_model_raises() -> None:
    with pytest.raises(DemProcessingError):
        load_bundled_geoid("NOT_A_MODEL")


def test_geoid_grid_is_not_accidentally_hashed_on_construction() -> None:
    # eq=False keeps identity semantics so the ndarray field is never hashed.
    grid = GeoidGrid(
        undulation=np.zeros((2, 2), dtype=np.float32),
        lat0=90.0,
        lon0=0.0,
        dlat=-0.25,
        dlon=0.25,
        model="TEST",
    )
    assert grid == grid  # noqa: PLR0124 - identity check is intentional
