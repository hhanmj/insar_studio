"""AOI import from Shapefile / KML / KMZ vector files (Task 048).

Offline helpers that build a Processing :class:`~insar_prep.core.models.Aoi`
from an ESRI Shapefile (``.shp``), a KML file (``.kml``), or a zipped KML
(``.kmz``). They extend the GeoJSON/WKT importers in
:mod:`insar_prep.processing.aoi_import` and reuse its
:func:`~insar_prep.processing.aoi_import.geometry_to_processing_aoi` validator so
every source ends up going through the same checks.

Design constraints (kept identical to the GeoJSON/WKT importer):

* **small dependency surface** -- ``struct`` parses the shapefile geometry, the
  standard-library ``xml.etree`` parses KML, and ``zipfile`` unpacks KMZ. When a
  Shapefile has ``.prj``, ``pyproj`` is used to transform it to EPSG:4326.
* **AOI output is always lon/lat**. Shapefiles without ``.prj`` are treated as
  WGS84 only when their bounds already look like longitude/latitude. KML/KMZ are
  WGS84 lon/lat by specification.
* Only areal geometries (``Polygon`` / ``MultiPolygon``) are accepted; the
  Processing AOI bbox is taken from the merged geometry bounds.

Polygon interior rings (holes) are not preserved -- each ring is treated as a
filled polygon and all rings are merged (``unary_union``). This is intentional:
an AOI only uses the outer bounds downstream, so filling holes never changes the
result while keeping the parser simple and robust.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from shapely.geometry import Polygon
from shapely.ops import transform as shapely_transform, unary_union

from insar_prep.core.enums import AoiSource
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.processing.aoi_import import geometry_to_processing_aoi

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry

    from insar_prep.core.models import Aoi

logger = get_logger("processing.aoi_vector")

# ESRI shapefile polygon shape-type codes (2D / Z / M). Points, polylines and
# multipatch are rejected: an AOI must be areal.
_SHP_POLYGON_TYPES = frozenset({5, 15, 25})
_SHP_NULL_TYPE = 0
_SHP_HEADER_SIZE = 100


def load_aoi_from_file(path: str | Path, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from any supported vector file, by extension.

    Dispatches on the lower-cased suffix: ``.shp`` -> shapefile, ``.kml`` ->
    KML, ``.kmz`` -> zipped KML, and ``.geojson`` / ``.json`` -> GeoJSON (handled
    by :mod:`insar_prep.processing.aoi_import`). Raises
    :class:`~insar_prep.core.exceptions.InputValidationError` (``AOI001``) for an
    unknown extension or any underlying parse/validation failure.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".shp":
        return load_aoi_from_shapefile(path, name=name)
    if suffix == ".kml":
        return load_aoi_from_kml(path, name=name)
    if suffix == ".kmz":
        return load_aoi_from_kmz(path, name=name)
    if suffix in (".geojson", ".json"):
        # Imported here to avoid a hard import cycle at module load time.
        from insar_prep.processing.aoi_import import load_aoi_from_geojson

        return load_aoi_from_geojson(path, name=name)
    raise InputValidationError(
        f"unsupported AOI vector file extension {suffix!r}; "
        "expected .shp, .kml, .kmz, .geojson, or .json",
        code=ErrorCode.AOI001,
    )


# --------------------------------------------------------------------------- #
# Shapefile (.shp)
# --------------------------------------------------------------------------- #
def load_aoi_from_shapefile(path: str | Path, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from an ESRI Shapefile (``.shp``).

    Reads polygon geometry directly from the ``.shp`` main file (the ``.shx``
    index is not required) and merges every polygon ring into one geometry. A
    sidecar ``.prj`` file, when present, is used to transform projected or
    non-WGS84 coordinates to EPSG:4326 before validation.
    """
    shp_path = Path(path)
    if shp_path.suffix.lower() != ".shp":
        raise InputValidationError(
            f"not a shapefile (.shp expected): {shp_path}", code=ErrorCode.AOI001
        )
    if not shp_path.is_file():
        raise InputValidationError(f"shapefile not found: {shp_path}", code=ErrorCode.AOI001)
    try:
        data = shp_path.read_bytes()
    except OSError as exc:
        raise InputValidationError(
            f"cannot read shapefile {shp_path}: {exc}", code=ErrorCode.AOI001
        ) from exc

    geometry = _geometry_from_shapefile_bytes(data, shp_path)
    return geometry_to_processing_aoi(geometry, source=AoiSource.VECTOR_FILE, name=name)


