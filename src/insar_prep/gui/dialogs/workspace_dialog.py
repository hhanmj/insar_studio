"""Dialog to collect a new Workspace name and root path (Task 038)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class WorkspaceDialog(QDialog):
    """Collect a workspace display name and (logical) root path."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Workspace")
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("workspace_name_edit")
        self._root_edit = QLineEdit()
        self._root_edit.setObjectName("workspace_root_edit")

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Root path:", self._root_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def workspace_name(self) -> str:
        return self._name_edit.text().strip()

    def workspace_root(self) -> str:
        return self._root_edit.text().strip()
