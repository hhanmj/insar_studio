"""In-memory GUI state for the insar-prep desktop GUI (Task 038).

A thin, PySide6-free layer that holds the current ``Workspace -> Project ->
Region`` hierarchy as **existing** core models (:mod:`insar_prep.core.models`)
and exposes create/select helpers for the GUI widgets to call. It contains no
Qt code (so it is fully testable headless) and no business logic of its own: it
only assembles core models, derives SARscape-safe names via
:func:`insar_prep.core.naming.sarscape_safe_name`, and raises
:class:`~insar_prep.core.exceptions.InsarPrepError` (with a stable error code)
when a precondition or input is invalid.

Nothing here is persisted to disk and no real data files are created; the
workspace/project/region roots are logical paths only.
"""

from __future__ import annotations

from pathlib import Path

from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError, InsarPrepError
from insar_prep.core.models import Aoi, Project, Region, Scene, Workspace
from insar_prep.core.naming import sarscape_safe_name

_DISPLAY_NAME_KEY = "display_name"


def _safe_name(value: str) -> str:
    """Return a SARscape-safe name, raising a coded GUI error on failure."""
    try:
        return sarscape_safe_name(value)
    except ValueError as exc:
        raise InputValidationError(str(exc), code=ErrorCode.GUI003) from exc


def workspace_display_name(workspace: Workspace) -> str:
    """Return a human-friendly label for a workspace (for the tree)."""
    name = workspace.global_settings.get(_DISPLAY_NAME_KEY)
    if isinstance(name, str) and name:
        return name
    return workspace.workspace_root.name or str(workspace.workspace_root)


class GuiState:
    """Holds the current workspace hierarchy and the active selections."""

    def __init__(self) -> None:
        self.workspace: Workspace | None = None
        self.current_project_id: str | None = None
        self.current_region_id: str | None = None

    def create_workspace(self, root: str | Path, name: str | None = None) -> Workspace:
        """Create the workspace from a (logical) root path and optional name."""
        root_text = str(root).strip()
        if not root_text:
            raise InputValidationError("workspace root path is required", code=ErrorCode.GUI003)
        settings = {}
        if name and name.strip():
            settings[_DISPLAY_NAME_KEY] = name.strip()
        workspace = Workspace(workspace_root=Path(root_text), global_settings=settings)
        self.workspace = workspace
        self.current_project_id = None
        self.current_region_id = None
        return workspace

    def add_project(self, name: str) -> Project:
        """Create a project under the workspace and make it current."""
        if self.workspace is None:
            raise InsarPrepError(
                "create a workspace before adding a project", code=ErrorCode.GUI002
            )
        safe = _safe_name(name)
        project = Project(
            workspace_id=self.workspace.workspace_id,
            project_name=name,
            safe_name=safe,
            project_root=self.workspace.workspace_root / safe,
        )
        self.workspace.projects.append(project)
        self.current_project_id = project.project_id
        self.current_region_id = None
        return project

    def add_region(self, name: str) -> Region:
        """Create a region under the current project and make it current.

        The region starts with a placeholder Processing AOI (no bbox); a real
        AOI is bound later (Task 039).
        """
        if self.workspace is None:
            raise InsarPrepError("create a workspace before adding a region", code=ErrorCode.GUI002)
        project = self.current_project()
        if project is None:
            raise InsarPrepError(
                "create or select a project before adding a region", code=ErrorCode.GUI002
            )
        safe = _safe_name(name)
        placeholder_aoi = Aoi(source=AoiSource.MANUAL_BBOX, role=AoiRole.PROCESSING_AOI, bbox=None)
        region = Region(
            project_id=project.project_id,
            region_name=name,
            region_safe_name=safe,
            region_root=project.project_root / safe,
            aoi=placeholder_aoi,
        )
        project.regions.append(region)
        self.current_region_id = region.region_id
        return region

    def select_project(self, project_id: str) -> Project:
        """Make an existing project current; clears the region selection."""
        project = self._find_project(project_id)
        if project is None:
            raise InsarPrepError(f"unknown project {project_id!r}", code=ErrorCode.GUI002)
        self.current_project_id = project_id
        self.current_region_id = None
        return project

    def select_region(self, region_id: str) -> Region:
        """Make an existing region current (and its parent project)."""
        if self.workspace is not None:
            for project in self.workspace.projects:
                for region in project.regions:
                    if region.region_id == region_id:
                        self.current_project_id = project.project_id
                        self.current_region_id = region_id
                        return region
        raise InsarPrepError(f"unknown region {region_id!r}", code=ErrorCode.GUI002)

    def current_project(self) -> Project | None:
        """Return the currently selected project, or ``None``."""
        if self.current_project_id is None:
            return None
        return self._find_project(self.current_project_id)

    def current_region(self) -> Region | None:
        """Return the currently selected region, or ``None``."""
        project = self.current_project()
        if project is None or self.current_region_id is None:
            return None
        for region in project.regions:
            if region.region_id == self.current_region_id:
                return region
        return None

    def set_current_region_aoi(self, aoi: Aoi) -> Region:
        """Bind an AOI to the current region (used by the AOI panel, Task 039)."""
        region = self.current_region()
        if region is None:
            raise InsarPrepError(
                "create or select a region before setting an AOI", code=ErrorCode.GUI002
            )
        region.aoi = aoi
        return region

    def set_current_region_scenes(self, scenes: list[Scene]) -> Region:
        """Store parsed scenes on the current region (used by Task 040)."""
        region = self.current_region()
        if region is None:
            raise InsarPrepError(
                "create or select a region before importing scenes", code=ErrorCode.GUI002
            )
        region.scenes = list(scenes)
        return region

    def _find_project(self, project_id: str) -> Project | None:
        if self.workspace is None:
            return None
        for project in self.workspace.projects:
            if project.project_id == project_id:
                return project
        return None