def _geometry_from_shapefile_bytes(data: bytes, shp_path: Path) -> BaseGeometry:
    if len(data) < _SHP_HEADER_SIZE:
        raise InputValidationError(
            f"shapefile is too short to be valid: {shp_path}", code=ErrorCode.AOI001
        )
    if struct.unpack(">i", data[0:4])[0] != 9994:
        raise InputValidationError(
            f"not a valid shapefile (bad magic number): {shp_path}", code=ErrorCode.AOI001
        )
    file_type = struct.unpack("<i", data[32:36])[0]
    if file_type != _SHP_NULL_TYPE and file_type not in _SHP_POLYGON_TYPES:
        raise InputValidationError(
            f"shapefile geometry type {file_type} is not a polygon; an AOI must be areal "
            f"(Polygon/MultiPolygon): {shp_path}",
            code=ErrorCode.AOI001,
        )

    polygons = _read_shapefile_polygons(data, shp_path)
    if not polygons:
        raise InputValidationError(
            f"shapefile contains no usable polygon geometry: {shp_path}", code=ErrorCode.AOI001
        )
    geometry = unary_union(polygons)
    if geometry.is_empty:
        raise InputValidationError(
            f"shapefile polygons merged to an empty geometry: {shp_path}", code=ErrorCode.AOI001
        )
    geometry = _normalise_shapefile_geometry_crs(geometry, shp_path)
    logger.debug("read %d polygon ring(s) from shapefile %s", len(polygons), shp_path)
    return geometry


def _read_shapefile_polygons(data: bytes, shp_path: Path) -> list[Polygon]:
    polygons: list[Polygon] = []
    offset = _SHP_HEADER_SIZE
    size = len(data)
    while offset + 8 <= size:
        # Record header: record number + content length, both big-endian, the
        # length being measured in 16-bit words.
        _record_number, content_len_words = struct.unpack(">ii", data[offset : offset + 8])
        content_start = offset + 8
        content_end = content_start + content_len_words * 2
        if content_end > size:
            break  # truncated trailing record; stop gracefully.
        content = data[content_start:content_end]
        offset = content_end
        if len(content) < 4:
            continue
        shape_type = struct.unpack("<i", content[0:4])[0]
        if shape_type == _SHP_NULL_TYPE:
            continue
        if shape_type not in _SHP_POLYGON_TYPES:
            raise InputValidationError(
                f"shapefile record geometry type {shape_type} is not a polygon: {shp_path}",
                code=ErrorCode.AOI001,
            )
        polygons.extend(_polygons_from_shapefile_record(content))
    return polygons


def _polygons_from_shapefile_record(content: bytes) -> list[Polygon]:
    # Polygon record layout after the 4-byte shape type: bbox (4 doubles),
    # numParts (int), numPoints (int), parts[numParts] (ints), then
    # points[numPoints] (pairs of doubles). Any trailing Z/M arrays are ignored.
    num_parts, num_points = struct.unpack("<ii", content[36:44])
    if num_parts <= 0 or num_points <= 0:
        return []
    parts_start = 44
    parts_end = parts_start + 4 * num_parts
    points_end = parts_end + 16 * num_points
    if points_end > len(content):
        return []
    parts = struct.unpack(f"<{num_parts}i", content[parts_start:parts_end])
    coords = struct.unpack(f"<{2 * num_points}d", content[parts_end:points_end])

    polygons: list[Polygon] = []
    ring_bounds = (*parts, num_points)
    for index in range(num_parts):
        start = ring_bounds[index]
        end = ring_bounds[index + 1]
        ring = [(coords[2 * i], coords[2 * i + 1]) for i in range(start, end)]
        polygon = _polygon_from_ring(ring)
        if polygon is not None:
            polygons.append(polygon)
    return polygons


