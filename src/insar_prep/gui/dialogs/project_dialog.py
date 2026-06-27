"""Dialog to collect a new Project name (Task 038)."""

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


class ProjectDialog(QDialog):
    """Collect a project name (the SARscape-safe name is derived from it)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dlg.project.title"))
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("project_name_edit")

        form = QFormLayout()
        form.addRow(i18n.tr("common.name"), self._name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def project_name(self) -> str:
        return self._name_edit.text().strip()
