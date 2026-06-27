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

from insar_prep import i18n


class WorkspaceDialog(QDialog):
    """Collect a workspace display name and (logical) root path."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dlg.workspace.title"))
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("workspace_name_edit")
        self._root_edit = QLineEdit()
        self._root_edit.setObjectName("workspace_root_edit")

        form = QFormLayout()
        form.addRow(i18n.tr("common.name"), self._name_edit)
        form.addRow(i18n.tr("common.root_path"), self._root_edit)

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