def _polygon_from_ring(ring: list[tuple[float, float]]) -> Polygon | None:
    if len(ring) < 4:
        return None
    polygon = Polygon(ring)
    if not polygon.is_valid:
        repaired = polygon.buffer(0)
        if repaired.is_empty or not isinstance(repaired, Polygon):
            return polygon if not polygon.is_empty else None
        return repaired
    return polygon


def _check_shapefile_prj(shp_path: Path) -> None:
    _shapefile_crs_from_prj(shp_path)


def _normalise_shapefile_geometry_crs(geometry: BaseGeometry, shp_path: Path) -> BaseGeometry:
    prj_path = shp_path.with_suffix(".prj")
    crs = _shapefile_crs_from_prj(shp_path)
    if crs is None:
        _ensure_shapefile_lonlat_bounds(geometry, shp_path, has_prj=False)
        return geometry
    try:
        from pyproj import CRS, Transformer
    except Exception as exc:  # noqa: BLE001
        raise InputValidationError(
            "Shapefile 带有 .prj，但当前环境缺少 pyproj，无法自动转换坐标。",
            code=ErrorCode.AOI001,
        ) from exc
    try:
        transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        geometry = shapely_transform(transformer.transform, geometry)
    except Exception as exc:  # noqa: BLE001
        raise InputValidationError(
            f"Shapefile 坐标转换失败：{prj_path.name}，请确认 .prj 与 .shp 坐标一致。",
            code=ErrorCode.AOI001,
        ) from exc
    _ensure_shapefile_lonlat_bounds(geometry, shp_path, has_prj=True)
    return geometry


def _shapefile_crs_from_prj(shp_path: Path):
    prj_text = _read_shapefile_prj_text(shp_path)
    if not prj_text:
        return None
    try:
        from pyproj import CRS
    except Exception as exc:  # noqa: BLE001
        if _prj_text_looks_wgs84_like(prj_text):
            return None
        raise InputValidationError(
            "Shapefile 坐标不是经纬度；当前环境缺少 pyproj，无法根据同名 .prj 自动转换。",
            code=ErrorCode.AOI001,
        ) from exc
    try:
        return CRS.from_wkt(prj_text)
    except Exception as exc:  # noqa: BLE001
        raise InputValidationError(
            f"Shapefile .prj 坐标系无法识别：{shp_path.with_suffix('.prj').name}",
            code=ErrorCode.AOI001,
        ) from exc


def _read_shapefile_prj_text(shp_path: Path) -> str:
    prj_path = shp_path.with_suffix(".prj")
    if not prj_path.is_file():
        return ""
    try:
        return prj_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _prj_text_looks_wgs84_like(prj_text: str) -> bool:
    normalized = prj_text.upper()
    return "PROJCS" not in normalized and any(
        token in normalized
        for token in (
            "WGS_1984",
            "WGS84",
            "4326",
            "CRS84",
            "CGCS2000",
            "CHINA_GEODETIC_COORDINATE_SYSTEM_2000",
            "4490",
        )
    )


def _ensure_shapefile_lonlat_bounds(
    geometry: BaseGeometry, shp_path: Path, *, has_prj: bool
) -> None:
    minx, miny, maxx, maxy = geometry.bounds
    valid = -180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90
    if valid:
        return
    if has_prj:
        raise InputValidationError(
            f"Shapefile 根据 .prj 转换后的坐标仍不在经纬度范围内：{shp_path.name}",
            code=ErrorCode.AOI001,
        )
    raise InputValidationError(
        f"该 Shapefile 坐标不是经纬度且缺少同名 .prj，无法自动转换：{shp_path.name}。"
        "请保留同目录下同名 .prj 文件后重新导入。",
        code=ErrorCode.AOI001,
    )


