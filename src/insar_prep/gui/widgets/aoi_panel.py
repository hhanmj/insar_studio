"""Centre panel: Processing AOI input for the current Region (Task 039).

Lets the user define a Region's Processing AOI from one of three mutually
exclusive sources -- a manual bounding box, a GeoJSON file, or a WKT string --
and hands the result to :class:`insar_prep.gui.state.GuiState`. The panel holds
no parsing/business logic of its own: it only collects text and calls the
existing core interfaces

* :func:`insar_prep.processing.aoi.make_processing_aoi_from_bbox`,
* :func:`insar_prep.processing.aoi_import.load_aoi_from_geojson`,
* :func:`insar_prep.processing.aoi_import.load_aoi_from_wkt`,

which already validate input and raise coded :class:`InsarPrepError` errors.
Shapefile / KML / GeoPackage are intentionally not supported, and no coordinate
transform is performed (EPSG:4326 lon/lat only).
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import ValidationError
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.processing.aoi_import import load_aoi_from_geojson, load_aoi_from_wkt


class AoiInputMode(IntEnum):
    """The three mutually exclusive AOI input sources (stacked-page order)."""

    BBOX = 0
    GEOJSON = 1
    WKT = 2


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

        self.stack = QStackedWidget()
        self.stack.setObjectName("aoi_input_stack")
        self.stack.addWidget(self._build_bbox_page())
        self.stack.addWidget(self._build_geojson_page())
        self.stack.addWidget(self._build_wkt_page())
        self.mode_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        self.apply_button = QPushButton("Set AOI for current region")
        self.apply_button.setObjectName("aoi_apply_button")

        layout = QVBoxLayout(self)
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.stack)
        layout.addWidget(self.apply_button)

    def _build_bbox_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
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
        return page

    def _build_geojson_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.geojson_edit = QLineEdit()
        self.geojson_edit.setObjectName("aoi_geojson_path")
        self.geojson_edit.setPlaceholderText("Path to a .geojson / .json file (EPSG:4326)")
        form.addRow("GeoJSON path:", self.geojson_edit)
        return page

    def _build_wkt_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.wkt_edit = QPlainTextEdit()
        self.wkt_edit.setObjectName("aoi_wkt_text")
        self.wkt_edit.setPlaceholderText("POLYGON ((...)) or MULTIPOLYGON (...) in EPSG:4326")
        layout.addWidget(self.wkt_edit)
        return page

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
        return self._build_wkt_aoi()

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
