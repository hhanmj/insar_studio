"""Main window for the insar-prep GUI (Task 037 skeleton, Task 038 tree binding).

Four-zone shell:

* left: Workspace / Project / Region tree (now backed by :class:`GuiState`);
* centre: Region workflow steps;
* right: task queue + log summary;
* bottom: warnings / errors status bar (starts as ``Ready``).

A toolbar adds *New Workspace / New Project / New Region* actions. The window
holds a :class:`GuiState` and only calls existing core interfaces through it; it
contains no business logic. Errors raised by the state carry an error code and
are shown in the bottom status bar.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.models import Aoi, Scene
from insar_prep.gui import WINDOW_TITLE
from insar_prep.gui.dialogs.earthdata_login_dialog import EarthdataLoginDialog
from insar_prep.gui.dialogs.gacos_email_dialog import GacosEmailDialog
from insar_prep.gui.dialogs.opentopography_key_dialog import OpenTopographyKeyDialog
from insar_prep.gui.dialogs.project_dialog import ProjectDialog
from insar_prep.gui.dialogs.region_dialog import RegionDialog
from insar_prep.gui.dialogs.workspace_dialog import WorkspaceDialog
from insar_prep.gui.state import GuiState, workspace_display_name
from insar_prep.gui.widgets.aoi_panel import AoiPanel
from insar_prep.gui.widgets.asf_cart_panel import AsfCartPanel
from insar_prep.gui.widgets.dem_download_panel import DemDownloadPanel, DemDownloadWorker
from insar_prep.gui.widgets.download_panel import DownloadPanel, DownloadWorker
from insar_prep.gui.widgets.gacos_download_panel import (
    GacosDownloadPanel,
    GacosFetchWorker,
    GacosRequestWorker,
)
from insar_prep.gui.widgets.planning_panel import PlanningPanel
from insar_prep.gui.widgets.project_tree import ProjectTreeWidget
from insar_prep.gui.widgets.queue_log_panel import QueueLogPanel
from insar_prep.gui.widgets.report_panel import ReportPanel
from insar_prep.gui.widgets.scene_check_panel import SceneCheckPanel
from insar_prep.gui.widgets.scene_table import SceneTableWidget
from insar_prep.gui.widgets.status_bar import StatusBarWidget
from insar_prep.gui.widgets.workflow_steps import WorkflowStepsWidget
from insar_prep.providers.asf import (
    AsfDownloadPlan,
    DownloadRunSummary,
    resolve_credentials,
    run_asf_download,
)
from insar_prep.providers.dem import (
    DemConversionReport,
    DemDownloadRunSummary,
    DemKeySource,
    DemPlanningReport,
    DemRequestPlan,
    create_dem_request_plan,
    run_dem_download,
)
from insar_prep.providers.gacos import (
    GacosDownloadRunSummary,
    GacosImportCheckReport,
    GacosPlanningReport,
    GacosRequestRunSummary,
    extract_gacos_dates_from_scenes,
    run_gacos_download,
    run_gacos_request,
)
from insar_prep.providers.gacos.planner import GACOS_REQUESTS_SUBDIR
from insar_prep.providers.orbit import OrbitMatchReport
from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.quality.types import CheckSeverity, SceneCheckReport
from insar_prep.reporting.types import DataPreparationReport


class MainWindow(QMainWindow):
    """The insar-prep main window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.state = GuiState()

        # Most recent sub-reports produced by the workflow panels; consolidated by
        # the report panel. None until the matching step has been run.
        self.last_scene_report: SceneCheckReport | None = None
        self.last_orbit_report: OrbitMatchReport | None = None
        self.last_dem_planning_report: DemPlanningReport | None = None
        self.last_dem_conversion_report: DemConversionReport | None = None
        self.last_gacos_planning_report: GacosPlanningReport | None = None
        self.last_gacos_import_report: GacosImportCheckReport | None = None

        self.project_tree = ProjectTreeWidget()
        self.workflow_steps = WorkflowStepsWidget()
        self.aoi_panel = AoiPanel()
        self.aoi_panel.apply_button.clicked.connect(self._on_set_aoi)
        self.asf_cart_panel = AsfCartPanel()
        self.asf_cart_panel.import_button.clicked.connect(self._on_import_cart)
        self.scene_table = SceneTableWidget()
        self.scene_check_panel = SceneCheckPanel()
        self.scene_check_panel.run_button.clicked.connect(self._on_run_scene_check)
        self.planning_panel = PlanningPanel()
        self.planning_panel.orbit_button.clicked.connect(self._on_run_orbit_match)
        self.planning_panel.dem_button.clicked.connect(self._on_run_dem_plan)
        self.planning_panel.gacos_button.clicked.connect(self._on_run_gacos_plan)
        self.report_panel = ReportPanel()
        self.report_panel.generate_button.clicked.connect(self._on_generate_reports)
        self.download_panel = DownloadPanel()
        self.download_panel.download_button.clicked.connect(self._on_run_download)
        self.download_panel.cancel_button.clicked.connect(self._on_cancel_download)
        self.download_panel.login_button.clicked.connect(self._on_download_login)
        self._download_worker: DownloadWorker | None = None
        self.dem_download_panel = DemDownloadPanel()
        self.dem_download_panel.download_button.clicked.connect(self._on_run_dem_download)
        self.dem_download_panel.cancel_button.clicked.connect(self._on_cancel_dem_download)
        self.dem_download_panel.key_button.clicked.connect(self._on_dem_key_login)
        self._dem_download_worker: DemDownloadWorker | None = None
        self.gacos_download_panel = GacosDownloadPanel()
        self.gacos_download_panel.submit_button.clicked.connect(self._on_gacos_submit)
        self.gacos_download_panel.download_button.clicked.connect(self._on_gacos_fetch)
        self.gacos_download_panel.cancel_button.clicked.connect(self._on_cancel_gacos)
        self.gacos_download_panel.email_button.clicked.connect(self._on_gacos_email)
        self._gacos_request_worker: GacosRequestWorker | None = None
        self._gacos_fetch_worker: GacosFetchWorker | None = None
        self.queue_log_panel = QueueLogPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.project_tree)
        splitter.addWidget(self._build_centre())
        splitter.addWidget(self.queue_log_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        self.setCentralWidget(splitter)

        self.status_bar_widget = StatusBarWidget()
        self.setStatusBar(self.status_bar_widget)

        self._build_toolbar()
        self._build_menu_bar()
        self.retranslate_ui()
        self.resize(1000, 640)

    def _build_centre(self) -> QScrollArea:
        """Build the scrollable centre column (workflow steps + workflow panels)."""
        centre = QWidget()
        self.centre_layout = QVBoxLayout(centre)
        self.centre_layout.addWidget(self.workflow_steps)
        self.centre_layout.addWidget(self.aoi_panel)
        self.centre_layout.addWidget(self.asf_cart_panel)
        self.centre_layout.addWidget(self.scene_table)
        self.centre_layout.addWidget(self.scene_check_panel)
        self.centre_layout.addWidget(self.planning_panel)
        self.centre_layout.addWidget(self.report_panel)
        self.centre_layout.addWidget(self.download_panel)
        self.centre_layout.addWidget(self.dem_download_panel)
        self.centre_layout.addWidget(self.gacos_download_panel)
        self.centre_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("centre_scroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(centre)
        return scroll

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("main_toolbar")
        self.addToolBar(toolbar)

        self.new_workspace_action = QAction("New Workspace", self)
        self.new_workspace_action.triggered.connect(self._on_new_workspace)
        toolbar.addAction(self.new_workspace_action)

        self.new_project_action = QAction("New Project", self)
        self.new_project_action.triggered.connect(self._on_new_project)
        toolbar.addAction(self.new_project_action)

        self.new_region_action = QAction("New Region", self)
        self.new_region_action.triggered.connect(self._on_new_region)
        toolbar.addAction(self.new_region_action)

        self.earthdata_login_action = QAction("Earthdata Login", self)
        self.earthdata_login_action.triggered.connect(self._on_earthdata_login)
        toolbar.addAction(self.earthdata_login_action)

        self.gacos_email_action = QAction("GACOS Email", self)
        self.gacos_email_action.triggered.connect(self._on_gacos_email)
        toolbar.addAction(self.gacos_email_action)

    def _build_menu_bar(self) -> None:
        """Build the menu bar with a Language switcher and a Help/About entry."""
        menu_bar = self.menuBar()
        menu_bar.setObjectName("main_menu_bar")

        self.language_menu = menu_bar.addMenu(i18n.tr("menu.language"))
        self.language_menu.setObjectName("language_menu")
        self._language_group = QActionGroup(self)
        self._language_group.setExclusive(True)
        self._language_actions: dict[str, QAction] = {}
        for code, name in i18n.available_languages():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setData(code)
            action.setChecked(code == i18n.get_language())
            action.triggered.connect(lambda _checked=False, c=code: self._on_change_language(c))
            self._language_group.addAction(action)
            self.language_menu.addAction(action)
            self._language_actions[code] = action

        self.help_menu = menu_bar.addMenu(i18n.tr("menu.help"))
        self.help_menu.setObjectName("help_menu")
        self.about_action = QAction(i18n.tr("menu.about"), self)
        self.about_action.triggered.connect(self._on_about)
        self.help_menu.addAction(self.about_action)

    def _on_change_language(self, code: str) -> None:
        """Switch the UI language, persist the choice, and retranslate live."""
        i18n.set_language(code)
        i18n.save_language(code)
        self.retranslate_ui()

    def _on_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox  # noqa: PLC0415 - only needed here

        QMessageBox.information(self, i18n.tr("menu.about"), i18n.tr("about.text"))

    def retranslate_ui(self) -> None:
        """Re-apply all translatable text after a language change."""
        self.setWindowTitle(i18n.tr("app.title"))
        self.new_workspace_action.setText(i18n.tr("toolbar.new_workspace"))
        self.new_project_action.setText(i18n.tr("toolbar.new_project"))
        self.new_region_action.setText(i18n.tr("toolbar.new_region"))
        self.earthdata_login_action.setText(i18n.tr("toolbar.earthdata_login"))
        self.gacos_email_action.setText(i18n.tr("toolbar.gacos_email"))
        self.language_menu.setTitle(i18n.tr("menu.language"))
        self.help_menu.setTitle(i18n.tr("menu.help"))
        self.about_action.setText(i18n.tr("menu.about"))
        for code, action in self._language_actions.items():
            action.setChecked(code == i18n.get_language())
        # Retranslate every child panel that supports it.
        for widget in (
            self.project_tree,
            self.workflow_steps,
            self.aoi_panel,
            self.asf_cart_panel,
            self.scene_table,
            self.scene_check_panel,
            self.planning_panel,
            self.report_panel,
            self.download_panel,
            self.dem_download_panel,
            self.gacos_download_panel,
            self.queue_log_panel,
            self.status_bar_widget,
        ):
            retranslate = getattr(widget, "retranslate_ui", None)
            if callable(retranslate):
                retranslate()

    # --- logic methods (testable without dialogs) -----------------------------

    def apply_new_workspace(self, root: str, name: str | None = None) -> bool:
        """Create a workspace from the given root/name; report via the status bar."""
        try:
            workspace = self.state.create_workspace(root, name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created workspace: {workspace_display_name(workspace)}")
        return True

    def apply_new_project(self, name: str) -> bool:
        """Create a project under the current workspace; report via the status bar."""
        try:
            project = self.state.add_project(name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created project: {project.project_name}")
        return True

    def apply_new_region(self, name: str) -> bool:
        """Create a region under the current project; report via the status bar."""
        try:
            region = self.state.add_region(name)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"Created region: {region.region_name}")
        return True

    def apply_set_region_aoi(self, aoi: Aoi) -> bool:
        """Bind an AOI to the current region; report via the status bar."""
        try:
            region = self.state.set_current_region_aoi(aoi)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.project_tree.refresh_from_state(self.state)
        self.status_bar_widget.set_status(f"AOI set for region: {region.region_name}")
        return True

    def apply_import_scenes(self, scenes: list[Scene]) -> bool:
        """Store parsed scenes on the current region and show them in the table."""
        try:
            region = self.state.set_current_region_scenes(scenes)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return False
        self.scene_table.set_scenes(region.scenes)
        self.status_bar_widget.set_status(
            f"Imported {len(region.scenes)} scene(s) into region: {region.region_name}"
        )
        return True

    def apply_run_scene_check(self) -> SceneCheckReport | None:
        """Run the scene consistency check on the current region's scenes."""
        region = self.state.current_region()
        if region is None:
            self.status_bar_widget.set_status(
                str(
                    InsarPrepError(
                        "create or select a region before running the scene check",
                        code=ErrorCode.GUI002,
                    )
                )
            )
            return None
        report = self.scene_check_panel.run_check(region.scenes)
        self.last_scene_report = report
        self._show_report_status(report)
        return report

    def _show_report_status(self, report: SceneCheckReport) -> None:
        """Link the scene-check report to the bottom warnings/errors bar."""
        errors = sum(1 for issue in report.issues if issue.severity is CheckSeverity.ERROR)
        warnings = sum(1 for issue in report.issues if issue.severity is CheckSeverity.WARNING)
        if report.has_errors:
            self.status_bar_widget.set_status(f"Scene check: {errors} error(s)")
        elif report.has_warnings:
            self.status_bar_widget.set_status(f"Scene check: {warnings} warning(s)")
        else:
            self.status_bar_widget.set_ready()

    def _require_region(self, action: str):
        """Return the current region, or report a coded GUI002 error and ``None``."""
        region = self.state.current_region()
        if region is None:
            error = InsarPrepError(
                f"create or select a region before {action}", code=ErrorCode.GUI002
            )
            self.status_bar_widget.set_status(str(error))
        return region

    def apply_run_orbit_match(self) -> OrbitMatchReport | None:
        """Scan a local orbit directory and match it to the region's scenes."""
        region = self._require_region("matching orbits")
        if region is None:
            return None
        if not region.scenes:
            self.status_bar_widget.set_status(
                str(InsarPrepError("import scenes before matching orbits", code=ErrorCode.GUI002))
            )
            return None
        try:
            report = self.planning_panel.run_orbit_match(region.scenes)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None
        self.last_orbit_report = report
        self.status_bar_widget.set_status(
            f"Orbit: {report.matched_scenes}/{report.total_scenes} scene(s) matched"
        )
        return report

    def apply_run_dem_plan(self) -> tuple[DemPlanningReport, DemConversionReport] | None:
        """Build an offline DEM request + conversion plan for the region's AOI."""
        region = self._require_region("planning a DEM")
        if region is None:
            return None
        project = self.state.current_project()
        output_root = project.project_root if project is not None else region.region_root
        try:
            reports = self.planning_panel.run_dem_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_root=output_root,
            )
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None
        self.last_dem_planning_report, self.last_dem_conversion_report = reports
        self.status_bar_widget.set_status("DEM plan built (planned only; no .tif created)")
        return reports

    def apply_run_gacos_plan(
        self,
    ) -> tuple[GacosPlanningReport, GacosImportCheckReport | None] | None:
        """Build an offline GACOS request plan (and optional import check)."""
        region = self._require_region("planning GACOS")
        if region is None:
            return None
        project = self.state.current_project()
        output_root = project.project_root if project is not None else region.region_root
        try:
            reports = self.planning_panel.run_gacos_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                scenes=region.scenes,
                output_root=output_root,
            )
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None
        planning_report, import_report = reports
        self.last_gacos_planning_report = planning_report
        self.last_gacos_import_report = import_report
        dates = len(planning_report.plan.unique_dates) if planning_report.plan is not None else 0
        self.status_bar_widget.set_status(f"GACOS plan built (planned only; {dates} date(s))")
        return reports

    def apply_generate_reports(self) -> tuple[DataPreparationReport, list[Path]] | None:
        """Generate the five-file report set for the current region (planned/offline)."""
        region = self._require_region("generating reports")
        if region is None:
            return None
        output_root = self.report_panel.output_root()
        if not output_root:
            error = InsarPrepError("output root is required", code=ErrorCode.GUI003)
            self.status_bar_widget.set_status(str(error))
            return None
        # Always include a scene-consistency section: reuse the last check if the
        # user ran one, otherwise run it now from the region's scenes (core call).
        scene_report = self.last_scene_report
        if scene_report is None:
            scene_report = check_scene_collection(region.scenes)
        try:
            report, paths = self.report_panel.generate(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                scenes=region.scenes,
                output_root=output_root,
                scene_check_report=scene_report,
                orbit_match_report=self.last_orbit_report,
                dem_planning_report=self.last_dem_planning_report,
                dem_conversion_report=self.last_dem_conversion_report,
                gacos_planning_report=self.last_gacos_planning_report,
                gacos_import_report=self.last_gacos_import_report,
            )
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None
        self._show_generated_report_status(report, paths)
        return report, paths

    def _show_generated_report_status(
        self, report: DataPreparationReport, paths: list[Path]
    ) -> None:
        """Reflect the generated report set on the bottom warnings/errors bar."""
        summary = report.summary
        errors = int(summary.get("error_count", 0))
        warnings = int(summary.get("warning_count", 0))
        if report.has_errors:
            self.status_bar_widget.set_status(
                f"Reports generated ({len(paths)} files): {errors} error(s)"
            )
        elif report.has_warnings:
            self.status_bar_widget.set_status(
                f"Reports generated ({len(paths)} files): {warnings} warning(s)"
            )
        else:
            self.status_bar_widget.set_status(f"Reports generated: {len(paths)} files (Ready)")

    # --- ASF SLC download -----------------------------------------------------

    def _download_inputs(self, action: str) -> tuple[list[Scene], str] | None:
        """Return ``(scenes, output_dir)`` for a download, or report a coded error."""
        region = self._require_region(action)
        if region is None:
            return None
        if not region.scenes:
            self.status_bar_widget.set_status(
                str(InsarPrepError(f"import scenes before {action}", code=ErrorCode.GUI002))
            )
            return None
        output_dir = self.download_panel.output_dir()
        if not output_dir:
            error = InsarPrepError("output root is required", code=ErrorCode.GUI003)
            self.status_bar_widget.set_status(str(error))
            return None
        return region.scenes, output_dir

    def apply_plan_downloads(self) -> AsfDownloadPlan | None:
        """Write the offline dry-run download plan for the current region (no network)."""
        inputs = self._download_inputs("planning downloads")
        if inputs is None:
            return None
        scenes, output_dir = inputs
        try:
            plan = self.download_panel.plan_only(scenes, output_dir)
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None
        self.status_bar_widget.set_status(
            f"Download plan (dry-run): {plan.planned_count} planned, "
            f"{plan.missing_url_count} missing URL"
        )
        return plan

    def apply_run_real_download(
        self, *, downloader: object | None = None, resolver: object | None = None
    ) -> DownloadRunSummary | None:
        """Run the real download synchronously (used headless/in tests).

        The live GUI uses :meth:`_on_run_download`, which runs the same
        :func:`run_asf_download` on a :class:`DownloadWorker` thread so the
        window stays responsive. Both paths share one orchestration. Inject
        ``downloader`` / ``resolver`` to exercise this offline without a network
        or a real Earthdata account.
        """
        inputs = self._download_inputs("downloading SLCs")
        if inputs is None:
            return None
        scenes, output_dir = inputs
        try:
            summary = run_asf_download(
                scenes,
                output_dir,
                credential_source=self.download_panel.selected_credential_source(),
                downloader=downloader,
                resolver=resolver or resolve_credentials,
                progress=self.download_panel.on_scene_done,
            )
        except InsarPrepError as exc:
            self.download_panel.set_failed(str(exc))
            self.status_bar_widget.set_status(str(exc))
            return None
        self.download_panel.set_download_summary(summary)
        self.status_bar_widget.set_status(f"Download: {summary.summary_line()}")
        return summary

    # --- DEM download ---------------------------------------------------------

    def _build_dem_plan(self, action: str) -> DemRequestPlan | None:
        """Build a DEM request plan for the current region (needs an AOI + output root)."""
        region = self._require_region(action)
        if region is None:
            return None
        output_root = self.dem_download_panel.output_dir()
        if not output_root:
            error = InsarPrepError("output root is required", code=ErrorCode.GUI003)
            self.status_bar_widget.set_status(str(error))
            return None
        try:
            return create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_root=output_root,
                dataset=self.dem_download_panel.selected_dataset(),
            )
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return None

    def apply_plan_dem_download(self) -> DemRequestPlan | None:
        """Show the offline dry-run DEM plan for the current region (no network)."""
        plan = self._build_dem_plan("planning a DEM download")
        if plan is None:
            return None
        self.dem_download_panel.plan_summary(plan)
        self.status_bar_widget.set_status(
            f"DEM plan (dry-run): {plan.dataset} (no file downloaded)"
        )
        return plan

    def apply_run_real_dem_download(
        self, *, downloader: object | None = None
    ) -> DemDownloadRunSummary | None:
        """Run the real DEM download synchronously (used headless/in tests).

        The live GUI uses :meth:`_on_run_dem_download`, which runs the same
        :func:`run_dem_download` on a :class:`DemDownloadWorker` thread. Inject
        ``downloader`` to exercise this offline without a network or a real key.
        """
        plan = self._build_dem_plan("downloading a DEM")
        if plan is None:
            return None
        output_dir = self.dem_download_panel.output_dir()
        try:
            summary = run_dem_download(
                [plan],
                output_dir,
                key_source=DemKeySource.AUTO,
                downloader=downloader,
                progress=self.dem_download_panel.on_dem_done,
            )
        except InsarPrepError as exc:
            self.dem_download_panel.set_failed(str(exc))
            self.status_bar_widget.set_status(str(exc))
            return None
        self.dem_download_panel.set_dem_summary(summary)
        self.status_bar_widget.set_status(f"DEM download: {summary.summary_line()}")
        return summary

    # --- dialog handlers ------------------------------------------------------

    def _on_new_workspace(self) -> None:
        dialog = WorkspaceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_workspace(dialog.workspace_root(), dialog.workspace_name())

    def _on_new_project(self) -> None:
        dialog = ProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_project(dialog.project_name())

    def _on_new_region(self) -> None:
        dialog = RegionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_new_region(dialog.region_name())

    def _on_earthdata_login(self) -> None:
        EarthdataLoginDialog(self).exec()
        self.download_panel.refresh_credential_status()

    def _on_set_aoi(self) -> None:
        try:
            aoi = self.aoi_panel.build_aoi()
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return
        self.apply_set_region_aoi(aoi)

    def _on_import_cart(self) -> None:
        try:
            scenes = self.asf_cart_panel.parse_cart()
        except InsarPrepError as exc:
            self.status_bar_widget.set_status(str(exc))
            return
        self.apply_import_scenes(scenes)

    def _on_run_scene_check(self) -> None:
        self.apply_run_scene_check()

    def _on_run_orbit_match(self) -> None:
        self.apply_run_orbit_match()

    def _on_run_dem_plan(self) -> None:
        self.apply_run_dem_plan()

    def _on_run_gacos_plan(self) -> None:
        self.apply_run_gacos_plan()

    def _on_generate_reports(self) -> None:
        self.apply_generate_reports()

    def _on_download_login(self) -> None:
        EarthdataLoginDialog(self).exec()
        self.download_panel.refresh_credential_status()

    def _on_run_download(self) -> None:
        """Dispatch the Download panel's Run button: dry-run (sync) or real (threaded)."""
        if self.download_panel.selected_mode() != "real":
            self.apply_plan_downloads()
            return
        inputs = self._download_inputs("downloading SLCs")
        if inputs is None:
            return
        scenes, output_dir = inputs
        # Real download needs the optional 'download' extra (requests). Check
        # without importing it so a missing extra gives a clear message.
        if importlib.util.find_spec("requests") is None:
            self.status_bar_widget.set_status(
                "real download needs the 'download' extra (requests); "
                "install it with 'uv sync --extra download'"
            )
            return
        if self._download_worker is not None and self._download_worker.isRunning():
            self.status_bar_widget.set_status("a download is already running")
            return
        total = sum(1 for scene in scenes if getattr(scene, "url", None))
        self.download_panel.begin_run(total)
        worker = DownloadWorker(
            scenes, output_dir, self.download_panel.selected_credential_source()
        )
        worker.scene_done.connect(self.download_panel.on_scene_done)
        worker.run_finished.connect(self._on_download_finished)
        worker.run_failed.connect(self._on_download_failed)
        worker.finished.connect(worker.deleteLater)
        self._download_worker = worker
        self.status_bar_widget.set_status(f"Downloading {total} scene(s)… (Cancel to stop)")
        worker.start()

    def _on_cancel_download(self) -> None:
        worker = self._download_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self.status_bar_widget.set_status("Cancelling download…")

    def _on_download_finished(self, summary: DownloadRunSummary) -> None:
        self.download_panel.set_download_summary(summary)
        self.status_bar_widget.set_status(f"Download: {summary.summary_line()}")
        self._download_worker = None

    def _on_download_failed(self, message: str) -> None:
        self.download_panel.set_failed(message)
        self.status_bar_widget.set_status(f"Download failed: {message}")
        self._download_worker = None

    def _on_dem_key_login(self) -> None:
        OpenTopographyKeyDialog(self).exec()
        self.dem_download_panel.refresh_key_status()

    def _on_run_dem_download(self) -> None:
        """Dispatch the DEM panel's Run button: dry-run (sync) or real (threaded)."""
        if self.dem_download_panel.selected_mode() != "real":
            self.apply_plan_dem_download()
            return
        plan = self._build_dem_plan("downloading a DEM")
        if plan is None:
            return
        # Real download needs the optional 'download' extra (requests). Check
        # without importing it so a missing extra gives a clear message.
        if importlib.util.find_spec("requests") is None:
            self.status_bar_widget.set_status(
                "real DEM download needs the 'download' extra (requests); "
                "install it with 'uv sync --extra download'"
            )
            return
        if self._dem_download_worker is not None and self._dem_download_worker.isRunning():
            self.status_bar_widget.set_status("a DEM download is already running")
            return
        output_dir = self.dem_download_panel.output_dir()
        self.dem_download_panel.begin_run()
        worker = DemDownloadWorker(plan, output_dir, DemKeySource.AUTO)
        worker.dem_done.connect(self.dem_download_panel.on_dem_done)
        worker.run_finished.connect(self._on_dem_download_finished)
        worker.run_failed.connect(self._on_dem_download_failed)
        worker.finished.connect(worker.deleteLater)
        self._dem_download_worker = worker
        self.status_bar_widget.set_status("Downloading DEM… (Cancel to stop)")
        worker.start()

    def _on_cancel_dem_download(self) -> None:
        worker = self._dem_download_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self.status_bar_widget.set_status("Cancelling DEM download…")

    def _on_dem_download_finished(self, summary: DemDownloadRunSummary) -> None:
        self.dem_download_panel.set_dem_summary(summary)
        self.status_bar_widget.set_status(f"DEM download: {summary.summary_line()}")
        self._dem_download_worker = None

    def _on_dem_download_failed(self, message: str) -> None:
        self.dem_download_panel.set_failed(message)
        self.status_bar_widget.set_status(f"DEM download failed: {message}")
        self._dem_download_worker = None

    # --- GACOS request / download ---------------------------------------------

    def _on_gacos_email(self) -> None:
        GacosEmailDialog(self).exec()
        self.gacos_download_panel.refresh_email_status()

    def _gacos_request_inputs(self, action: str):
        """Return ``(region, bbox, dates, output_root)`` for a GACOS request."""
        region = self._require_region(action)
        if region is None:
            return None
        if region.aoi is None or region.aoi.bbox is None:
            self.status_bar_widget.set_status(
                str(InsarPrepError("set an AOI before requesting GACOS", code=ErrorCode.AOI001))
            )
            return None
        output_root = self.gacos_download_panel.output_dir()
        if not output_root:
            error = InsarPrepError("output root is required", code=ErrorCode.GUI003)
            self.status_bar_widget.set_status(str(error))
            return None
        dates = self.gacos_download_panel.manual_dates()
        if not dates:
            dates = extract_gacos_dates_from_scenes(region.scenes)
        if not dates:
            self.status_bar_widget.set_status(
                str(
                    InsarPrepError(
                        "import scenes or enter dates before requesting GACOS",
                        code=ErrorCode.GAC001,
                    )
                )
            )
            return None
        bbox = region.aoi.bbox.buffer(0.05)
        return region, bbox, dates, output_root

    def apply_run_gacos_request(
        self, *, client: object | None = None
    ) -> GacosRequestRunSummary | None:
        """Run the GACOS request synchronously (used headless/in tests)."""
        inputs = self._gacos_request_inputs("submitting a GACOS request")
        if inputs is None:
            return None
        region, bbox, dates, output_root = inputs
        hour, minute = self.gacos_download_panel.selected_time()
        try:
            summary = run_gacos_request(
                region_safe_name=region.region_safe_name,
                bbox=bbox,
                dates=dates,
                email="",
                output_root=output_root,
                hour=hour,
                minute=minute,
                output_format=self.gacos_download_panel.selected_format(),
                client=client,
            )
        except InsarPrepError as exc:
            self.gacos_download_panel.set_failed(str(exc))
            self.status_bar_widget.set_status(str(exc))
            return None
        self.gacos_download_panel.set_request_summary(summary)
        self.status_bar_widget.set_status(f"GACOS request: {summary.summary_line()}")
        return summary

    def apply_run_gacos_download(
        self, *, client: object | None = None
    ) -> GacosDownloadRunSummary | None:
        """Run the GACOS result download synchronously (used headless/in tests)."""
        region = self._require_region("downloading GACOS results")
        if region is None:
            return None
        urls = self.gacos_download_panel.result_urls()
        if not urls:
            self.status_bar_widget.set_status(
                str(InsarPrepError("paste at least one GACOS link", code=ErrorCode.GAC004))
            )
            return None
        output_root = self.gacos_download_panel.output_dir()
        if not output_root:
            error = InsarPrepError("output root is required", code=ErrorCode.GUI003)
            self.status_bar_widget.set_status(str(error))
            return None
        output_dir = Path(output_root) / region.region_safe_name / Path(*GACOS_REQUESTS_SUBDIR)
        expected = extract_gacos_dates_from_scenes(region.scenes) or None
        try:
            summary = run_gacos_download(urls, output_dir, expected_dates=expected, client=client)
        except InsarPrepError as exc:
            self.gacos_download_panel.set_failed(str(exc))
            self.status_bar_widget.set_status(str(exc))
            return None
        self.gacos_download_panel.set_download_summary(summary)
        self.status_bar_widget.set_status(f"GACOS download: {summary.summary_line()}")
        return summary

    def _on_gacos_submit(self) -> None:
        """Start the real GACOS request on a background thread."""
        inputs = self._gacos_request_inputs("submitting a GACOS request")
        if inputs is None:
            return
        if importlib.util.find_spec("requests") is None:
            self.status_bar_widget.set_status(
                "real GACOS request needs the 'download' extra (requests); "
                "install it with 'uv sync --extra download'"
            )
            return
        if self._gacos_request_worker is not None and self._gacos_request_worker.isRunning():
            self.status_bar_widget.set_status("a GACOS request is already running")
            return
        region, bbox, dates, output_root = inputs
        hour, minute = self.gacos_download_panel.selected_time()
        self.gacos_download_panel.begin_run("Submitting GACOS request…")
        worker = GacosRequestWorker(
            region_safe_name=region.region_safe_name,
            bbox=bbox,
            dates=dates,
            email="",
            output_root=output_root,
            hour=hour,
            minute=minute,
            output_format=self.gacos_download_panel.selected_format(),
        )
        worker.batch_done.connect(self.gacos_download_panel.on_batch_done)
        worker.run_finished.connect(self._on_gacos_request_finished)
        worker.run_failed.connect(self._on_gacos_failed)
        worker.finished.connect(worker.deleteLater)
        self._gacos_request_worker = worker
        self.status_bar_widget.set_status("Submitting GACOS request… (Cancel to stop)")
        worker.start()

    def _on_gacos_fetch(self) -> None:
        """Start the real GACOS result download on a background thread."""
        region = self._require_region("downloading GACOS results")
        if region is None:
            return
        urls = self.gacos_download_panel.result_urls()
        if not urls:
            self.status_bar_widget.set_status(
                str(InsarPrepError("paste at least one GACOS link", code=ErrorCode.GAC004))
            )
            return
        output_root = self.gacos_download_panel.output_dir()
        if not output_root:
            self.status_bar_widget.set_status(
                str(InsarPrepError("output root is required", code=ErrorCode.GUI003))
            )
            return
        if importlib.util.find_spec("requests") is None:
            self.status_bar_widget.set_status(
                "real GACOS download needs the 'download' extra (requests); "
                "install it with 'uv sync --extra download'"
            )
            return
        if self._gacos_fetch_worker is not None and self._gacos_fetch_worker.isRunning():
            self.status_bar_widget.set_status("a GACOS download is already running")
            return
        output_dir = Path(output_root) / region.region_safe_name / Path(*GACOS_REQUESTS_SUBDIR)
        expected = extract_gacos_dates_from_scenes(region.scenes) or None
        self.gacos_download_panel.begin_run("Downloading GACOS result…")
        worker = GacosFetchWorker(urls=urls, output_directory=output_dir, expected_dates=expected)
        worker.fetch_done.connect(self.gacos_download_panel.on_fetch_done)
        worker.run_finished.connect(self._on_gacos_download_finished)
        worker.run_failed.connect(self._on_gacos_failed)
        worker.finished.connect(worker.deleteLater)
        self._gacos_fetch_worker = worker
        self.status_bar_widget.set_status("Downloading GACOS result… (Cancel to stop)")
        worker.start()

    def _on_cancel_gacos(self) -> None:
        worker = self._gacos_fetch_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self.status_bar_widget.set_status("Cancelling GACOS download…")

    def _on_gacos_request_finished(self, summary: GacosRequestRunSummary) -> None:
        self.gacos_download_panel.set_request_summary(summary)
        self.status_bar_widget.set_status(f"GACOS request: {summary.summary_line()}")
        self._gacos_request_worker = None

    def _on_gacos_download_finished(self, summary: GacosDownloadRunSummary) -> None:
        self.gacos_download_panel.set_download_summary(summary)
        self.status_bar_widget.set_status(f"GACOS download: {summary.summary_line()}")
        self._gacos_fetch_worker = None

    def _on_gacos_failed(self, message: str) -> None:
        self.gacos_download_panel.set_failed(message)
        self.status_bar_widget.set_status(f"GACOS failed: {message}")
        self._gacos_request_worker = None
        self._gacos_fetch_worker = None
