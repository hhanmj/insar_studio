from __future__ import annotations

from datetime import datetime
from pathlib import Path

from insar_prep.core.models import Scene
from insar_prep.desktop.api import Api

_GRANULE = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
_URL = f"https://datapool.asf.alaska.edu/SLC/SA/{_GRANULE}.zip"


def test_desktop_v3_provider_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = Api().get_v3_providers()

    assert result["ok"] is True
    ids = {item["provider_id"] for item in result["providers"]}
    assert {"asf.sentinel1", "opentopography.dem", "gacos.atmosphere"} <= ids


def test_desktop_v3_unknown_provider_returns_coded_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = Api().v3_search_provider("missing.provider", {})

    assert result["ok"] is False
    assert result["code"] == "GUI003"
    assert "unknown provider" in result["error"]


def test_desktop_v3_dem_plan_without_aoi_returns_coded_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = Api().v3_plan_provider(
        "opentopography.dem",
        {"output_root": str(tmp_path / "dem"), "filters": {"dataset": "COP30"}},
    )

    assert result["ok"] is False
    assert result["code"] == "AOI001"
    assert "processing_aoi or bbox" in result["error"]


def test_desktop_v3_gacos_plan_with_empty_scenes_returns_coded_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    result = Api().v3_plan_provider(
        "gacos.atmosphere",
        {
            "bbox": {"west": 109.5, "east": 117.5, "south": 20.0, "north": 25.5},
            "scenes": [],
            "output_root": str(tmp_path / "gacos"),
        },
    )

    assert result["ok"] is False
    assert result["code"] == "GAC001"
    assert "at least one scene" in result["error"]


def test_desktop_v3_asf_search_and_plan_from_query(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    output_root = tmp_path / "out"

    search = api.v3_search_provider(
        "asf.sentinel1",
        {"filters": {"scene_sources": [_URL]}, "output_root": str(output_root)},
    )
    plan = api.v3_plan_provider(
        "asf.sentinel1",
        {"output_root": str(output_root)},
        search["products"],
    )

    assert search["ok"] is True
    assert search["products"][0]["product_id"] == _GRANULE
    assert plan["ok"] is True
    assert plan["plan"]["items"][0]["target_path"] == str(
        output_root / "SAR_Data" / "SLC" / f"{_GRANULE}.zip"
    )
    assert not (output_root / "SAR_Data").exists()


def test_desktop_v3_dem_plan_from_current_region(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    assert api.create_workspace(str(tmp_path / "workspace"), "demo")["ok"] is True
    assert api.add_project("project")["ok"] is True
    assert api.add_region("default area")["ok"] is True
    assert api.set_region_aoi_bbox(109.5, 117.5, 20.0, 25.5)["ok"] is True

    plan = api.v3_plan_provider(
        "opentopography.dem",
        {"filters": {"dataset": "COP30"}, "output_root": str(tmp_path / "dem")},
    )

    assert plan["ok"] is True
    assert plan["plan"]["legacy_plan"]["region_safe_name"] == "default_area"
    assert plan["plan"]["legacy_plan"]["dataset"] == "COP30"
    assert [item["properties"]["stage"] for item in plan["plan"]["items"]] == [
        "raw_dem",
        "ellipsoid_dem",
        "sarscape_ready_dem",
    ]


def test_desktop_v3_gacos_plan_from_current_region_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    assert api.create_workspace(str(tmp_path / "workspace"), "demo")["ok"] is True
    assert api.add_project("project")["ok"] is True
    assert api.add_region("default area")["ok"] is True
    assert api.set_region_aoi_bbox(109.5, 117.5, 20.0, 25.5)["ok"] is True
    region = api._state.current_region()
    assert region is not None
    region.scenes = [
        Scene(acquisition_datetime=datetime(2024, 1, 1, 12, 0)),
        Scene(acquisition_datetime=datetime(2024, 1, 13, 12, 0)),
    ]

    plan = api.v3_plan_provider("gacos.atmosphere", {"output_root": str(tmp_path / "gacos")})

    assert plan["ok"] is True
    assert plan["plan"]["manual_action_required"] is True
    assert plan["plan"]["execution_mode"] == "browser_assisted_web_form"
    assert plan["plan"]["submission"]["kind"] == "web_form_submission"
    assert plan["plan"]["submission"]["batches"][0]["form_fields"]["date"] == "20240101\n20240113"
    assert plan["plan"]["submission"]["batches"][0]["required_sensitive_fields"] == ["email"]
    assert len(plan["plan"]["items"]) == 2
    assert plan["plan"]["legacy_plan"]["scene_count"] == 2
    assert not (tmp_path / "gacos").exists()
