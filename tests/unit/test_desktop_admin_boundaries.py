from __future__ import annotations

from pathlib import Path

from insar_prep.desktop.api import Api


def test_local_admin_options_include_city_and_county() -> None:
    api = Api()

    options = api.get_admin_options("内蒙古自治区", "包头市")

    assert options["ok"] is True
    assert "包头市" in options["cities"]
    assert "昆都仑区" in options["districts"]
    assert "达尔罕茂明安联合旗" in options["districts"]


def test_aoi_bind_auto_creates_default_region(tmp_path: Path, monkeypatch) -> None:
    api = Api()
    api._state.workspace = None
    api._state.current_project_id = None
    api._state.current_region_id = None
    api._state_path = tmp_path / "desktop_state.json"
    monkeypatch.setattr(api, "_default_workspace_root", lambda: tmp_path / "projects")

    result = api.set_region_aoi_bbox(109.0, 110.0, 40.0, 41.0)

    assert result["ok"] is True
    assert result["region_name"] == "default_area"
    context = api.get_context()
    assert context["region"]["has_aoi"] is True
    assert context["region"]["bbox"]["west"] == 109.0
