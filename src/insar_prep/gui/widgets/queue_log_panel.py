"""Right panel: task queue + log summary (Task 037).

Skeleton only: a read-only placeholder queue list and a read-only log view.
The real queue is driven by :mod:`insar_prep.queue` and the project logger in
later tasks; this widget holds no business logic and starts no tasks.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n


class QueueLogPanel(QWidget):
    """A placeholder task-queue list above a read-only log view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("queue_log_panel")
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)

        queue_container = QWidget()
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_title_label = QLabel(i18n.tr("queue.tasks"))
        queue_layout.addWidget(self.queue_title_label)
        self.queue_view = QListWidget()
        self.queue_view.setObjectName("queue_view")
        self.queue_view.addItem("(no tasks)")
        self.queue_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        queue_layout.addWidget(self.queue_view)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_title_label = QLabel(i18n.tr("queue.log"))
        log_layout.addWidget(self.log_title_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log_view")
        self.log_view.setReadOnly(True)
        self.log_view.setPlainText("(no log output)")
        log_layout.addWidget(self.log_view)

        splitter.addWidget(queue_container)
        splitter.addWidget(log_container)
        layout.addWidget(splitter)

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.queue_title_label.setText(i18n.tr("queue.tasks"))
        self.log_title_label.setText(i18n.tr("queue.log"))
