"""Centre panel: Processing AOI input for the current Region (Task 039, 048).

Lets the user define a Region's Processing AOI from one of several mutually
exclusive sources -- a manual bounding box, a GeoJSON file, a WKT string, an
ESRI Shapefile, a KML file, a zipped KML (KMZ), or any of those vector files
auto-detected by extension -- and hands the result to
:class:`insar_prep.gui.state.GuiState`. File sources carry a Browse button (a
native file picker). The panel holds no parsing/business logic of its own: it
only collects text and calls the existing core interfaces

* :func:`insar_prep.processing.aoi.make_processing_aoi_from_bbox`,
* :func:`insar_prep.processing.aoi_import.load_aoi_from_geojson`,
* :func:`insar_prep.processing.aoi_import.load_aoi_from_wkt`,
* :func:`insar_prep.processing.aoi_vector.load_aoi_from_shapefile`,
* :func:`insar_prep.processing.aoi_vector.load_aoi_from_kml`,
* :func:`insar_prep.processing.aoi_vector.load_aoi_from_kmz`,
* :func:`insar_prep.processing.aoi_vector.load_aoi_from_file`,

which already validate input and raise coded :class:`InsarPrepError` errors. No
coordinate transform is performed (EPSG:4326 lon/lat only).
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import ValidationError
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi, BBox
from insar_prep.gui.map_picker import MapPickerDialog, is_map_available
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.processing.aoi_import import load_aoi_from_geojson, load_aoi_from_wkt
from insar_prep.processing.aoi_vector import (
    load_aoi_from_file,
    load_aoi_from_kml,
    load_aoi_from_kmz,
    load_aoi_from_shapefile,
)

# Qt file-dialog filters per AOI file source.
_GEOJSON_FILTER = "GeoJSON (*.geojson *.json);;All files (*)"
_SHP_FILTER = "ESRI Shapefile (*.shp);;All files (*)"
_KML_FILTER = "KML (*.kml);;All files (*)"
_KMZ_FILTER = "KMZ (*.kmz);;All files (*)"
_ANY_VECTOR_FILTER = "Vector AOI (*.geojson *.json *.shp *.kml *.kmz);;All files (*)"


class AoiInputMode(IntEnum):
    """The mutually exclusive AOI input sources (stacked-page order)."""

    BBOX = 0
    GEOJSON = 1
    WKT = 2
    SHP = 3
    KML = 4
    KMZ = 5
    FILE = 6


class AoiPanel(QGroupBox):
    """Collect a Processing AOI from a bbox, a GeoJSON file, or a WKT string."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Area of interest (AOI)", parent)
        self.setObjectName("aoi_panel")

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("aoi_mode_combo")
        self.mode_combo.addItem("Bounding box (W S E N)", AoiInputMode.BBOX)
        self.mode_combo.addItem("GeoJSON file", AoiInputMode.GEOJSON)
        self.mode_combo.addItem("WKT text", AoiInputMode.WKT)
        self.mode_combo.addItem("Shapefile (.shp)", AoiInputMode.SHP)
        self.mode_combo.addItem("KML file (.kml)", AoiInputMode.KML)
        self.mode_combo.addItem("KMZ file (.kmz)", AoiInputMode.KMZ)
        self.mode_combo.addItem("Vector file (auto-detect)", AoiInputMode.FILE)

        self.stack = QStackedWidget()
        self.stack.setObjectName("aoi_input_stack")
        # Pages are added in AoiInputMode order so the combo index, the stacked
        # page index, and the enum value all line up. File pages carry a Browse
        # button (a native file picker) alongside the editable path.
        self.stack.addWidget(self._build_bbox_page())
        self.geojson_edit = self._build_file_page(
            "aoi_geojson_path", "Path to a .geojson / .json file (EPSG:4326)", _GEOJSON_FILTER
        )
        self.stack.addWidget(self._build_wkt_page())
        self.shp_edit = self._build_file_page(
            "aoi_shp_path", "Path to a .shp file (EPSG:4326)", _SHP_FILTER
        )
        self.kml_edit = self._build_file_page(
            "aoi_kml_path", "Path to a .kml file (WGS84 lon/lat)", _KML_FILTER
        )
        self.kmz_edit = self._build_file_page(
            "aoi_kmz_path", "Path to a .kmz file (WGS84 lon/lat)", _KMZ_FILTER
        )
        self.file_edit = self._build_file_page(
            "aoi_any_path", "Path to a .geojson/.shp/.kml/.kmz file", _ANY_VECTOR_FILTER
        )
        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        self.apply_button = QPushButton("Set AOI for current region")
        self.apply_button.setObjectName("aoi_apply_button")
        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        apply_row.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)
        layout.addLayout(apply_row)

    def _build_bbox_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.west_edit = QLineEdit()
        self.west_edit.setObjectName("aoi_bbox_west")
        self.south_edit = QLineEdit()
        self.south_edit.setObjectName("aoi_bbox_south")
        self.east_edit = QLineEdit()
        self.east_edit.setObjectName("aoi_bbox_east")
        self.north_edit = QLineEdit()
        self.north_edit.setObjectName("aoi_bbox_north")
        form.addRow("West:", self.west_edit)
        form.addRow("South:", self.south_edit)
        form.addRow("East:", self.east_edit)
        form.addRow("North:", self.north_edit)
        layout.addLayout(form)

        self.map_button = QPushButton(i18n.tr("aoi.pick_on_map"))
        self.map_button.setObjectName("aoi_map_button")
        self.map_button.clicked.connect(self._on_pick_on_map)
        if not is_map_available():
            self.map_button.setEnabled(False)
            self.map_button.setToolTip(i18n.tr("aoi.map.unavailable"))
        layout.addWidget(self.map_button)
        return page

    def _current_bbox_or_none(self) -> BBox | None:
        """Return a BBox from the four bbox fields if all are valid, else None."""
        try:
            west = float(self.west_edit.text().strip())
            south = float(self.south_edit.text().strip())
            east = float(self.east_edit.text().strip())
            north = float(self.north_edit.text().strip())
            return BBox(west=west, south=south, east=east, north=north)
        except (ValueError, ValidationError):
            return None

    def _on_pick_on_map(self) -> None:
        """Open the interactive map; on accept, fill the bbox fields."""
        dialog = MapPickerDialog(self, initial_bbox=self._current_bbox_or_none())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        bbox = dialog.selected_bbox()
        if bbox is None:
            return
        self.west_edit.setText(f"{bbox.west}")
        self.south_edit.setText(f"{bbox.south}")
        self.east_edit.setText(f"{bbox.east}")
        self.north_edit.setText(f"{bbox.north}")
        self.set_mode(AoiInputMode.BBOX)

    def _build_wkt_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.wkt_edit = QPlainTextEdit()
        self.wkt_edit.setObjectName("aoi_wkt_text")
        self.wkt_edit.setPlaceholderText("POLYGON ((...)) or MULTIPOLYGON (...) in EPSG:4326")
        layout.addWidget(self.wkt_edit)
        return page

    def _build_file_page(self, object_name: str, placeholder: str, file_filter: str) -> QLineEdit:
        """Build a file-path page (editable path + Browse button), add it, return the edit."""
        page = QWidget()
        form = QFormLayout(page)
        edit = QLineEdit()
        edit.setObjectName(object_name)
        edit.setPlaceholderText(placeholder)
        browse = QPushButton("Browse\u2026")
        browse.setObjectName(object_name + "_browse")
        browse.clicked.connect(lambda: self._browse_into(edit, file_filter))
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(edit)
        row_layout.addWidget(browse)
        form.addRow("File path:", row)
        self.stack.addWidget(page)
        return edit

    def _browse_into(self, edit: QLineEdit, file_filter: str) -> None:
        """Open a native file picker and write the chosen path into ``edit``."""
        path, _selected = QFileDialog.getOpenFileName(self, "Select AOI file", "", file_filter)
        if path:
            edit.setText(path)

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("aoi.title"))
        self.apply_button.setText(i18n.tr("aoi.apply"))
        self.map_button.setText(i18n.tr("aoi.pick_on_map"))
        if not self.map_button.isEnabled():
            self.map_button.setToolTip(i18n.tr("aoi.map.unavailable"))

    def current_mode(self) -> AoiInputMode:
        """Return the currently selected AOI input mode."""
        return AoiInputMode(self.mode_combo.currentData())

    def set_mode(self, mode: AoiInputMode) -> None:
        """Select an AOI input mode (also switches the visible input page)."""
        self.mode_combo.setCurrentIndex(int(mode))

    def build_aoi(self) -> Aoi:
        """Build a Processing AOI from the active input by calling core helpers.

        Raises :class:`~insar_prep.core.exceptions.InsarPrepError` (``AOI001``)
        for any invalid input; the heavy lifting (and most validation) lives in
        the reused core functions.
        """
        mode = self.current_mode()
        if mode is AoiInputMode.BBOX:
            return self._build_bbox_aoi()
        if mode is AoiInputMode.GEOJSON:
            return self._build_geojson_aoi()
        if mode is AoiInputMode.WKT:
            return self._build_wkt_aoi()
        if mode is AoiInputMode.SHP:
            return self._build_file_aoi(self.shp_edit, "Shapefile", load_aoi_from_shapefile)
        if mode is AoiInputMode.KML:
            return self._build_file_aoi(self.kml_edit, "KML", load_aoi_from_kml)
        if mode is AoiInputMode.KMZ:
            return self._build_file_aoi(self.kmz_edit, "KMZ", load_aoi_from_kmz)
        return self._build_file_aoi(self.file_edit, "AOI file", load_aoi_from_file)

    def _build_bbox_aoi(self) -> Aoi:
        values: dict[str, float] = {}
        for label, edit in (
            ("west", self.west_edit),
            ("south", self.south_edit),
            ("east", self.east_edit),
            ("north", self.north_edit),
        ):
            text = edit.text().strip()
            try:
                values[label] = float(text)
            except ValueError as exc:
                raise InputValidationError(
                    f"bbox {label} must be a number, got {text!r}", code=ErrorCode.AOI001
                ) from exc
        try:
            return make_processing_aoi_from_bbox(
                values["west"], values["east"], values["south"], values["north"]
            )
        except (ValidationError, ValueError) as exc:
            raise InputValidationError(f"invalid bbox: {exc}", code=ErrorCode.AOI001) from exc

    def _build_geojson_aoi(self) -> Aoi:
        path = self.geojson_edit.text().strip()
        if not path:
            raise InputValidationError("GeoJSON path is required", code=ErrorCode.AOI001)
        return load_aoi_from_geojson(path)

    def _build_wkt_aoi(self) -> Aoi:
        return load_aoi_from_wkt(self.wkt_edit.toPlainText())

    def _build_file_aoi(self, edit: QLineEdit, label: str, loader) -> Aoi:
        path = edit.text().strip()
        if not path:
            raise InputValidationError(f"{label} path is required", code=ErrorCode.AOI001)
        return loader(path)
