"""Tests for offline AOI import from GeoJSON / WKT (Task 029).

Covers the supported GeoJSON shapes (Geometry, Feature, FeatureCollection) and
WKT geometries (Polygon, MultiPolygon), the error paths (missing/empty file,
invalid JSON/WKT, unsupported geometry types, out-of-range coordinates, non-WGS84
CRS), and that the resulting Processing AOI bbox matches the geometry bounds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi
from insar_prep.processing.aoi_import import (
    geometry_to_processing_aoi,
    load_aoi_from_geojson,
    load_aoi_from_wkt,
)

_WEST, _SOUTH, _EAST, _NORTH = 110.1, 30.8, 110.6, 31.2


def _rect(west: float, south: float, east: float, north: float) -> list:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


def _rect_wkt(west: float, south: float, east: float, north: float) -> str:
    return (
        f"POLYGON (({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )


def _polygon(west: float, south: float, east: float, north: float) -> dict:
    return {"type": "Polygon", "coordinates": _rect(west, south, east, north)}


def _feature(west: float, south: float, east: float, north: float) -> dict:
    return {"type": "Feature", "properties": {}, "geometry": _polygon(west, south, east, north)}


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


def _assert_demo_bounds(aoi: Aoi) -> None:
    assert aoi.bbox is not None
    assert aoi.bbox.west == pytest.approx(_WEST)
    assert aoi.bbox.south == pytest.approx(_SOUTH)
    assert aoi.bbox.east == pytest.approx(_EAST)
    assert aoi.bbox.north == pytest.approx(_NORTH)


def test_geojson_geometry_polygon(tmp_path: Path) -> None:
    path = _write(tmp_path, "geom.geojson", _polygon(_WEST, _SOUTH, _EAST, _NORTH))
    aoi = load_aoi_from_geojson(path)
    assert aoi.role is AoiRole.PROCESSING_AOI
    assert aoi.source is AoiSource.VECTOR_FILE
    _assert_demo_bounds(aoi)


def test_geojson_feature_polygon(tmp_path: Path) -> None:
    path = _write(tmp_path, "feature.geojson", _feature(_WEST, _SOUTH, _EAST, _NORTH))
    _assert_demo_bounds(load_aoi_from_geojson(path))


def test_geojson_feature_collection_merges_bounds(tmp_path: Path) -> None:
    # Two disjoint polygons; the merged bounds must span the union of both.
    fc = {
        "type": "FeatureCollection",
        "features": [
            _feature(110.1, 30.8, 110.3, 31.0),
            _feature(110.4, 31.0, 110.6, 31.2),
        ],
    }
    path = _write(tmp_path, "fc.geojson", fc)
    _assert_demo_bounds(load_aoi_from_geojson(path))


def test_wkt_polygon() -> None:
    _assert_demo_bounds(load_aoi_from_wkt(_rect_wkt(_WEST, _SOUTH, _EAST, _NORTH)))


def test_wkt_multipolygon() -> None:
    wkt = (
        "MULTIPOLYGON ("
        "((110.1 30.8, 110.3 30.8, 110.3 31.0, 110.1 31.0, 110.1 30.8)), "
        "((110.4 31.0, 110.6 31.0, 110.6 31.2, 110.4 31.2, 110.4 31.0)))"
    )
    _assert_demo_bounds(load_aoi_from_wkt(wkt))


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_geojson(tmp_path / "nope.geojson")


def test_empty_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.geojson", "")
    with pytest.raises(InputValidationError):
        load_aoi_from_geojson(path)


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.geojson", "{not valid json")
    with pytest.raises(InputValidationError):
        load_aoi_from_geojson(path)


def test_empty_wkt_raises() -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_wkt("   ")


def test_invalid_wkt_raises() -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_wkt("POLYGON (oops)")


def test_geojson_linestring_rejected(tmp_path: Path) -> None:
    geom = {"type": "LineString", "coordinates": [[110.1, 30.8], [110.6, 31.2]]}
    path = _write(tmp_path, "line.geojson", geom)
    with pytest.raises(InputValidationError):
        load_aoi_from_geojson(path)


def test_wkt_point_rejected() -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_wkt("POINT (110.1 30.8)")


def test_wkt_geometrycollection_rejected() -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_wkt("GEOMETRYCOLLECTION (POINT (110.1 30.8))")


def test_out_of_range_coordinates_rejected() -> None:
    # Longitude 200 is outside [-180, 180]; BBox validation must reject the bounds.
    wkt = "POLYGON ((200 30.8, 201 30.8, 201 31.2, 200 31.2, 200 30.8))"
    with pytest.raises(InputValidationError):
        load_aoi_from_wkt(wkt)


def test_non_wgs84_crs_rejected(tmp_path: Path) -> None:
    payload = _polygon(_WEST, _SOUTH, _EAST, _NORTH)
    payload["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32649"}}
    path = _write(tmp_path, "utm.geojson", payload)
    with pytest.raises(InputValidationError):
        load_aoi_from_geojson(path)


def test_explicit_wgs84_crs_accepted(tmp_path: Path) -> None:
    payload = _polygon(_WEST, _SOUTH, _EAST, _NORTH)
    payload["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}
    path = _write(tmp_path, "crs84.geojson", payload)
    _assert_demo_bounds(load_aoi_from_geojson(path))


def test_geometry_to_processing_aoi_rejects_empty() -> None:
    with pytest.raises(InputValidationError):
        geometry_to_processing_aoi(Polygon())
