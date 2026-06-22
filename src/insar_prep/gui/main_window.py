"""Main window for the insar-prep GUI (Task 037 skeleton, Task 038 tree binding).

Four-zone shell:

* left: Workspace / Project / Region tree (now backed by :class:`GuiState`);
* centre: Region workflow steps;
* right: task queue + log summary;
* bottom: warnings / errors status bar (starts as ``Ready``).

A toolbar adds *New Workspace / New Project / New Region* actions. The window
holds a :class:`GuiState` and only calls existing core interfaces through it; it
contains no business logic. Errors raised by the state carry an error code and
are shown in the bottom status bar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMainWindow, QSplitter, QToolBar, QWidget

from insar_prep.core.exceptions import InsarPrepError
from insar_prep.gui import WINDOW_TITLE
from insar_prep.gui.dialogs.project_dialog import ProjectDialog
from insar_prep.gui.dialogs.region_dialog import RegionDialog
from insar_prep.gui.dialogs.workspace_dialog import WorkspaceDialog
from insar_prep.gui.state import GuiState, workspace_display_name
from insar_prep.gui.widgets.project_tree import ProjectTreeWidget
from insar_prep.gui.widgets.queue_log_panel import QueueLogPanel
from insar_prep.gui.widgets.status_bar import StatusBarWidget
from insar_prep.gui.widgets.workflow_steps import WorkflowStepsWidget


class MainWindow(QMainWindow):
    """The insar-prep main window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.state = GuiState()

        self.project_tree = ProjectTreeWidget()
        self.workflow_steps = WorkflowStepsWidget()
        self.queue_log_panel = QueueLogPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.project_tree)
        splitter.addWidget(self.workflow_steps)
        splitter.addWidget(self.queue_log_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        self.setCentralWidget(splitter)

        self.status_bar_widget = StatusBarWidget()
        self.setStatusBar(self.status_bar_widget)

        self._build_toolbar()
        self.resize(1000, 640)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("main_toolbar")
        self.addToolBar(toolbar)

        new_workspace = QAction("New Workspace", self)
        new_workspace.triggered.connect(self._on_new_workspace)
        toolbar.addAction(new_workspace)

        new_project = QAction("New Project", self)
        new_project.triggered.connect(self._on_new_project)
        toolbar.addAction(new_project)

        new_region = QAction("New Region", self)
        new_region.triggered.connect(self._on_new_region)
        toolbar.addAction(new_region)

    # --- logic methods (testable without dialogs) -----------------------------

    def apply_new_workspace(self, root: str, name: str | None = None) -> bool:
        """Create a workspace from the given root/name; report via the status bar."""
        try:
            workspace = self.state.create_workspace(root, name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created workspace: {workspace_display_name(workspace)}")
        return True

    def apply_new_project(self, name: str) -> bool:
        """Create a project under the current workspace; report via the status bar."""
        try:
            project = self.state.add_project(name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created project: {project.project_name}")
        return True

    def apply_new_region(self, name: str) -> bool:
        """Create a region under the current project; report via the status bar."""
        try:
            region = self.state.add_region(name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created region: {region.region_name}")
        return True

    # --- dialog handlers ------------------------------------------------------

    def _on_new_workspace(self) -> None:
        dialog = WorkspaceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_workspace(dialog.workspace_root(), dialog.workspace_name())

    def _on_new_project(self) -> None:
        dialog = ProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_project(dialog.project_name())

    def _on_new_region(self) -> None:
        dialog = RegionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_region(dialog.region_name())
