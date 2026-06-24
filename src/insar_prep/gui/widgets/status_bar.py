"""Bottom bar: warnings / errors summary (Task 037).

Skeleton only: a status bar that shows ``Ready`` initially. Later tasks push
real warning/error summaries here from the core check/report results; this
widget holds no business logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QStatusBar, QWidget

from insar_prep import i18n

READY_TEXT = "Ready"


class StatusBarWidget(QStatusBar):
    """A warnings/errors status bar; starts in the ``Ready`` state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("status_bar")
        self._is_ready = True
        self._label = QLabel(i18n.tr("status.ready"))
        self._label.setObjectName("status_label")
        self.addWidget(self._label)

    def set_status(self, text: str) -> None:
        """Set the status text (e.g. a warnings/errors summary)."""
        self._is_ready = False
        self._label.setText(text)

    def set_ready(self) -> None:
        """Reset to the translated ready state."""
        self._is_ready = True
        self._label.setText(i18n.tr("status.ready"))

    def status_text(self) -> str:
        """Return the current status text (used by tests)."""
        return self._label.text()

    def retranslate_ui(self) -> None:
        """Re-apply the ready text if the bar is currently in the ready state."""
        if self._is_ready:
            self._label.setText(i18n.tr("status.ready"))
