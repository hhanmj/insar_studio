"""Tests for offline AOI import from Shapefile / KML / KMZ (Task 048).

Covers the happy paths (a single polygon and a multi-part polygon shapefile, a
KML Polygon, a KMZ-wrapped KML), the dispatcher
:func:`~insar_prep.processing.aoi_vector.load_aoi_from_file`, and the error
paths (missing file, wrong extension, projected / non-WGS84 ``.prj``, non-areal
geometry, malformed XML, non-zip KMZ). All fixtures are generated in-test with
the standard library only -- no sample data files and no extra dependencies.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi
from insar_prep.processing.aoi_vector import (
    load_aoi_from_file,
    load_aoi_from_kml,
    load_aoi_from_kmz,
    load_aoi_from_shapefile,
)

_WEST, _SOUTH, _EAST, _NORTH = 110.1, 30.8, 110.6, 31.2

_WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
    '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
_PROJECTED_PRJ = (
    'PROJCS["WGS_1984_UTM_Zone_49N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'UNIT["Meter",1.0]]'
)
_CGCS2000_PRJ = (
    'GEOGCS["GCS_China_Geodetic_Coordinate_System_2000",DATUM["D_China_2000",'
    'SPHEROID["CGCS2000",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]]'
)


def _rect(west: float, south: float, east: float, north: float) -> list[tuple[float, float]]:
    return [(west, south), (east, south), (east, north), (west, north), (west, south)]


def _write_polygon_shapefile(
    path: Path, rings: list[list[tuple[float, float]]], *, prj_text: str | None = _WGS84_PRJ
) -> Path:
    """Write a minimal ESRI polygon shapefile (one record, one or more parts)."""
    all_pts = [pt for ring in rings for pt in ring]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    num_parts = len(rings)
    num_points = len(all_pts)
    offsets: list[int] = []
    acc = 0
    for ring in rings:
        offsets.append(acc)
        acc += len(ring)

    content = struct.pack("<i", 5)
    content += struct.pack("<4d", xmin, ymin, xmax, ymax)
    content += struct.pack("<ii", num_parts, num_points)
    content += struct.pack(f"<{num_parts}i", *offsets)
    for x, y in all_pts:
        content += struct.pack("<2d", x, y)

    record = struct.pack(">ii", 1, len(content) // 2) + content
    file_length_words = (100 + len(record)) // 2
    header = struct.pack(">i", 9994) + b"\x00" * 20 + struct.pack(">i", file_length_words)
    header += struct.pack("<i", 1000) + struct.pack("<i", 5)
    header += struct.pack("<4d", xmin, ymin, xmax, ymax) + struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)
    path.write_bytes(header + record)
    if prj_text is not None:
        path.with_suffix(".prj").write_text(prj_text, encoding="utf-8")
    return path


def _write_point_shapefile(path: Path) -> Path:
    """Write a header-only POINT shapefile (shape type 1) to exercise rejection."""
    header = struct.pack(">i", 9994) + b"\x00" * 20 + struct.pack(">i", 50)
    header += struct.pack("<i", 1000) + struct.pack("<i", 1)
    header += struct.pack("<4d", 0.0, 0.0, 0.0, 0.0) + struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)
    path.write_bytes(header)
    return path


def _kml_text(coords: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>'
        f"<outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"
    )


_DEMO_KML_COORDS = "110.1,30.8,0 110.6,30.8,0 110.6,31.2,0 110.1,31.2,0 110.1,30.8,0"


def _assert_demo_bounds(aoi: Aoi) -> None:
    assert aoi.bbox is not None
    assert aoi.bbox.west == pytest.approx(_WEST)
    assert aoi.bbox.south == pytest.approx(_SOUTH)
    assert aoi.bbox.east == pytest.approx(_EAST)
    assert aoi.bbox.north == pytest.approx(_NORTH)


# --------------------------------------------------------------------------- #
# Shapefile
# --------------------------------------------------------------------------- #
def test_shapefile_polygon(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(tmp_path / "aoi.shp", [_rect(_WEST, _SOUTH, _EAST, _NORTH)])
    aoi = load_aoi_from_shapefile(shp)
    assert aoi.role is AoiRole.PROCESSING_AOI
    assert aoi.source is AoiSource.VECTOR_FILE
    _assert_demo_bounds(aoi)


def test_shapefile_multipart_merges_bounds(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(
        tmp_path / "multi.shp",
        [_rect(110.1, 30.8, 110.3, 31.0), _rect(110.4, 31.0, 110.6, 31.2)],
    )
    _assert_demo_bounds(load_aoi_from_shapefile(shp))


def test_shapefile_no_prj_assumes_wgs84(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(
        tmp_path / "noprj.shp", [_rect(_WEST, _SOUTH, _EAST, _NORTH)], prj_text=None
    )
    _assert_demo_bounds(load_aoi_from_shapefile(shp))


def test_shapefile_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_shapefile(tmp_path / "nope.shp")


def test_shapefile_wrong_extension_raises(tmp_path: Path) -> None:
    other = tmp_path / "aoi.txt"
    other.write_text("not a shapefile", encoding="utf-8")
    with pytest.raises(InputValidationError):
        load_aoi_from_shapefile(other)


def test_shapefile_projected_prj_rejected(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(
        tmp_path / "utm.shp", [_rect(_WEST, _SOUTH, _EAST, _NORTH)], prj_text=_PROJECTED_PRJ
    )
    with pytest.raises(InputValidationError):
        load_aoi_from_shapefile(shp)


def test_shapefile_non_wgs84_geographic_prj_rejected(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(
        tmp_path / "cgcs.shp", [_rect(_WEST, _SOUTH, _EAST, _NORTH)], prj_text=_CGCS2000_PRJ
    )
    with pytest.raises(InputValidationError):
        load_aoi_from_shapefile(shp)


def test_shapefile_point_type_rejected(tmp_path: Path) -> None:
    shp = _write_point_shapefile(tmp_path / "point.shp")
    with pytest.raises(InputValidationError):
        load_aoi_from_shapefile(shp)


# --------------------------------------------------------------------------- #
# KML
# --------------------------------------------------------------------------- #
def test_kml_polygon(tmp_path: Path) -> None:
    kml = tmp_path / "aoi.kml"
    kml.write_text(_kml_text(_DEMO_KML_COORDS), encoding="utf-8")
    aoi = load_aoi_from_kml(kml)
    assert aoi.source is AoiSource.VECTOR_FILE
    _assert_demo_bounds(aoi)


def test_kml_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_kml(tmp_path / "nope.kml")


def test_kml_without_polygon_rejected(tmp_path: Path) -> None:
    kml = tmp_path / "point.kml"
    kml.write_text(
        '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Placemark>'
        "<Point><coordinates>110.1,30.8,0</coordinates></Point></Placemark></kml>",
        encoding="utf-8",
    )
    with pytest.raises(InputValidationError):
        load_aoi_from_kml(kml)


def test_kml_invalid_xml_rejected(tmp_path: Path) -> None:
    kml = tmp_path / "bad.kml"
    kml.write_text("<kml><Polygon>", encoding="utf-8")
    with pytest.raises(InputValidationError):
        load_aoi_from_kml(kml)


# --------------------------------------------------------------------------- #
# KMZ
# --------------------------------------------------------------------------- #
def test_kmz_polygon(tmp_path: Path) -> None:
    kmz = tmp_path / "aoi.kmz"
    with zipfile.ZipFile(kmz, "w") as archive:
        archive.writestr("doc.kml", _kml_text(_DEMO_KML_COORDS))
    _assert_demo_bounds(load_aoi_from_kmz(kmz))


def test_kmz_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        load_aoi_from_kmz(tmp_path / "nope.kmz")


def test_kmz_without_kml_rejected(tmp_path: Path) -> None:
    kmz = tmp_path / "empty.kmz"
    with zipfile.ZipFile(kmz, "w") as archive:
        archive.writestr("readme.txt", "no kml here")
    with pytest.raises(InputValidationError):
        load_aoi_from_kmz(kmz)


def test_kmz_not_a_zip_rejected(tmp_path: Path) -> None:
    kmz = tmp_path / "fake.kmz"
    kmz.write_bytes(b"this is not a zip archive")
    with pytest.raises(InputValidationError):
        load_aoi_from_kmz(kmz)


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def test_load_aoi_from_file_dispatches_shapefile(tmp_path: Path) -> None:
    shp = _write_polygon_shapefile(tmp_path / "d.shp", [_rect(_WEST, _SOUTH, _EAST, _NORTH)])
    _assert_demo_bounds(load_aoi_from_file(shp))


def test_load_aoi_from_file_dispatches_kml(tmp_path: Path) -> None:
    kml = tmp_path / "d.kml"
    kml.write_text(_kml_text(_DEMO_KML_COORDS), encoding="utf-8")
    _assert_demo_bounds(load_aoi_from_file(kml))


def test_load_aoi_from_file_dispatches_kmz(tmp_path: Path) -> None:
    kmz = tmp_path / "d.kmz"
    with zipfile.ZipFile(kmz, "w") as archive:
        archive.writestr("doc.kml", _kml_text(_DEMO_KML_COORDS))
    _assert_demo_bounds(load_aoi_from_file(kmz))


def test_load_aoi_from_file_dispatches_geojson(tmp_path: Path) -> None:
    geojson = tmp_path / "d.geojson"
    geojson.write_text(
        '{"type": "Polygon", "coordinates": '
        "[[[110.1, 30.8], [110.6, 30.8], [110.6, 31.2], [110.1, 31.2], [110.1, 30.8]]]}",
        encoding="utf-8",
    )
    _assert_demo_bounds(load_aoi_from_file(geojson))


def test_load_aoi_from_file_unknown_extension_raises(tmp_path: Path) -> None:
    other = tmp_path / "aoi.gpkg"
    other.write_text("unsupported", encoding="utf-8")
    with pytest.raises(InputValidationError):
        load_aoi_from_file(other)