# --------------------------------------------------------------------------- #
# KML (.kml) and KMZ (.kmz)
# --------------------------------------------------------------------------- #
def load_aoi_from_kml(path: str | Path, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from a KML file (WGS84 lon/lat by KML spec)."""
    kml_path = Path(path)
    if not kml_path.is_file():
        raise InputValidationError(f"KML file not found: {kml_path}", code=ErrorCode.AOI001)
    try:
        raw = kml_path.read_bytes()
    except OSError as exc:
        raise InputValidationError(
            f"cannot read KML file {kml_path}: {exc}", code=ErrorCode.AOI001
        ) from exc
    geometry = _geometry_from_kml_bytes(raw, str(kml_path))
    return geometry_to_processing_aoi(geometry, source=AoiSource.VECTOR_FILE, name=name)


def load_aoi_from_kmz(path: str | Path, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from a zipped KML (``.kmz``).

    The first ``.kml`` entry inside the archive (``doc.kml`` by convention) is
    parsed; the geometry rules are identical to :func:`load_aoi_from_kml`.
    """
    kmz_path = Path(path)
    if not kmz_path.is_file():
        raise InputValidationError(f"KMZ file not found: {kmz_path}", code=ErrorCode.AOI001)
    try:
        with zipfile.ZipFile(kmz_path) as archive:
            kml_name = _first_kml_name(archive.namelist())
            if kml_name is None:
                raise InputValidationError(
                    f"KMZ archive contains no .kml entry: {kmz_path}", code=ErrorCode.AOI001
                )
            raw = archive.read(kml_name)
    except zipfile.BadZipFile as exc:
        raise InputValidationError(
            f"invalid KMZ (not a zip archive): {kmz_path}", code=ErrorCode.AOI001
        ) from exc
    geometry = _geometry_from_kml_bytes(raw, f"{kmz_path}!{kml_name}")
    return geometry_to_processing_aoi(geometry, source=AoiSource.VECTOR_FILE, name=name)


def _first_kml_name(names: list[str]) -> str | None:
    # Prefer the conventional doc.kml; otherwise take the first .kml entry.
    kml_names = [n for n in names if n.lower().endswith(".kml")]
    for candidate in kml_names:
        if Path(candidate).name.lower() == "doc.kml":
            return candidate
    return kml_names[0] if kml_names else None


def _geometry_from_kml_bytes(raw: bytes, source: str) -> BaseGeometry:
    try:
        root = ET.fromstring(raw)  # noqa: S314 - trusted local file, no DTD/network entities used
    except ET.ParseError as exc:
        raise InputValidationError(
            f"invalid KML (not well-formed XML): {source}: {exc}", code=ErrorCode.AOI001
        ) from exc
    polygons: list[Polygon] = []
    for polygon_elem in _iter_local(root, "Polygon"):
        ring = _kml_outer_ring(polygon_elem)
        polygon = _polygon_from_ring(ring) if ring else None
        if polygon is not None:
            polygons.append(polygon)
    if not polygons:
        raise InputValidationError(
            f"KML contains no Polygon geometry (an AOI must be areal): {source}",
            code=ErrorCode.AOI001,
        )
    geometry = unary_union(polygons)
    if geometry.is_empty:
        raise InputValidationError(
            f"KML polygons merged to an empty geometry: {source}", code=ErrorCode.AOI001
        )
    logger.debug("read %d polygon(s) from KML %s", len(polygons), source)
    return geometry


def _kml_outer_ring(polygon_elem: ET.Element) -> list[tuple[float, float]]:
    outer = _find_local(polygon_elem, "outerBoundaryIs")
    container = outer if outer is not None else polygon_elem
    coords_elem = _find_local(container, "coordinates")
    if coords_elem is None or not coords_elem.text:
        return []
    return _parse_kml_coordinates(coords_elem.text)


def _parse_kml_coordinates(text: str) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        ring.append((lon, lat))
    return ring


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_local(elem: ET.Element, name: str):
    for child in elem.iter():
        if _local_name(child.tag) == name:
            yield child


def _find_local(elem: ET.Element, name: str) -> ET.Element | None:
    for child in elem.iter():
        if _local_name(child.tag) == name:
            return child
    return None
