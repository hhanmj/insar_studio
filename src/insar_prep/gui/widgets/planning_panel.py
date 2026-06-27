"""Centre panel: offline orbit / DEM / GACOS planning (Task 042).

Drives the existing offline planners for the current Region and shows their
results. Everything here is **planning / matching / import-checking only**: the
panel re-implements no planner logic, never downloads anything, never creates a
DEM ``.tif``, never performs a real vertical-datum conversion, and never
contacts the network. It only collects a few inputs and calls existing core
interfaces:

* orbit: :func:`scan_orbit_directory` + :func:`match_orbits_for_scenes`,
* DEM: :func:`create_dem_request_plan` / :func:`validate_dem_request_plan`
  + :func:`create_dem_conversion_plan` / :func:`validate_dem_conversion_plan`,
* GACOS: :func:`create_gacos_request_plan` / :func:`validate_gacos_request_plan`
  + :func:`check_gacos_products` (read-only import check).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.core.enums import DemDataset, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import OrbitMatchingError
from insar_prep.core.models import Aoi, Scene
from insar_prep.providers.dem import (
    DemConversionReport,
    DemPlanningReport,
    DemProvider,
    create_dem_conversion_plan,
    create_dem_request_plan,
    validate_dem_conversion_plan,
    validate_dem_request_plan,
)
from insar_prep.providers.gacos import (
    GacosImportCheckReport,
    GacosPlanningReport,
    check_gacos_products,
    create_gacos_request_plan,
    validate_gacos_request_plan,
)
from insar_prep.providers.orbit import (
    OrbitMatchReport,
    match_orbits_for_scenes,
    scan_orbit_directory,
)

_PLANNED_ONLY = "PLANNED ONLY (no download, no .tif, no real conversion)"


class PlanningPanel(QGroupBox):
    """Offline orbit / DEM / GACOS planning for the current Region."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Offline planning (orbit / DEM / GACOS)", parent)
        self.setObjectName("planning_panel")

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_orbit_group())
        layout.addWidget(self._build_dem_group())
        layout.addWidget(self._build_gacos_group())

    # --- orbit ---------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("planning.title"))
        self.orbit_group.setTitle(i18n.tr("planning.orbit.title"))
        self.orbit_button.setText(i18n.tr("planning.orbit.button"))
        self.dem_group.setTitle(i18n.tr("planning.dem.title"))
        self.dem_button.setText(i18n.tr("planning.dem.button"))
        self.gacos_group.setTitle(i18n.tr("planning.gacos.title"))
        self.gacos_button.setText(i18n.tr("planning.gacos.button"))

    def _build_orbit_group(self) -> QGroupBox:
        group = QGroupBox("Orbit matching")
        group.setObjectName("planning_orbit_group")
        self.orbit_group = group
        self.orbit_dir_edit = QLineEdit()
        self.orbit_dir_edit.setObjectName("planning_orbit_dir")
        self.orbit_dir_edit.setPlaceholderText("Local directory of Sentinel-1 orbit (.EOF) files")
        self.orbit_button = QPushButton("Scan and match orbits")
        self.orbit_button.setObjectName("planning_orbit_button")
        self.orbit_result_label = QLabel("Orbit: not run")
        self.orbit_result_label.setObjectName("planning_orbit_result")

        row = QHBoxLayout()
        row.addWidget(self.orbit_dir_edit)
        row.addWidget(self.orbit_button)
        layout = QVBoxLayout(group)
        layout.addLayout(row)
        layout.addWidget(self.orbit_result_label)
        return group

    def orbit_directory(self) -> str:
        """Return the entered orbit directory (stripped)."""
        return self.orbit_dir_edit.text().strip()

    def run_orbit_match(self, scenes: list[Scene]) -> OrbitMatchReport:
        """Scan the orbit directory and match it against ``scenes`` (offline)."""
        directory = self.orbit_directory()
        if not directory:
            raise OrbitMatchingError("orbit directory is required", code=ErrorCode.ORB001)
        orbit_files = scan_orbit_directory(directory)
        report = match_orbits_for_scenes(scenes, orbit_files)
        self.orbit_result_label.setText(
            f"Orbit: matched {report.matched_scenes} / {report.total_scenes} "
            f"(unmatched {report.unmatched_scenes}; {len(orbit_files)} orbit files)"
        )
        return report

    # --- DEM -----------------------------------------------------------------

    def _build_dem_group(self) -> QGroupBox:
        group = QGroupBox("DEM request + conversion plan")
        group.setObjectName("planning_dem_group")
        self.dem_group = group
        self.dem_dataset_combo = _enum_combo(DemDataset, DemDataset.COP30, "planning_dem_dataset")
        self.dem_provider_combo = _enum_combo(
            DemProvider, DemProvider.OPENTOPOGRAPHY, "planning_dem_provider"
        )
        self.dem_source_combo = _enum_combo(
            VerticalDatum, VerticalDatum.EGM2008, "planning_dem_source_datum"
        )
        self.dem_target_combo = _enum_combo(
            VerticalDatum, VerticalDatum.WGS84_ELLIPSOID, "planning_dem_target_datum"
        )
        self.dem_button = QPushButton("Build DEM plan")
        self.dem_button.setObjectName("planning_dem_button")
        self.dem_result_label = QLabel("DEM: not run")
        self.dem_result_label.setObjectName("planning_dem_result")
        self.dem_paths_label = QLabel("")
        self.dem_paths_label.setObjectName("planning_dem_paths")
        self.dem_paths_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Dataset:", self.dem_dataset_combo)
        form.addRow("Provider:", self.dem_provider_combo)
        form.addRow("Source datum:", self.dem_source_combo)
        form.addRow("Target datum:", self.dem_target_combo)
        dem_button_row = QHBoxLayout()
        dem_button_row.addStretch(1)
        dem_button_row.addWidget(self.dem_button)

        layout = QVBoxLayout(group)
        layout.addLayout(form)
        layout.addLayout(dem_button_row)
        layout.addWidget(self.dem_result_label)
        layout.addWidget(self.dem_paths_label)
        return group

    def run_dem_plan(
        self,
        *,
        region_id: str,
        region_safe_name: str,
        processing_aoi: Aoi,
        output_root: Path | str,
    ) -> tuple[DemPlanningReport, DemConversionReport]:
        """Build + validate an offline DEM request and conversion plan."""
        plan = create_dem_request_plan(
            region_id=region_id,
            region_safe_name=region_safe_name,
            processing_aoi=processing_aoi,
            output_root=output_root,
            dataset=self.dem_dataset_combo.currentData(),
            provider=self.dem_provider_combo.currentData(),
            source_vertical_datum=VerticalDatum(self.dem_source_combo.currentData()),
            target_vertical_datum=VerticalDatum(self.dem_target_combo.currentData()),
        )
        planning_report = validate_dem_request_plan(plan)
        conversion_report = validate_dem_conversion_plan(create_dem_conversion_plan(plan))
        self.dem_result_label.setText(f"DEM plan: {_PLANNED_ONLY}")
        self.dem_paths_label.setText(
            f"Raw DEM: {plan.raw_dem_path}\n"
            f"Ellipsoid DEM: {plan.ellipsoid_dem_path}\n"
            f"SARscape-ready DEM: {plan.sarscape_ready_dem_path}"
        )
        return planning_report, conversion_report

    # --- GACOS ---------------------------------------------------------------

    def _build_gacos_group(self) -> QGroupBox:
        group = QGroupBox("GACOS request plan + import check")
        group.setObjectName("planning_gacos_group")
        self.gacos_group = group
        self.gacos_import_dir_edit = QLineEdit()
        self.gacos_import_dir_edit.setObjectName("planning_gacos_import_dir")
        self.gacos_import_dir_edit.setPlaceholderText(
            "Optional: local directory of already-downloaded GACOS products"
        )
        self.gacos_button = QPushButton("Build GACOS plan")
        self.gacos_button.setObjectName("planning_gacos_button")
        self.gacos_result_label = QLabel("GACOS: not run")
        self.gacos_result_label.setObjectName("planning_gacos_result")

        row = QHBoxLayout()
        row.addWidget(self.gacos_import_dir_edit)
        row.addWidget(self.gacos_button)
        layout = QVBoxLayout(group)
        layout.addLayout(row)
        layout.addWidget(self.gacos_result_label)
        return group

    def gacos_import_directory(self) -> str:
        """Return the optional GACOS import directory (stripped)."""
        return self.gacos_import_dir_edit.text().strip()

    def run_gacos_plan(
        self,
        *,
        region_id: str,
        region_safe_name: str,
        processing_aoi: Aoi,
        scenes: list[Scene],
        output_root: Path | str,
    ) -> tuple[GacosPlanningReport, GacosImportCheckReport | None]:
        """Build + validate an offline GACOS request plan and optionally check imports."""
        plan = create_gacos_request_plan(
            region_id=region_id,
            region_safe_name=region_safe_name,
            processing_aoi=processing_aoi,
            scenes=scenes,
            output_root=output_root,
        )
        planning_report = validate_gacos_request_plan(plan)
        import_report: GacosImportCheckReport | None = None
        import_dir = self.gacos_import_directory()
        if import_dir:
            import_report = check_gacos_products(request_plan=plan, product_directory=import_dir)

        text = (
            f"GACOS plan: {_PLANNED_ONLY} — "
            f"{len(plan.unique_dates)} date(s) / {len(plan.batches)} batch(es)"
        )
        if import_report is not None:
            text += (
                f"; import check: {len(import_report.found_dates)} found, "
                f"{len(import_report.missing_dates)} missing"
            )
        self.gacos_result_label.setText(text)
        return planning_report, import_report


def _enum_combo(enum_cls, default, object_name: str) -> QComboBox:
    """Build a combo box of a StrEnum's values, defaulting to ``default``."""
    combo = QComboBox()
    combo.setObjectName(object_name)
    for member in enum_cls:
        combo.addItem(member.value, member.value)
    combo.setCurrentIndex(combo.findData(default.value))
    return combo
