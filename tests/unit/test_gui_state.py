"""Tests for the GUI state (Task 038).

Headless: :mod:`insar_prep.gui.state` imports no PySide6, so these run without
the ``gui`` extra. No network, no disk persistence, no real data files.
"""

from __future__ import annotations

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.gui.state import GuiState, workspace_display_name
from insar_prep.processing.aoi import make_processing_aoi_from_bbox


def test_create_workspace_project_region() -> None:
    state = GuiState()
    workspace = state.create_workspace("C:/work", name="My Area")
    assert state.workspace is workspace
    assert workspace_display_name(workspace) == "My Area"

    project = state.add_project("Demo Project")
    assert project.safe_name == "demo_project"
    assert project.workspace_id == workspace.workspace_id
    assert state.current_project() is project

    region = state.add_region("Region One")
    assert region.region_safe_name == "region_one"
    assert region.project_id == project.project_id
    assert region.aoi is not None
    assert region.aoi.bbox is None
    assert state.current_region() is region
    assert workspace.projects[0].regions[0].region_id == region.region_id


def test_workspace_display_name_falls_back_to_root_name() -> None:
    state = GuiState()
    workspace = state.create_workspace("C:/work/myroot")
    assert workspace_display_name(workspace) == "myroot"


def test_create_project_without_workspace_errors() -> None:
    state = GuiState()
    with pytest.raises(InsarPrepError) as excinfo:
        state.add_project("Demo")
    assert excinfo.value.code == ErrorCode.GUI002


def test_create_region_without_project_errors() -> None:
    state = GuiState()
    state.create_workspace("C:/work")
    with pytest.raises(InsarPrepError) as excinfo:
        state.add_region("Region One")
    assert excinfo.value.code == ErrorCode.GUI002


def test_invalid_workspace_root_errors() -> None:
    state = GuiState()
    with pytest.raises(InsarPrepError) as excinfo:
        state.create_workspace("   ")
    assert excinfo.value.code == ErrorCode.GUI003


def test_underivable_name_errors() -> None:
    state = GuiState()
    state.create_workspace("C:/work")
    with pytest.raises(InsarPrepError) as excinfo:
        state.add_project("!!!")
    assert excinfo.value.code == ErrorCode.GUI003


def test_set_region_aoi_without_region_errors() -> None:
    state = GuiState()
    state.create_workspace("C:/work")
    state.add_project("p")
    aoi = make_processing_aoi_from_bbox(110.0, 111.0, 30.0, 31.0)
    with pytest.raises(InsarPrepError) as excinfo:
        state.set_current_region_aoi(aoi)
    assert excinfo.value.code == ErrorCode.GUI002


def test_set_region_aoi_success_binds_to_current_region() -> None:
    state = GuiState()
    state.create_workspace("C:/work")
    state.add_project("p")
    region = state.add_region("r")
    aoi = make_processing_aoi_from_bbox(110.0, 111.0, 30.0, 31.0)

    updated = state.set_current_region_aoi(aoi)
    assert updated.region_id == region.region_id
    assert updated.aoi.bbox is not None
    assert updated.aoi.bbox.east == 111.0
