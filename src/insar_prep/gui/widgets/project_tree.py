"""Left panel: the Workspace / Project / Region tree (Task 038).

Renders the hierarchy held by :class:`insar_prep.gui.state.GuiState`. Before a
workspace exists it shows a single ``Workspace`` placeholder. It holds no
business logic: it only reflects the state's existing core models.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from insar_prep.gui.state import GuiState, workspace_display_name


def _region_label(region_name: str, has_aoi: bool) -> str:
    return f"{region_name} [AOI set]" if has_aoi else region_name


class ProjectTreeWidget(QTreeWidget):
    """A Workspace / Project / Region tree backed by :class:`GuiState`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("project_tree")
        self.setHeaderLabel("Workspace")
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self.clear()
        self.addTopLevelItem(QTreeWidgetItem(["Workspace"]))

    def refresh_from_state(self, state: GuiState) -> None:
        """Rebuild the tree from the given GUI state."""
        workspace = state.workspace
        if workspace is None:
            self._show_placeholder()
            return
        self.clear()
        workspace_item = QTreeWidgetItem([workspace_display_name(workspace)])
        for project in workspace.projects:
            project_item = QTreeWidgetItem([project.project_name])
            for region in project.regions:
                has_aoi = region.aoi is not None and region.aoi.bbox is not None
                project_item.addChild(QTreeWidgetItem([_region_label(region.region_name, has_aoi)]))
            workspace_item.addChild(project_item)
        self.addTopLevelItem(workspace_item)
        self.expandAll()
