"""Interactive map AOI picker (Leaflet in QtWebEngine) -- Task 057.

A modal dialog with an embedded OpenStreetMap (Leaflet) where the user drags a
rectangle to define the Processing AOI; the drawn bounds (W/S/E/N) are sent back
to Python over a ``QWebChannel`` bridge and used to fill the AOI bounding box.

Leaflet is **vendored locally** (``insar_prep/gui/web/leaflet.{js,css}``; BSD-2,
see THIRD_PARTY_REFERENCES) so the library is not a CDN dependency -- only the map
*tiles* are fetched from OpenStreetMap when online. QtWebEngine (PySide6-Addons)
is imported lazily, so the rest of the GUI and the headless tests never need it;
:func:`is_map_available` reports whether the component is installed.
"""

from __future__ import annotations

import importlib.resources as resources
import importlib.util
import json

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from insar_prep import i18n
from insar_prep.core.logging import get_logger
from insar_prep.core.models import BBox

logger = get_logger("gui.map_picker")

# Default view: roughly the Three Gorges / Shiliushubao demo area.
_DEFAULT_CENTER = (31.0, 110.35)
_DEFAULT_ZOOM = 8


def is_map_available() -> bool:
    """Return True if the QtWebEngine + QtWebChannel components are importable."""
    return (
        importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
        and importlib.util.find_spec("PySide6.QtWebChannel") is not None
    )


def _read_web_asset(name: str) -> str:
    """Read a vendored web asset (leaflet.js / leaflet.css) as text."""
    resource = resources.files("insar_prep.gui").joinpath("web", name)
    return resource.read_text(encoding="utf-8")


def parse_bounds(payload: str) -> tuple[float, float, float, float] | None:
    """Parse a ``{west,south,east,north}`` JSON payload into a tuple, or None."""
    try:
        data = json.loads(payload)
        west = float(data["west"])
        south = float(data["south"])
        east = float(data["east"])
        north = float(data["north"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    if west >= east or south >= north:
        return None
    return (west, south, east, north)


def build_map_html(initial_bbox: BBox | None = None) -> str:
    """Build the self-contained Leaflet HTML (vendored CSS/JS inlined).

    The page draws an OSM map, lets the user drag a rectangle, and reports the
    bounds to the ``bridge`` object exposed via QWebChannel.
    """
    leaflet_css = _read_web_asset("leaflet.css")
    leaflet_js = _read_web_asset("leaflet.js")
    if initial_bbox is not None:
        center_lat = (initial_bbox.south + initial_bbox.north) / 2
        center_lon = (initial_bbox.west + initial_bbox.east) / 2
        initial = json.dumps(
            {
                "west": initial_bbox.west,
                "south": initial_bbox.south,
                "east": initial_bbox.east,
                "north": initial_bbox.north,
            }
        )
    else:
        center_lat, center_lon = _DEFAULT_CENTER
        initial = "null"
    hint = i18n.tr("aoi.map.hint")
    draw_label = i18n.tr("aoi.map.use")
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>{leaflet_css}</style>
<style>
  html, body {{ margin: 0; height: 100%;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; }}
  #map {{ position: absolute; top: 44px; bottom: 0; left: 0; right: 0; }}
  #bar {{ height: 44px; display: flex; align-items: center; gap: 12px; padding: 0 12px;
          background: #1e293b; color: #e2e8f0; font-size: 13px; }}
  #drawbtn {{ background: #2563eb; color: #fff; border: none; border-radius: 6px;
             padding: 6px 12px; cursor: pointer; }}
  #drawbtn.on {{ background: #16a34a; }}
  #hint {{ color: #cbd5e1; }}
