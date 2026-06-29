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


def _selftest() -> int:
    import os
    import tempfile
    import traceback
    from pathlib import Path

    try:
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
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return _selftest()
    from insar_prep.desktop.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
