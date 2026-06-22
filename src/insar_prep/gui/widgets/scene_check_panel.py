"""Centre panel: run the scene consistency check and show results (Task 041).

Runs the existing core scene consistency check over the current Region's scenes
and displays a structured result (total scenes, error/warning counts, and the
issue list). The panel holds no checking logic of its own: it only calls
:func:`insar_prep.quality.scene_checks.check_scene_collection` and formats the
returned :class:`~insar_prep.quality.types.SceneCheckReport` for display. No
network, no downloads.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep.core.enums import Polarization
from insar_prep.core.models import Scene
from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.quality.types import CheckSeverity, SceneCheckReport

_ANY_POLARIZATION = "(any)"


class SceneCheckPanel(QGroupBox):
    """Run the core scene consistency check and present its report."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Scene consistency check", parent)
        self.setObjectName("scene_check_panel")

        self.polarization_combo = QComboBox()
        self.polarization_combo.setObjectName("scene_check_polarization")
        self.polarization_combo.addItem(_ANY_POLARIZATION, None)
        for member in Polarization:
            self.polarization_combo.addItem(member.value, member.value)

        self.run_button = QPushButton("Run scene check")
        self.run_button.setObjectName("scene_check_run_button")

        self.total_label = QLabel("Total scenes: -")
        self.total_label.setObjectName("scene_check_total")
        self.errors_label = QLabel("Errors: -")
        self.errors_label.setObjectName("scene_check_errors")
        self.warnings_label = QLabel("Warnings: -")
        self.warnings_label.setObjectName("scene_check_warnings")

        self.issues_list = QListWidget()
        self.issues_list.setObjectName("scene_check_issues")

        form = QFormLayout()
        form.addRow("Expected polarization:", self.polarization_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.run_button)
        layout.addWidget(self.total_label)
        layout.addWidget(self.errors_label)
        layout.addWidget(self.warnings_label)
        layout.addWidget(self.issues_list)

    def expected_polarization(self) -> Polarization | None:
        """Return the selected expected polarization, or ``None`` for ``(any)``."""
        data = self.polarization_combo.currentData()
        return Polarization(data) if data else None

    def run_check(self, scenes: list[Scene]) -> SceneCheckReport:
        """Run the core scene check over ``scenes`` and display the report."""
        report = check_scene_collection(scenes, expected_polarization=self.expected_polarization())
        self.set_report(report)
        return report

    def set_report(self, report: SceneCheckReport) -> None:
        """Populate the result widgets from a scene-check report."""
        errors = _count(report, CheckSeverity.ERROR)
        warnings = _count(report, CheckSeverity.WARNING)
        self.total_label.setText(f"Total scenes: {report.total_scenes}")
        self.errors_label.setText(f"Errors: {errors}")
        self.warnings_label.setText(f"Warnings: {warnings}")
        self.issues_list.clear()
        for issue in report.issues:
            label = f"[{issue.severity.value}] {issue.code}"
            if issue.scene_id:
                label += f" ({issue.scene_id})"
            self.issues_list.addItem(f"{label}: {issue.message}")


def _count(report: SceneCheckReport, severity: CheckSeverity) -> int:
    return sum(1 for issue in report.issues if issue.severity is severity)
