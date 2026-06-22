"""Centre panel: the Region workflow steps (Task 037).

Skeleton only: it lists the workflow steps as read-only placeholder items
(see :data:`insar_prep.gui.WORKFLOW_STEPS`). Each step is wired to the matching
``insar_prep`` core interface in later tasks; this widget holds no business logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from insar_prep.gui import WORKFLOW_STEPS


class WorkflowStepsWidget(QWidget):
    """A placeholder, read-only list of the Region workflow steps."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workflow_steps")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Workflow steps"))
        self.step_list = QListWidget()
        self.step_list.setObjectName("workflow_step_list")
        self.step_list.addItems(list(WORKFLOW_STEPS))
        self.step_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.step_list)
