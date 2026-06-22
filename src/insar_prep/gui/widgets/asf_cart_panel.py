"""Centre panel: import scenes from a local ASF cart file (Task 040).

Lets the user point at a locally exported ASF cart (Vertex Python script, URL
text, CSV, or GeoJSON) and parse it into scenes. The panel holds no parsing
logic of its own: it only collects the file path and calls the existing core
parser :func:`insar_prep.providers.asf.cart_parser.parse_asf_cart_file`, which
is strictly local (no network, no script execution) and raises a coded
``ASF001`` error for unreadable / unsupported / empty carts. Nothing is
downloaded and no SLC files are created.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Scene
from insar_prep.providers.asf.cart_parser import parse_asf_cart_file


class AsfCartPanel(QGroupBox):
    """Collect an ASF cart path and parse it into scenes via the core parser."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ASF cart import", parent)
        self.setObjectName("asf_cart_panel")

        self.cart_edit = QLineEdit()
        self.cart_edit.setObjectName("asf_cart_path")
        self.cart_edit.setPlaceholderText("Path to a local ASF cart (.py/.txt/.csv/.geojson/.json)")

        self.import_button = QPushButton("Import cart")
        self.import_button.setObjectName("asf_cart_import_button")

        row = QHBoxLayout()
        row.addWidget(self.cart_edit)
        row.addWidget(self.import_button)

        layout = QVBoxLayout(self)
        layout.addLayout(row)

    def parse_cart(self) -> list[Scene]:
        """Parse the entered cart path into scenes using the core parser.

        Raises :class:`~insar_prep.core.exceptions.InsarPrepError` (``ASF001``)
        for an empty path or any parser failure.
        """
        path = self.cart_edit.text().strip()
        if not path:
            raise InputValidationError("ASF cart path is required", code=ErrorCode.ASF001)
        return parse_asf_cart_file(path)
