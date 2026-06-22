"""Dialog to collect a new Region name (Task 038)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class RegionDialog(QDialog):
    """Collect a region name (the SARscape-safe name is derived from it)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Region")
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("region_name_edit")

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def region_name(self) -> str:
        return self._name_edit.text().strip()
