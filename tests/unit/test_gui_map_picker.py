"""Tests for the interactive map AOI picker (Task 057).

The QWebEngine view itself is never instantiated here (it needs a real browser
engine / GPU and would be flaky headless); instead the pure pieces are tested:
bounds parsing, the HTML builder, and the QWebChannel bridge signal. The AOI
panel's map button is checked for presence/enabled-state.
"""

from __future__ import annotations

import importlib.util

import pytest

from insar_prep.core.models import BBox
from insar_prep.gui.map_picker import (
    MapBridge,
    build_map_html,
    is_map_available,
    parse_bounds,
)

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")


@pytest.fixture(autouse=True)
def _offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    create_application([])


def test_parse_bounds_valid() -> None:
    assert parse_bounds('{"west": 1, "south": 2, "east": 3, "north": 4}') == (1.0, 2.0, 3.0, 4.0)


def test_parse_bounds_invalid() -> None:
    assert parse_bounds("not json") is None
    assert parse_bounds('{"west": 1}') is None
    # inverted / degenerate boxes are rejected
    assert parse_bounds('{"west": 3, "south": 2, "east": 1, "north": 4}') is None
    assert parse_bounds('{"west": 1, "south": 4, "east": 3, "north": 2}') is None


def test_build_map_html_contains_leaflet_and_bridge() -> None:
    html = build_map_html()
    assert "L.map(" in html
    assert "report_bounds" in html
    assert "qwebchannel.js" in html
    assert ".leaflet" in html  # vendored CSS inlined


def test_build_map_html_with_initial_bbox() -> None:
    bbox = BBox(west=110.1, south=30.8, east=110.6, north=31.2)
    html = build_map_html(bbox)
    assert "110.6" in html
    assert "30.8" in html


def test_is_map_available_is_bool() -> None:
    assert isinstance(is_map_available(), bool)


def test_map_bridge_emits_parsed_bounds() -> None:
    bridge = MapBridge()
    captured: list[tuple[float, float, float, float]] = []
    bridge.boundsChanged.connect(lambda w, s, e, n: captured.append((w, s, e, n)))
    bridge.report_bounds('{"west": 1, "south": 2, "east": 3, "north": 4}')
    assert captured == [(1.0, 2.0, 3.0, 4.0)]
    bridge.report_bounds("garbage")  # ignored, no emit
    assert len(captured) == 1


def test_aoi_panel_has_map_button() -> None:
    from insar_prep.gui.widgets.aoi_panel import AoiPanel

    panel = AoiPanel()
    assert panel.map_button is not None
    # When the QtWebEngine component is present the button is enabled.
    assert panel.map_button.isEnabled() == is_map_available()
