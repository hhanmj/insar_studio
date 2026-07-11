"""PyInstaller entry point for the pywebview desktop app.

A thin, package-external launcher used only for freezing the **windowed** desktop
executable (the modern web UI hosted in a native WebView2 window). Freezing a
module that lives *inside* the ``insar_prep`` package as a top-level script can
cause double-import / relative-path edge cases; this external entry imports the
installed package and delegates to it instead.

With no arguments it opens the native desktop window. With ``--selftest`` it
verifies the bundled web assets resolve and exercises the in-process core
end-to-end (workspace -> AOI -> scenes -> DEM plan/convert -> report) **without**
opening a window or touching the network, then exits 0. This proves a frozen
build bundled every lazy dependency (shapely, the ASF/DEM/GACOS providers, the
reporting stack) and the ``ui/dist`` web assets.

Because the exe is windowed (no console), a self-test failure is written to
``%TEMP%/insar_desktop_selftest.log`` and surfaced via a non-zero exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DLL_DIR_HANDLES: list[object] = []


def _activate_bundled_gdal_runtime() -> None:
    """Point GDAL/PROJ at data directories bundled by the PyInstaller build."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    import os

    root = Path(meipass)
    if hasattr(os, "add_dll_directory"):
        handle = os.add_dll_directory(str(root))
        _DLL_DIR_HANDLES.append(handle)

    gdal_data = root / "gdal_data"
    proj_data = root / "proj_data"
    if gdal_data.exists():
        os.environ["GDAL_DATA"] = str(gdal_data)
    if proj_data.exists():
        os.environ["PROJ_LIB"] = str(proj_data)
        os.environ["PROJ_DATA"] = str(proj_data)


def _selftest() -> int:
    import os
    import tempfile
    import traceback

    try:
        _activate_bundled_gdal_runtime()
        from insar_prep.desktop.api import Api
        from insar_prep.desktop.app import resolve_url

        url = resolve_url()
        if not url.startswith("http") and not Path(url).exists():
            raise RuntimeError(f"bundled web index not found: {url}")

        with tempfile.TemporaryDirectory() as tmp:
            previous_localappdata = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = str(Path(tmp) / "localappdata")
            try:
                api = Api()
            finally:
                if previous_localappdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_localappdata

            if not api.get_app_info().get("ok"):
                raise RuntimeError("get_app_info failed")
            admin_options = api.get_admin_options()
            if not admin_options.get("ok"):
                raise RuntimeError(f"admin boundary API failed: {admin_options}")

            def check(label: str, result: dict) -> None:
                if not result.get("ok"):
                    raise RuntimeError(f"{label} failed: {result}")

            check("create_workspace", api.create_workspace(tmp, "selftest"))
            check("add_project", api.add_project("p"))
            check("add_region", api.add_region("r"))
            check("set_region_aoi_bbox", api.set_region_aoi_bbox(110.22, 110.52, 30.92, 31.14))
            check(
                "import_scenes_text",
                api.import_scenes_text(
                    "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C"
                ),
            )
            check("check_scenes", api.check_scenes())
            check("plan_asf_download", api.plan_asf_download())
            check("plan_dem_download", api.plan_dem_download())
            check("plan_dem_conversion", api.plan_dem_conversion())
            check("generate_report", api.generate_report())

            if os.environ.get("INSAR_SELFTEST_SKIP_RASTERIO") != "1":
                import numpy as np
                import pyproj
                import rasterio
                from rasterio.transform import from_origin

                crs = pyproj.CRS.from_epsg(4326)
                if crs.to_epsg() != 4326:
                    raise RuntimeError(f"pyproj CRS check failed: {crs}")
                raster_path = Path(tmp) / "selftest_dem.tif"
                with rasterio.open(
                    raster_path,
                    "w",
                    driver="GTiff",
                    height=2,
                    width=2,
                    count=1,
                    dtype="float32",
                    crs="EPSG:4326",
                    transform=from_origin(110.0, 31.0, 0.001, 0.001),
                ) as dataset:
                    dataset.write(np.ones((2, 2), dtype=np.float32), 1)
                with rasterio.open(raster_path) as dataset:
                    if dataset.crs is None or dataset.crs.to_epsg() != 4326:
                        raise RuntimeError(f"rasterio CRS check failed: {dataset.crs}")
                    data = dataset.read(1)
                    if data.shape != (2, 2):
                        raise RuntimeError(f"rasterio read shape check failed: {data.shape}")
    except Exception:  # noqa: BLE001 - windowed exe: persist the reason, fail loud
        log = Path(tempfile.gettempdir()) / "insar_desktop_selftest.log"
        try:
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        print(traceback.format_exc(), file=sys.stderr)  # noqa: T201
        return 3

    print("desktop selftest OK")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    _activate_bundled_gdal_runtime()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return _selftest()
    from insar_prep.desktop.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
