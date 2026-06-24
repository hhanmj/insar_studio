"""End-to-end tests for the ``convert-dem`` CLI.

``--plan-only`` is fully offline. The real conversion path is exercised both with
a monkeypatched runner (no rasterio needed) and, when rasterio is available, with
a genuine GeoTIFF round-trip. No network is ever used.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

import insar_prep.cli.commands as commands
from insar_prep.cli.main import main

_BBOX = ["--bbox", "10.0", "45.5", "10.5", "46.0"]


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_convert_dem_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["convert-dem", "--help"])
    assert exc.value.code == 0


def test_plan_only_is_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        [
            "convert-dem",
            "--region-name",
            "Demo Area",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "COP30",
            "--plan-only",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "DEM conversion plan" in out
    assert "EGM2008 -> WGS84_ELLIPSOID" in out
    assert "Plan only" in out
    assert not list(tmp_path.rglob("*.tif"))


def test_missing_aoi_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["convert-dem", "--region-name", "demo", "--output-root", str(tmp_path)])
    assert code == 2
    assert "AOI001" in capsys.readouterr().err


def test_user_local_auto_datum_unknown_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "convert-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "USER_LOCAL",
            "--plan-only",
        ]
    )
    assert code == 2
    assert "DEM002" in capsys.readouterr().err


def test_real_conversion_requires_convert_extra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_find_spec = importlib.util.find_spec

    def _no_rasterio(name: str, *args: object, **kwargs: object) -> object:
        if name == "rasterio":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(commands.importlib.util, "find_spec", _no_rasterio)
    code = main(
        [
            "convert-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "COP30",
        ]
    )
    assert code == 2
    assert "DEM003" in capsys.readouterr().err


def test_real_path_uses_runner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _Summary:
        results_path = tmp_path / "dem_convert" / "dem_convert_results.csv"
        has_failures = False
        results: list[object] = []

        def summary_line(self) -> str:
            return "1 converted, 0 copied, 0 skipped, 0 failed"

    def _fake_run(plans, output_dir, **kwargs):  # noqa: ANN001, ANN003
        captured["plans"] = list(plans)
        captured["geoid_grid_path"] = kwargs.get("geoid_grid_path")
        return _Summary()

    monkeypatch.setattr(commands, "run_dem_conversion", _fake_run)
    code = main(
        [
            "convert-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "SRTM_GL1",
        ]
    )
    assert code == 0
    assert len(captured["plans"]) == 1
    assert "DEM conversion finished" in capsys.readouterr().out


def test_real_conversion_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("rasterio")
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    raw = tmp_path / "demo" / "04_dem" / "raw" / "demo_srtm_gl1_raw.tif"
    raw.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        raw,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(4326),
        transform=from_origin(9.95, 46.05, 0.25, 0.25),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.full((4, 4), 50.0, dtype=np.float32), 1)

    code = main(
        [
            "convert-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "SRTM_GL1",
        ]
    )
    assert code == 0, capsys.readouterr().err
    ready = tmp_path / "demo" / "06_sarscape_ready" / "demo_dem.tif"
    assert ready.is_file()
    results_csv = tmp_path / "dem_convert" / "dem_convert_results.csv"
    assert results_csv.is_file()
    with rasterio.open(ready) as src:
        assert src.read(1).mean() != pytest.approx(50.0)  # geoid offset was applied
