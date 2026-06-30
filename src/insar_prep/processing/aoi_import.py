"""AOI import from GeoJSON / WKT for the prepare workflow (Task 029).

Offline helpers that build a Processing :class:`~insar_prep.core.models.Aoi`
from either a GeoJSON file or a WKT string, reusing the existing ``shapely``
dependency plus the standard-library ``json`` module. No new dependencies, no
``geopandas``/``fiona``/``rasterio``/``pyproj``/GDAL, no shapefile/KML/
GeoPackage, no network, and no coordinate transforms.

Only WGS84 lon/lat (``EPSG:4326``) ``Polygon`` / ``MultiPolygon`` geometries are
accepted; the Processing AOI bbox is taken from the geometry bounds. The
existing Download-AOI buffer logic (see :mod:`insar_prep.processing.aoi`) is left
untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from shapely import wkt as shapely_wkt
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.ops import polygonize, unary_union

from insar_prep.core.enums import AoiRole, AoiSource
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.core.models import Aoi, BBox

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry

logger = get_logger("processing.aoi_import")

# Only areal geometries are stored as an AOI. Some authoritative boundary files
# ship closed boundaries as linework, so we accept line geometries at import time
# and polygonize them before validation.
SUPPORTED_GEOMETRY_TYPES = ("Polygon", "MultiPolygon")
IMPORTABLE_GEOMETRY_TYPES = (
    "Polygon",
    "MultiPolygon",
    "LineString",
    "MultiLineString",
    "GeometryCollection",
)


def load_aoi_from_geojson(path: str | Path, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from a GeoJSON file (EPSG:4326 lon/lat only).

    Accepts a bare Geometry, a Feature, or a FeatureCollection; for a
    FeatureCollection every feature geometry is merged (``unary_union``) and the
    combined bounds become the AOI bbox. Raises :class:`InputValidationError`
    (``AOI001``) for a missing file, invalid JSON, an unsupported geometry type,
    a non-WGS84 ``crs`` member, an empty/invalid geometry, or out-of-range
    coordinates.
    """
    geojson_path = Path(path)
    if not geojson_path.is_file():
        raise InputValidationError(f"GeoJSON file not found: {geojson_path}", code=ErrorCode.AOI001)
    try:
        raw = geojson_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputValidationError(
            f"cannot read GeoJSON file {geojson_path}: {exc}", code=ErrorCode.AOI001
        ) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise InputValidationError(
            f"invalid GeoJSON (not valid JSON): {exc}", code=ErrorCode.AOI001
        ) from exc
    if not isinstance(data, dict):
        raise InputValidationError(
            "invalid GeoJSON: the top-level value must be a JSON object",
            code=ErrorCode.AOI001,
        )
    _reject_non_wgs84_crs(data)
    geometry = _geometry_from_geojson(data)
    return geometry_to_processing_aoi(geometry, source=AoiSource.VECTOR_FILE, name=name)


def load_aoi_from_wkt(wkt_text: str, *, name: str | None = None) -> Aoi:
    """Build a Processing AOI from a WKT string (EPSG:4326 lon/lat only).

    Only ``Polygon`` / ``MultiPolygon`` are accepted. An empty string, malformed
    WKT, or an unsupported geometry type (including ``GeometryCollection``)
    raises :class:`InputValidationError` (``AOI001``).
    """
    if not wkt_text or not wkt_text.strip():
        raise InputValidationError("WKT string is empty", code=ErrorCode.AOI001)
    try:
        geometry = shapely_wkt.loads(wkt_text)
    except (ShapelyError, ValueError, TypeError) as exc:
        raise InputValidationError(f"invalid WKT geometry: {exc}", code=ErrorCode.AOI001) from exc
    return geometry_to_processing_aoi(geometry, source=AoiSource.VECTOR_FILE, name=name)


def geometry_to_processing_aoi(
    geometry: BaseGeometry,
    *,
    source: AoiSource = AoiSource.VECTOR_FILE,
    name: str | None = None,
) -> Aoi:
    """Validate a shapely geometry and wrap its bounds as a Processing AOI."""
    _validate_geometry(geometry)
    bbox = _bbox_from_geometry(geometry)
    logger.debug(
        "built processing AOI from %s bounds %s (name=%r)",
        geometry.geom_type,
        geometry.bounds,
        name,
    )
    return Aoi(source=source, role=AoiRole.PROCESSING_AOI, bbox=bbox)


