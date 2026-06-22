"""Left panel: a read-only Workspace / Project / Region tree (Task 037).

Skeleton only: it shows a single placeholder hierarchy
(Workspace > Project > Region). Real workspace loading and editing wire to the
``insar_prep`` core models in later tasks; this widget holds no business logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget


class ProjectTreeWidget(QTreeWidget):
    """A placeholder Workspace / Project / Region tree."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("project_tree")
        self.setHeaderLabel("Workspace")
        self._build_placeholder_items()
        self.expandAll()

    def _build_placeholder_items(self) -> None:
        workspace_item = QTreeWidgetItem(["Workspace"])
        project_item = QTreeWidgetItem(["Project"])
        region_item = QTreeWidgetItem(["Region"])
        project_item.addChild(region_item)
        workspace_item.addChild(project_item)
        self.addTopLevelItem(workspace_item)
