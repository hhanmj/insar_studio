"""Centre panel: a read-only table of imported scenes (Task 040).

Displays a list of :class:`~insar_prep.core.models.Scene` objects (as produced
by the core ASF cart parser) in a flat table. It holds no business logic: it
only formats already-parsed scene fields for display and never parses carts,
downloads data, or accesses the network.
"""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem, QWidget

from insar_prep.core.models import Scene

SCENE_TABLE_COLUMNS = (
    "Scene ID",
    "Platform",
    "Acquisition",
    "Product",
    "Beam",
    "Polarization",
    "URL",
)


class SceneTableWidget(QTableWidget):
    """A read-only table that mirrors a list of parsed scenes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scene_table")
        self.setColumnCount(len(SCENE_TABLE_COLUMNS))
        self.setHorizontalHeaderLabels(list(SCENE_TABLE_COLUMNS))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.verticalHeader().setVisible(False)

    def set_scenes(self, scenes: list[Scene]) -> None:
        """Rebuild the table rows from a list of parsed scenes."""
        self.setRowCount(len(scenes))
        for row, scene in enumerate(scenes):
            for column, value in enumerate(_scene_row(scene)):
                self.setItem(row, column, QTableWidgetItem(value))


def _scene_row(scene: Scene) -> tuple[str, str, str, str, str, str, str]:
    acquisition = (
        scene.acquisition_datetime.strftime("%Y-%m-%d %H:%M:%S")
        if scene.acquisition_datetime is not None
        else ""
    )
    return (
        scene.scene_id,
        scene.platform.value,
        acquisition,
        scene.product_type.value,
        scene.beam_mode.value,
        scene.polarization.value,
        "present" if scene.url else "missing",
    )
