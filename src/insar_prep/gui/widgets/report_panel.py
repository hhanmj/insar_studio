"""Centre panel: generate the offline data-preparation report set (Task 043).

Produces the same five-file report set as the CLI ``prepare`` workflow for the
current Region — JSON, Markdown, HTML, ``manifest.csv`` and ``warnings.csv`` —
by reusing the existing reporting backend. The panel re-implements no reporting
logic and consolidates only the reports already produced by the other panels:

* :func:`build_data_preparation_report` + :func:`save_report` (JSON + Markdown),
* :func:`save_report_html` (self-contained static HTML),
* :func:`build_manifest_rows` + :func:`write_manifest_csv`,
* :func:`build_warning_rows` + :func:`write_warnings_csv`.

No SLC/DEM/GACOS data is downloaded or created and there is no network access;
only the report files are written under the user-supplied output root.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.core.models import Scene
from insar_prep.reporting.generator import build_data_preparation_report, save_report
from insar_prep.reporting.html import html_report_path_for, save_report_html
from insar_prep.reporting.manifest import (
    build_manifest_rows,
    manifest_path_for,
    write_manifest_csv,
)
from insar_prep.reporting.types import DataPreparationReport
from insar_prep.reporting.warnings import (
    build_warning_rows,
    warnings_path_for,
    write_warnings_csv,
)


class ReportPanel(QGroupBox):
    """Generate the offline five-file data-preparation report set."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Reports", parent)
        self.setObjectName("report_panel")

        self.output_root_edit = QLineEdit()
        self.output_root_edit.setObjectName("report_output_root")
        self.output_root_edit.setPlaceholderText("Workspace root for the report output")

        self.generate_button = QPushButton("Generate reports")
        self.generate_button.setObjectName("report_generate_button")

        self.result_label = QLabel("Reports: not generated")
        self.result_label.setObjectName("report_result")

        self.paths_view = QPlainTextEdit()
        self.paths_view.setObjectName("report_paths")
        self.paths_view.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Output root:", self.output_root_edit)

        generate_row = QHBoxLayout()
        generate_row.addStretch(1)
        generate_row.addWidget(self.generate_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(generate_row)
        layout.addWidget(self.result_label)
        layout.addWidget(self.paths_view)

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("report.title"))
        self.generate_button.setText(i18n.tr("report.generate"))

    def output_root(self) -> str:
        """Return the entered output root (stripped)."""
        return self.output_root_edit.text().strip()

    def generate(
        self,
        *,
        region_id: str,
        region_safe_name: str,
        scenes: list[Scene],
        output_root: Path | str,
        scene_check_report=None,
        orbit_match_report=None,
        dem_planning_report=None,
        dem_conversion_report=None,
        gacos_planning_report=None,
        gacos_import_report=None,
    ) -> tuple[DataPreparationReport, list[Path]]:
        """Build and write the five-file report set; return the report and paths."""
        report = build_data_preparation_report(
            region_id=region_id,
            region_safe_name=region_safe_name,
            scene_check_report=scene_check_report,
            orbit_match_report=orbit_match_report,
            dem_planning_report=dem_planning_report,
            dem_conversion_report=dem_conversion_report,
            gacos_planning_report=gacos_planning_report,
            gacos_import_report=gacos_import_report,
        )
        output = save_report(report, output_root)
        reports_dir = output.json_path.parent

        html_path = html_report_path_for(reports_dir, region_safe_name)
        save_report_html(report, html_path)

        manifest_path = manifest_path_for(reports_dir, region_safe_name)
        manifest_rows = build_manifest_rows(
            region_id=region_id,
            region_safe_name=region_safe_name,
            report=report,
            scenes=scenes,
            scene_check_report=scene_check_report,
            orbit_match_report=orbit_match_report,
            dem_planning_report=dem_planning_report,
            dem_conversion_report=dem_conversion_report,
            gacos_planning_report=gacos_planning_report,
            gacos_import_report=gacos_import_report,
            json_report_path=output.json_path,
            markdown_report_path=output.markdown_path,
            manifest_csv_path=manifest_path,
        )
        write_manifest_csv(manifest_path, manifest_rows)

        warnings_path = warnings_path_for(reports_dir, region_safe_name)
        warning_rows = build_warning_rows(
            region_safe_name=region_safe_name,
            scene_check_report=scene_check_report,
            orbit_match_report=orbit_match_report,
            dem_planning_report=dem_planning_report,
            dem_conversion_report=dem_conversion_report,
            gacos_planning_report=gacos_planning_report,
            gacos_import_report=gacos_import_report,
        )
        write_warnings_csv(warnings_path, warning_rows)

        paths = [
            output.json_path,
            output.markdown_path,
            html_path,
            manifest_path,
            warnings_path,
        ]
        self.set_result(report, paths)
        return report, paths

    def set_result(self, report: DataPreparationReport, paths: list[Path]) -> None:
        """Show the generated report status and output paths."""
        status = report.summary.get("overall_status", "-")
        self.result_label.setText(f"Reports generated ({len(paths)} files); status: {status}")
        self.paths_view.setPlainText("\n".join(str(path) for path in paths))