</style>
<script type="text/javascript" src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>{leaflet_js}</script>
</head>
<body>
<div id="bar"><button id="drawbtn">{draw_label}</button><span id="hint">{hint}</span></div>
<div id="map"></div>
<script>
  var map = L.map('map').setView([{center_lat}, {center_lon}], {_DEFAULT_ZOOM});
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{ maxZoom: 19, attribution: '(c) OpenStreetMap contributors' }}).addTo(map);
  var bridge = null, rect = null, drawing = false, start = null, active = false;
  var initial = {initial};
  if (initial) {{
    rect = L.rectangle([[initial.south, initial.west], [initial.north, initial.east]],
      {{ color: '#2563eb', weight: 2 }}).addTo(map);
    map.fitBounds(rect.getBounds());
  }}
  if (typeof QWebChannel !== 'undefined') {{
    new QWebChannel(qt.webChannelTransport, function(ch) {{ bridge = ch.objects.bridge; }});
  }}
  function setActive(on) {{
    active = on;
    document.getElementById('drawbtn').classList.toggle('on', on);
    if (on) {{ map.dragging.disable(); }} else {{ map.dragging.enable(); }}
  }}
  document.getElementById('drawbtn').onclick = function() {{ setActive(!active); }};
  map.on('mousedown', function(e) {{
    if (!active) return;
    drawing = true; start = e.latlng;
    if (rect) {{ map.removeLayer(rect); rect = null; }}
  }});
  map.on('mousemove', function(e) {{
    if (!drawing) return;
    var b = L.latLngBounds(start, e.latlng);
    if (rect) {{ rect.setBounds(b); }}
    else {{ rect = L.rectangle(b, {{ color: '#2563eb', weight: 2 }}).addTo(map); }}
  }});
  map.on('mouseup', function() {{
    if (!drawing) return;
    drawing = false; setActive(false);
    if (!rect) return;
    var b = rect.getBounds();
    var payload = JSON.stringify({{ west: b.getWest(), south: b.getSouth(),
      east: b.getEast(), north: b.getNorth() }});
    if (bridge) {{ bridge.report_bounds(payload); }}
  }});
</script>
</body>
</html>"""


class MapBridge(QObject):
    """QWebChannel bridge: receives drawn bounds from the page (JS -> Python)."""

    boundsChanged = Signal(float, float, float, float)

    @Slot(str)
    def report_bounds(self, payload: str) -> None:
        parsed = parse_bounds(payload)
        if parsed is not None:
            self.boundsChanged.emit(*parsed)


class MapPickerDialog(QDialog):
    """Modal dialog: draw a rectangle on a Leaflet map to pick an AOI bbox.

    QtWebEngine is imported here (lazily). If it is unavailable, the dialog shows
    a short message instead of a map and :meth:`selected_bbox` returns ``None``.
    """

    def __init__(self, parent: QWidget | None = None, *, initial_bbox: BBox | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("aoi.mode.map"))
        self.resize(900, 640)
        self._bounds: tuple[float, float, float, float] | None = None

        layout = QVBoxLayout(self)
        if not is_map_available():
            layout.addWidget(QLabel(i18n.tr("aoi.map.unavailable")))
            close = QPushButton(i18n.tr("common.close"))
            close.clicked.connect(self.reject)
            layout.addWidget(close)
            return

        from PySide6.QtWebChannel import QWebChannel  # noqa: PLC0415 - optional, lazy
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: PLC0415 - optional, lazy

        self._bridge = MapBridge()
        self._bridge.boundsChanged.connect(self._on_bounds)
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view = QWebEngineView()
        self._view.page().setWebChannel(self._channel)
        self._view.setHtml(build_map_html(initial_bbox))
        layout.addWidget(self._view, 1)

        self._status = QLabel(i18n.tr("aoi.map.hint"))
        layout.addWidget(self._status)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._ok_button = QPushButton(i18n.tr("aoi.map.use"))
        self._ok_button.setEnabled(False)
        self._ok_button.clicked.connect(self.accept)
        cancel = QPushButton(i18n.tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        button_row.addWidget(self._ok_button)
        button_row.addWidget(cancel)
        layout.addLayout(button_row)

    def _on_bounds(self, west: float, south: float, east: float, north: float) -> None:
        self._bounds = (west, south, east, north)
        if hasattr(self, "_status"):
            self._status.setText(f"W {west:.4f}  S {south:.4f}  E {east:.4f}  N {north:.4f}")
        if hasattr(self, "_ok_button"):
            self._ok_button.setEnabled(True)

    def selected_bbox(self) -> BBox | None:
        """Return the drawn AOI bbox, or ``None`` if nothing was drawn."""
        if self._bounds is None:
            return None
        west, south, east, north = self._bounds
        return BBox(west=west, south=south, east=east, north=north)
