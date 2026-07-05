from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from insar_prep.desktop.api import Api


def _write_geotiff(path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110.0, 31.0, 0.01, 0.01),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.ones((2, 2), dtype=np.float32), 1)


def test_local_dem_plan_uses_source_name_and_avoids_existing_outputs(tmp_path: Path) -> None:
    api = Api()
    api._state_path = tmp_path / "desktop_state.json"
    assert api.create_workspace(str(tmp_path / "workspace"), "demo")["ok"] is True
    assert api.add_project("project")["ok"] is True
    assert api.add_region("default area")["ok"] is True

    source = tmp_path / "input" / "AW3D30m.tif"
    output = tmp_path / "out"
    _write_geotiff(source)
    output.mkdir()
    (output / "AW3D30m_ellipsoid.tif").write_bytes(b"old")
    (output / "AW3D30m_dem.hdr").write_text("old", encoding="utf-8")

    result = api.plan_local_dem_conversion(str(source), str(output), "WGS84_ELLIPSOID")

    assert result["ok"] is True
    plan = result["plan"]
    assert Path(plan["ellipsoid_dem_path"]).name == "AW3D30m_ellipsoid_2.tif"
    assert Path(plan["sarscape_ready_dem_path"]).name == "AW3D30m_dem_2"
    assert "default_area" not in Path(plan["ellipsoid_dem_path"]).name.lower()
