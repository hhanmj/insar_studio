"""Main window for the insar-prep GUI skeleton (Task 037).

Builds the four-zone shell:

* left: Workspace / Project / Region tree;
* centre: Region workflow steps;
* right: task queue + log summary;
* bottom: warnings / errors status bar (starts as ``Ready``).

This is a read-only skeleton. It wires only placeholder widgets and holds no
business logic; later tasks connect each zone to the existing ``insar_prep``
core interfaces.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget

from insar_prep.gui import WINDOW_TITLE
from insar_prep.gui.widgets.project_tree import ProjectTreeWidget
from insar_prep.gui.widgets.queue_log_panel import QueueLogPanel
from insar_prep.gui.widgets.status_bar import StatusBarWidget
from insar_prep.gui.widgets.workflow_steps import WorkflowStepsWidget


class MainWindow(QMainWindow):
    """The insar-prep main window (skeleton)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)

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

        self.resize(1000, 640)