def _geometry_from_geojson(data: dict[str, Any]) -> BaseGeometry:
    obj_type = data.get("type")
    if not isinstance(obj_type, str):
        raise InputValidationError(
            "invalid GeoJSON: missing or non-string 'type' member", code=ErrorCode.AOI001
        )
    if obj_type == "FeatureCollection":
        features = data.get("features")
        if not isinstance(features, list) or not features:
            raise InputValidationError(
                "invalid GeoJSON FeatureCollection: 'features' must be a non-empty array",
                code=ErrorCode.AOI001,
            )
        geometries = [_geometry_from_feature(feature) for feature in features]
        return _coerce_to_areal_geometry(unary_union(geometries))
    if obj_type == "Feature":
        return _coerce_to_areal_geometry(_geometry_from_feature(data))
    if obj_type in IMPORTABLE_GEOMETRY_TYPES:
        return _coerce_to_areal_geometry(_shape_from_mapping(data))
    raise InputValidationError(
        f"不支持的 GeoJSON 几何类型 {obj_type!r}；请提供 Polygon/MultiPolygon，"
        "或闭合的 LineString/MultiLineString 行政边界",
        code=ErrorCode.AOI001,
    )


def _geometry_from_feature(feature: Any) -> BaseGeometry:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise InputValidationError("invalid GeoJSON Feature object", code=ErrorCode.AOI001)
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise InputValidationError(
            "invalid GeoJSON Feature: missing 'geometry' object", code=ErrorCode.AOI001
        )
    geom_type = geometry.get("type")
    if geom_type not in IMPORTABLE_GEOMETRY_TYPES:
        raise InputValidationError(
            f"不支持的 GeoJSON 几何类型 {geom_type!r}；请提供 Polygon/MultiPolygon，"
            "或闭合的 LineString/MultiLineString 行政边界",
            code=ErrorCode.AOI001,
        )
    return _shape_from_mapping(geometry)


def _shape_from_mapping(geometry: dict[str, Any]) -> BaseGeometry:
    try:
        return shape(geometry)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InputValidationError(
            f"invalid GeoJSON geometry: {exc}", code=ErrorCode.AOI001
        ) from exc


def _validate_geometry(geometry: BaseGeometry) -> None:
    if geometry is None or geometry.is_empty:
        raise InputValidationError("AOI geometry is empty", code=ErrorCode.AOI001)
    if geometry.geom_type not in SUPPORTED_GEOMETRY_TYPES:
        raise InputValidationError(
            f"unsupported geometry type {geometry.geom_type!r}; expected Polygon or MultiPolygon",
            code=ErrorCode.AOI001,
        )
    if not geometry.is_valid:
        raise InputValidationError("AOI geometry is not valid", code=ErrorCode.AOI001)


def _coerce_to_areal_geometry(geometry: BaseGeometry) -> BaseGeometry:
    """Return a Polygon/MultiPolygon, polygonizing closed line boundaries if needed."""
    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.geom_type in SUPPORTED_GEOMETRY_TYPES:
        return geometry
    if geometry.geom_type in {"LineString", "MultiLineString", "LinearRing"}:
        polygons = list(polygonize(geometry))
        if polygons:
            return unary_union(polygons)
    if geometry.geom_type == "GeometryCollection":
        areal_parts: list[BaseGeometry] = []
        line_parts: list[BaseGeometry] = []
        for part in getattr(geometry, "geoms", []):
            if part.geom_type in SUPPORTED_GEOMETRY_TYPES:
                areal_parts.append(part)
            elif part.geom_type in {"LineString", "MultiLineString", "LinearRing"}:
                line_parts.append(part)
        polygons = list(polygonize(line_parts)) if line_parts else []
        merged = [*areal_parts, *polygons]
        if merged:
            return unary_union(merged)
    raise InputValidationError(
        f"无法从 {geometry.geom_type!r} 生成 AOI 面；如果这是行政边界线，请确认线闭合，"
        "或提供 Polygon/MultiPolygon 文件",
        code=ErrorCode.AOI001,
    )


def _bbox_from_geometry(geometry: BaseGeometry) -> BBox:
    minx, miny, maxx, maxy = geometry.bounds
    try:
        return BBox(west=minx, east=maxx, south=miny, north=maxy)
    except (ValidationError, ValueError) as exc:
        raise InputValidationError(
            f"AOI bounds are out of range or degenerate: {exc}", code=ErrorCode.AOI001
        ) from exc


def _reject_non_wgs84_crs(data: dict[str, Any]) -> None:
    crs = data.get("crs")
    if crs is None:
        return  # RFC 7946 GeoJSON is always WGS84 lon/lat.
    name: Any = None
    if isinstance(crs, dict):
        properties = crs.get("properties")
        if isinstance(properties, dict):
            name = properties.get("name")
    if not isinstance(name, str) or not _is_wgs84_crs_name(name):
        raise InputValidationError(
            f"unsupported GeoJSON CRS {crs!r}; only EPSG:4326 (WGS84 lon/lat) is allowed",
            code=ErrorCode.AOI001,
        )


def _is_wgs84_crs_name(name: str) -> bool:
    normalized = name.strip().upper()
    return "4326" in normalized or "CRS84" in normalized
