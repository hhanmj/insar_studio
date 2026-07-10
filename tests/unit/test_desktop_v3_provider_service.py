from __future__ import annotations

from datetime import datetime
from pathlib import Path

from insar_prep.core.models import Scene
from insar_prep.desktop.api import Api
from insar_prep.desktop.v3_provider_service import V3ProviderDesktopService


def _api_with_region(tmp_path: Path, monkeypatch) -> Api:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()
    assert api.create_workspace(str(tmp_path / "workspace"), "demo")["ok"] is True
    assert api.add_project("project")["ok"] is True
    assert api.add_region("default area")["ok"] is True
    assert api.set_region_aoi_bbox(109.5, 117.5, 20.0, 25.5)["ok"] is True
    return api


def test_desktop_v3_service_injects_current_region_context(tmp_path: Path, monkeypatch) -> None:
    api = _api_with_region(tmp_path, monkeypatch)
    service = V3ProviderDesktopService(api._state)

    data = service.query_data("opentopography.dem", {"filters": {"dataset": "COP30"}})

    assert data["provider_id"] == "opentopography.dem"
    assert data["region_safe_name"] == "default_area"
    assert data["processing_aoi"].bbox.west == 109.5
    assert data["output_root"] == tmp_path / "workspace" / "project" / "default_area"
    assert data["filters"] == {"dataset": "COP30"}


def test_desktop_v3_service_plans_gacos_browser_submission_from_region(
    tmp_path: Path,
    monkeypatch,
) -> None:
    api = _api_with_region(tmp_path, monkeypatch)
    region = api._state.current_region()
    assert region is not None
    region.scenes = [
        Scene(acquisition_datetime=datetime(2024, 1, 1, 12, 0)),
        Scene(acquisition_datetime=datetime(2024, 1, 13, 12, 0)),
    ]
    service = V3ProviderDesktopService(api._state)

    plan = service.plan_provider("gacos.atmosphere", {"filters": {"hour": 18, "minute": 30}})

    assert plan.execution_mode == "browser_assisted_web_form"
    assert plan.output_root == tmp_path / "workspace" / "project" / "default_area"
    assert plan.submission["batches"][0]["form_fields"]["date"] == "20240101\n20240113"
    assert plan.submission["batches"][0]["form_fields"]["H"] == "18"
    assert plan.submission["batches"][0]["required_sensitive_fields"] == ["email"]
