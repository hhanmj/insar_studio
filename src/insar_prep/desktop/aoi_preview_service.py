from __future__ import annotations

import base64
import binascii
import io
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from insar_prep.core.exceptions import InsarPrepError
from insar_prep.desktop.helpers import _error, _error_msg

_AOI_PREVIEW_FEATURE_LIMIT = 500


def _missing_dep(feature: str, exc: Exception) -> dict:
    """Helper to format python dynamic import dependency errors."""
    return _error_msg(f"{feature}需要安装额外的地理空间依赖：{exc}", "GUI003")


def _dump(obj: Any) -> Any:
    """Helper to convert Pydantic models to JSON-friendly dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _geojson_from_aoi_file(path: str | Path) -> dict | None:
    """Return displayable GeoJSON for supported local AOI files."""
    source = Path(path)
    suffix = source.suffix.lower()
    try:
        if suffix in {".geojson", ".json"}:
            data = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            from shapely.geometry import mapping

            from insar_prep.processing.aoi_import import _geometry_from_geojson

            geometry = _geometry_from_geojson(data)
            return dict(mapping(geometry))
        geometry = None
        if suffix == ".shp":
            from insar_prep.processing.aoi_vector import (
                _check_shapefile_prj,
                _geometry_from_shapefile_bytes,
            )

            _check_shapefile_prj(source)
            geometry = _geometry_from_shapefile_bytes(source.read_bytes(), source)
        elif suffix == ".kml":
            from insar_prep.processing.aoi_vector import _geometry_from_kml_bytes

            geometry = _geometry_from_kml_bytes(source.read_bytes(), str(source))
        elif suffix == ".kmz":
            import zipfile

            from insar_prep.processing.aoi_vector import _first_kml_name, _geometry_from_kml_bytes

            with zipfile.ZipFile(source) as archive:
                kml_name = _first_kml_name(archive.namelist())
                if kml_name is None:
                    return None
                geometry = _geometry_from_kml_bytes(archive.read(kml_name), f"{source}!{kml_name}")
        if geometry is None:
            return None
        from shapely.geometry import mapping

        return dict(mapping(geometry))
    except (FileNotFoundError, ValueError, json.JSONDecodeError, KeyError, AttributeError):
        return None


def _geojson_feature_count_from_file(path: str | Path) -> int | None:
    source = Path(path)
    if source.suffix.lower() not in {".geojson", ".json"}:
        return None
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("type") == "FeatureCollection":
        features = data.get("features")
        return len(features) if isinstance(features, list) else None
    if data.get("type") == "Feature":
        return 1
    return 1 if data.get("type") else None


def _read_aoi_vector_features(path: str | Path) -> list[dict[str, Any]]:
    """Read per-feature AOI geometry/properties from supported local vector files."""
    source = Path(path)
    suffix = source.suffix.lower()
    if not source.is_file():
        raise FileNotFoundError(f"边界文件不存在：{source}")
    if suffix in {".geojson", ".json"}:
        return _read_geojson_aoi_features(source)
    if suffix == ".shp":
        return _read_shapefile_aoi_features(source)
    if suffix == ".kml":
        return _read_kml_aoi_features(source.read_bytes(), str(source))
    if suffix == ".kmz":
        import zipfile

        from insar_prep.processing.aoi_vector import _first_kml_name

        with zipfile.ZipFile(source) as archive:
            kml_name = _first_kml_name(archive.namelist())
            if kml_name is None:
                raise ValueError(f"KMZ 文件内没有 .kml：{source}")
            return _read_kml_aoi_features(archive.read(kml_name), f"{source}!{kml_name}")
    raise ValueError("暂不支持该边界格式；请使用 .shp、.kml、.kmz、.geojson 或 .json。")


def _read_aoi_vector_features_from_text(file_name: str, text: str) -> list[dict[str, Any]]:
    """Read AOI features from browser-dragged text content."""
    source = Path(str(file_name or "boundary"))
    suffix = source.suffix.lower()
    raw = str(text or "")
    if suffix not in {".geojson", ".json", ".kml"}:
        if suffix in {".shp", ".kmz"}:
            raise ValueError(
                "该格式需要按二进制读取；请重新拖入文件，或点击“上传本地边界”选择文件。"
            )
        raise ValueError("仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。")
    if not raw.strip():
        raise ValueError("边界文件内容为空。")
    if suffix in {".geojson", ".json"}:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"GeoJSON/JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列附近格式不正确。"
            ) from exc
        return _read_geojson_aoi_features_from_data(data)
    return _read_kml_aoi_features(raw.encode("utf-8"), source.name)


def _read_aoi_vector_features_from_bytes(file_name: str, raw: bytes) -> list[dict[str, Any]]:
    """Read AOI features from browser-dragged binary content."""
    source = Path(str(file_name or "boundary"))
    suffix = source.suffix.lower()
    if not raw:
        raise ValueError("边界文件内容为空。")
    if suffix == ".shp":
        with tempfile.TemporaryDirectory(prefix="insar_aoi_") as tmp:
            shp_path = Path(tmp) / (source.name or "boundary.shp")
            shp_path.write_bytes(raw)
            return _read_shapefile_aoi_features(shp_path)
    if suffix == ".kmz":
        import zipfile

        from insar_prep.processing.aoi_vector import _first_kml_name

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                kml_name = _first_kml_name(archive.namelist())
                if kml_name is None:
                    raise ValueError("KMZ 文件内没有 .kml 文件。")
                return _read_kml_aoi_features(archive.read(kml_name), f"{source.name}!{kml_name}")
        except zipfile.BadZipFile as exc:
            raise ValueError("KMZ 文件不是有效压缩包。") from exc
    if suffix in {".geojson", ".json", ".kml"}:
        return _read_aoi_vector_features_from_text(
            source.name, raw.decode("utf-8", errors="replace")
        )
    raise ValueError("仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。")


def _read_geojson_aoi_features(source: Path) -> list[dict[str, Any]]:
    data = json.loads(source.read_text(encoding="utf-8"))
    return _read_geojson_aoi_features_from_data(data)


def _read_geojson_aoi_features_from_data(data: Any) -> list[dict[str, Any]]:
    from shapely.geometry import mapping, shape

    from insar_prep.processing.aoi_import import _coerce_to_areal_geometry, _reject_non_wgs84_crs

    if not isinstance(data, dict):
        raise ValueError("GeoJSON 顶层必须是对象。")
    _reject_non_wgs84_crs(data)
    obj_type = data.get("type")
    if obj_type == "FeatureCollection":
        raw_features = [
            feature for feature in data.get("features", []) if isinstance(feature, dict)
        ]
    elif obj_type == "Feature":
        raw_features = [data]
    elif obj_type in {
        "Polygon",
        "MultiPolygon",
        "LineString",
        "MultiLineString",
        "GeometryCollection",
    }:
        raw_features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        raise ValueError(f"不支持的 GeoJSON 类型：{obj_type}")
    out: list[dict[str, Any]] = []
    for index, feature in enumerate(raw_features):
        geometry_data = feature.get("geometry")
        if not isinstance(geometry_data, dict):
            continue
        try:
            geometry = _coerce_to_areal_geometry(shape(geometry_data))
        except Exception:
            continue
        if geometry.is_empty:
            continue
        props = feature.get("properties")
        out.append(
            {
                "properties": _clean_aoi_properties(props if isinstance(props, dict) else {}),
                "geometry": dict(mapping(geometry)),
                "_source_index": index,
            }
        )
    if not out:
        raise ValueError("边界文件内没有可用面要素。")
    return out


def _feature_collection_from_aoi_features(
    features: list[dict[str, Any]], source: str = ""
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "properties": {"source_file": source},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **dict(feature.get("properties") or {}),
                    "_insar_feature_index": index,
                    "_insar_feature_name": _aoi_feature_name(feature),
                },
                "geometry": feature["geometry"],
            }
            for index, feature in enumerate(features)
            if isinstance(feature.get("geometry"), dict)
        ],
    }


def _selected_geojson_from_feature_collection(
    geojson: dict,
    feature_ids: list[Any] | None = None,
    name_field: str = "",
    download_mode: str = "merge",
) -> dict[str, Any]:
    if not isinstance(geojson, dict):
        raise ValueError("边界数据必须是 GeoJSON 对象。")
    features = _read_geojson_aoi_features_from_data(geojson)
    selected_indices = _normalise_feature_indices(feature_ids, len(features))
    if not selected_indices:
        raise ValueError("请至少选择一个边界要素。")
    field = str(name_field or "").strip()
    selected = [features[index] for index in selected_indices]
    collection_props = (
        geojson.get("properties") if isinstance(geojson.get("properties"), dict) else {}
    )
    selected_geojson = {
        "type": "FeatureCollection",
        "properties": {
            "source_file": str(collection_props.get("source_file") or "dragged-boundary"),
            "selected_feature_count": len(selected),
            "total_feature_count": len(features),
            "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **dict(feature.get("properties") or {}),
                    "_insar_feature_index": selected_indices[i],
                    "_insar_feature_name": _aoi_feature_name(feature, field),
                },
                "geometry": feature["geometry"],
            }
            for i, feature in enumerate(selected)
        ],
    }
    return selected_geojson


def _friendly_aoi_error(exc: Exception, source: str | Path = "") -> str:
    source_name = Path(str(source or "边界文件")).name
    text = str(exc or "").strip()
    if isinstance(exc, FileNotFoundError) or "不存在" in text or "not found" in text.lower():
        return (
            "没有读取到文件的真实本机路径。请重新拖入文件；"
            "如果仍失败，请点击“上传本地边界”选择文件。"
        )
    if "unsupported" in text.lower() or "暂不支持" in text or "仅支持" in text:
        return "仅支持 .shp、.kml、.kmz、.geojson 或 .json 边界文件。"
    if "GeoJSON" in text or "JSON" in text:
        return text
    if "KML" in text or "KMZ" in text:
        return text
    if "缺少配套" in text or ".dbf" in text or ".shx" in text:
        return text
    if "缺少同名 .prj" in text or "无法自动转换" in text or ".prj 坐标系无法识别" in text:
        return text
    if "Shapefile" in text or "shapefile" in text:
        return "Shapefile 读取失败；请确认它是面边界，并保留同名 .dbf/.shx/.prj 配套文件。"
    if "边界文件内容为空" in text or "没有可用面要素" in text or "请至少选择" in text:
        return text
    return f"{source_name} 不是可识别的边界文件，请检查文件格式和坐标系。"


def _read_kml_aoi_features(raw: bytes, source: str) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    from shapely.geometry import mapping
    from shapely.ops import unary_union

    from insar_prep.processing.aoi_vector import (
        _iter_local,
        _kml_outer_ring,
        _local_name,
        _polygon_from_ring,
    )

    try:
        root = ET.fromstring(raw)  # noqa: S314
    except ET.ParseError as exc:
        raise ValueError(f"KML 解析失败：{source}: {exc}") from exc
    out: list[dict[str, Any]] = []
    placemarks = [elem for elem in root.iter() if _local_name(elem.tag) == "Placemark"]
    for index, placemark in enumerate(placemarks):
        name_elem = next((child for child in placemark if _local_name(child.tag) == "name"), None)
        name = (name_elem.text or "").strip() if name_elem is not None else ""
        polygons = []
        for polygon_elem in _iter_local(placemark, "Polygon"):
            ring = _kml_outer_ring(polygon_elem)
            polygon = _polygon_from_ring(ring) if ring else None
            if polygon is not None and not polygon.is_empty:
                polygons.append(polygon)
        if not polygons:
            continue
        out.append(
            {
                "properties": _clean_aoi_properties({"name": name or f"Placemark {index + 1}"}),
                "geometry": dict(mapping(unary_union(polygons))),
                "_source_index": index,
            }
        )
    if out:
        return out
    polygons = []
    for polygon_elem in _iter_local(root, "Polygon"):
        ring = _kml_outer_ring(polygon_elem)
        polygon = _polygon_from_ring(ring) if ring else None
        if polygon is not None and not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        raise ValueError(f"KML 内没有可用面要素：{source}")
    return [
        {
            "properties": _clean_aoi_properties({"name": Path(source).stem or "KML 边界"}),
            "geometry": dict(mapping(unary_union(polygons))),
            "_source_index": 0,
        }
    ]


def _read_shapefile_aoi_features(source: Path) -> list[dict[str, Any]]:
    from insar_prep.processing.aoi_vector import _check_shapefile_prj

    _check_shapefile_prj(source)
    return _read_shapefile_aoi_features_from_bytes(
        source.read_bytes(),
        str(source),
        dbf_rows=_read_dbf_records(source.with_suffix(".dbf")),
        source_path=source,
    )


def _read_shapefile_aoi_features_from_bytes(
    data: bytes,
    source: str,
    *,
    dbf_rows: list[dict[str, Any]] | None = None,
    source_path: Path | None = None,
) -> list[dict[str, Any]]:
    import struct

    from shapely.geometry import mapping
    from shapely.ops import unary_union

    from insar_prep.processing.aoi_vector import (
        _SHP_HEADER_SIZE,
        _SHP_NULL_TYPE,
        _SHP_POLYGON_TYPES,
        _normalise_shapefile_geometry_crs,
        _polygons_from_shapefile_record,
    )

    if len(data) < _SHP_HEADER_SIZE or struct.unpack(">i", data[0:4])[0] != 9994:
        raise ValueError(f"不是有效 Shapefile：{source}")
    file_type = struct.unpack("<i", data[32:36])[0]
    if file_type != _SHP_NULL_TYPE and file_type not in _SHP_POLYGON_TYPES:
        raise ValueError("Shapefile 不是面要素，不能作为 AOI。")
    rows = dbf_rows or []
    out: list[dict[str, Any]] = []
    offset = _SHP_HEADER_SIZE
    size = len(data)
    while offset + 8 <= size:
        record_number, content_len_words = struct.unpack(">ii", data[offset : offset + 8])
        content_start = offset + 8
        content_end = content_start + content_len_words * 2
        if content_end > size:
            break
        content = data[content_start:content_end]
        offset = content_end
        if len(content) < 4:
            continue
        shape_type = struct.unpack("<i", content[0:4])[0]
        if shape_type == _SHP_NULL_TYPE:
            continue
        if shape_type not in _SHP_POLYGON_TYPES:
            raise ValueError(f"Shapefile 记录 {record_number} 不是面要素。")
        polygons = _polygons_from_shapefile_record(content)
        if not polygons:
            continue
        geometry = unary_union(polygons)
        if source_path is not None:
            geometry = _normalise_shapefile_geometry_crs(geometry, Path(source_path))
        row_index = max(0, int(record_number) - 1)
        out.append(
            {
                "properties": _clean_aoi_properties(
                    rows[row_index] if row_index < len(rows) else {}
                ),
                "geometry": dict(mapping(geometry)),
                "_source_index": row_index,
            }
        )
    if not out:
        raise ValueError("Shapefile 内没有可用面要素。")
    return out


def _read_dbf_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = path.read_bytes()
    if len(data) < 33:
        return []
    try:
        record_count = int.from_bytes(data[4:8], "little")
        header_len = int.from_bytes(data[8:10], "little")
        record_len = int.from_bytes(data[10:12], "little")
    except Exception:
        return []
    fields: list[tuple[str, str, int, int]] = []
    offset = 32
    while offset + 32 <= len(data) and data[offset] != 0x0D:
        raw_name = data[offset : offset + 11].split(b"\x00", 1)[0]
        name = _decode_dbf_text(raw_name).strip() or f"field_{len(fields) + 1}"
        field_type = chr(data[offset + 11]) if data[offset + 11] else "C"
        field_len = int(data[offset + 16])
        decimals = int(data[offset + 17])
        fields.append((name, field_type, field_len, decimals))
        offset += 32
    rows: list[dict[str, Any]] = []
    start = header_len
    for row_index in range(record_count):
        row_start = start + row_index * record_len
        row = data[row_start : row_start + record_len]
        if len(row) < record_len or row[:1] == b"*":
            continue
        cursor = 1
        props: dict[str, Any] = {}
        for name, field_type, field_len, decimals in fields:
            raw = row[cursor : cursor + field_len]
            cursor += field_len
            text = _decode_dbf_text(raw).strip()
            if not text:
                props[name] = ""
            elif field_type in {"N", "F"}:
                try:
                    props[name] = int(text) if decimals == 0 and "." not in text else float(text)
                except ValueError:
                    props[name] = text
            elif field_type == "L":
                props[name] = text.upper() in {"Y", "T", "1"}
            else:
                props[name] = text
        rows.append(props)
    return rows


def _decode_dbf_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "cp936", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace")


def _clean_aoi_properties(props: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            cleaned[key.strip()] = value
        else:
            try:
                cleaned[key.strip()] = json.dumps(value, ensure_ascii=False)
            except TypeError:
                cleaned[key.strip()] = str(value)
    return cleaned


def _aoi_feature_fields(features: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for feature in features:
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        for key in props:
            if key not in fields:
                fields.append(str(key))
            if len(fields) >= 80:
                return fields
    return fields


def _suggest_aoi_name_field(fields: list[str]) -> str:
    preferred = [
        "name",
        "NAME",
        "Name",
        "名称",
        "NAME_CHN",
        "fullname",
        "FULLNAME",
        "县",
        "市",
        "省",
    ]
    for field in preferred:
        if field in fields:
            return field
    for field in fields:
        if "name" in field.lower() or "名" in field:
            return field
    return fields[0] if fields else ""


def _aoi_feature_name(feature: dict[str, Any], field: str = "") -> str:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    if field and field in props and str(props.get(field) or "").strip():
        return str(props.get(field)).strip()
    fallback_field = _suggest_aoi_name_field(list(props.keys()))
    if fallback_field and str(props.get(fallback_field) or "").strip():
        return str(props.get(fallback_field)).strip()
    index = int(feature.get("_source_index") or 0) + 1
    return f"要素 {index}"


def _aoi_feature_preview_row(index: int, feature: dict[str, Any], field: str) -> dict[str, Any]:
    from shapely.geometry import shape

    geometry = shape(feature["geometry"])
    minx, miny, maxx, maxy = geometry.bounds
    return {
        "id": str(index),
        "index": index + 1,
        "source_index": int(feature.get("_source_index") or index) + 1,
        "name": _aoi_feature_name(feature, field),
        "area_km2": round(_rough_geometry_area_km2(geometry), 2),
        "bbox": {"west": minx, "east": maxx, "south": miny, "north": maxy, "crs": "EPSG:4326"},
        "properties": dict(feature.get("properties") or {}),
    }


def _rough_geometry_area_km2(geometry: Any) -> float:
    if not hasattr(geometry, "bounds") or not hasattr(geometry, "area"):
        return 0.0
    try:
        _, miny, _, maxy = geometry.bounds
        lat = (float(miny) + float(maxy)) / 2
        return (
            abs(float(geometry.area))
            * 111.32
            * 111.32
            * max(0.12, abs(math.cos(math.radians(lat))))
        )
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def _normalise_feature_indices(feature_ids: list[Any] | None, total: int) -> list[int]:
    if not feature_ids:
        return list(range(total))
    out: list[int] = []
    for value in feature_ids:
        try:
            index = int(str(value).strip())
        except ValueError:
            continue
        if 0 <= index < total and index not in out:
            out.append(index)
    return out


def _extract_geojson_geometry(data: Any) -> dict | None:
    if not isinstance(data, dict):
        return None
    obj_type = data.get("type")
    if obj_type == "Feature":
        geometry = data.get("geometry")
        return geometry if isinstance(geometry, dict) else None
    if obj_type in {"Polygon", "MultiPolygon", "FeatureCollection"}:
        return data
    return None


def _write_region_aoi_geojson(region: Any, geojson: dict) -> Path | None:
    """Persist drawn/admin AOI geometry beside the selected region."""
    try:
        root = Path(region.region_root) / "AOI"
        root.mkdir(parents=True, exist_ok=True)
        target = root / "current_aoi.geojson"
        feature = _geojson_feature_for_storage(geojson)
        target.write_text(json.dumps(feature, ensure_ascii=False, indent=2), encoding="utf-8")
        return target
    except Exception:  # noqa: BLE001
        return None


def _geojson_feature_for_storage(geojson: dict) -> dict:
    obj_type = geojson.get("type")
    if obj_type in {"Feature", "FeatureCollection"}:
        return geojson
    return {
        "type": "Feature",
        "properties": {},
        "geometry": geojson,
    }


class AoiPreviewDesktopService:
    """Owns AOI parsing and preview logic Decoupled from Api."""

    def __init__(
        self,
        get_state_cb: Any,
        save_state_cb: Any,
        ensure_current_region_cb: Any,
        log_action_cb: Any,
    ) -> None:
        self._get_state = get_state_cb
        self._save_state = save_state_cb
        self._ensure_current_region = ensure_current_region_cb
        self._log_action = log_action_cb

    def set_region_aoi_file(self, path: str) -> dict:
        """Bind an AOI loaded from a vector file (shp/kml/kmz/geojson/json)."""
        try:
            from insar_prep.processing.aoi_vector import load_aoi_from_file
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("矢量文件导入", exc)
        try:
            aoi = load_aoi_from_file(path)
            self._ensure_current_region()
            region = self._get_state().set_current_region_aoi(aoi)
            preview_geojson = _geojson_from_aoi_file(path)
            feature_count = _geojson_feature_count_from_file(path)
            if preview_geojson is not None:
                saved_geojson = _write_region_aoi_geojson(region, preview_geojson)
                region.aoi.geometry_path = saved_geojson or Path(path)
            else:
                region.aoi.geometry_path = Path(path)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        self._log_action(f"从文件导入 AOI：{Path(path).name} → {region.region_name}", kind="aoi")
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(preview_geojson)
            if preview_geojson is not None
            else None,
            "aoi_feature_count": feature_count,
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def preview_aoi_file(self, path: str) -> dict:
        """Return selectable features from a local AOI vector file."""
        try:
            features = _read_aoi_vector_features(path)
        except InsarPrepError as exc:
            return _error(exc)
        except FileNotFoundError as exc:
            return _error_msg(_friendly_aoi_error(exc, path), "AOI001")
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, path), "AOI001")
        return self._aoi_preview_response(path, features)

    def preview_aoi_file_content(self, file_name: str, text: str) -> dict:
        """Return selectable features from dragged KML/GeoJSON text content."""
        try:
            features = _read_aoi_vector_features_from_text(file_name, text)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        return self._aoi_preview_response(
            file_name, features, source_kind="content", include_geojson=True
        )

    def preview_aoi_file_bytes(self, file_name: str, base64_data: str) -> dict:
        """Return selectable features from dragged binary AOI content."""
        try:
            raw = base64.b64decode(str(base64_data or ""), validate=True)
            features = _read_aoi_vector_features_from_bytes(file_name, raw)
        except (binascii.Error, ValueError) as exc:
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, file_name), "AOI001")
        return self._aoi_preview_response(
            file_name, features, source_kind="content", include_geojson=True
        )

    def preview_aoi_file_bundle(self, files: list[dict[str, Any]] | None = None) -> dict:
        """Return selectable features from a dragged Shapefile sidecar bundle."""
        bundle = [item for item in (files or []) if isinstance(item, dict)]
        names = [str(item.get("name") or "").strip() for item in bundle]
        shp_names = [name for name in names if Path(name).suffix.lower() == ".shp"]
        if not shp_names:
            return _error_msg("请拖入一个 .shp 边界文件。", "AOI001")
        shp_name = shp_names[0]
        stem = Path(shp_name).stem.lower()
        allowed = {".shp", ".dbf", ".shx", ".prj"}
        with tempfile.TemporaryDirectory(prefix="insar_aoi_") as tmp:
            root = Path(tmp)
            for item in bundle:
                name = Path(str(item.get("name") or "")).name
                suffix = Path(name).suffix.lower()
                if Path(name).stem.lower() != stem or suffix not in allowed:
                    continue
                try:
                    raw = base64.b64decode(
                        str(item.get("base64") or item.get("base64Data") or ""), validate=True
                    )
                except binascii.Error as exc:
                    return _error_msg(_friendly_aoi_error(exc, name), "AOI001")
                (root / f"{stem}{suffix}").write_bytes(raw)
            try:
                features = _read_aoi_vector_features(root / f"{stem}.shp")
            except Exception as exc:  # noqa: BLE001
                return _error_msg(_friendly_aoi_error(exc, shp_name), "AOI001")
        return self._aoi_preview_response(
            shp_name, features, source_kind="content", include_geojson=True
        )

    def set_region_aoi_geojson_features(
        self,
        geojson: dict,
        feature_ids: list[Any] | None = None,
        name_field: str = "",
        download_mode: str = "merge",
    ) -> dict:
        """Bind selected features from dragged GeoJSON/KML content."""
        try:
            selected_geojson = _selected_geojson_from_feature_collection(
                geojson,
                feature_ids=feature_ids,
                name_field=name_field,
                download_mode=download_mode,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_msg(_friendly_aoi_error(exc, "拖入边界"), "AOI001")
        return self.set_region_aoi_geojson(selected_geojson)

    def set_region_aoi_file_features(
        self,
        path: str,
        feature_ids: list[Any] | None = None,
        name_field: str = "",
        download_mode: str = "merge",
    ) -> dict:
        """Bind selected features from a local AOI vector file as the current AOI."""
        try:
            from shapely.geometry import mapping, shape
            from shapely.ops import unary_union

            from insar_prep.core.enums import AoiSource
            from insar_prep.processing.aoi_import import (
                _coerce_to_areal_geometry,
                geometry_to_processing_aoi,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("多要素 AOI 导入", exc)
        try:
            features = _read_aoi_vector_features(path)
            selected_indices = _normalise_feature_indices(feature_ids, len(features))
            if not selected_indices:
                return _error_msg("请至少选择一个边界要素。", "AOI001")
            selected = [features[index] for index in selected_indices]
            geometries = [
                _coerce_to_areal_geometry(shape(feature["geometry"]))
                for feature in selected
                if isinstance(feature.get("geometry"), dict)
            ]
            if not geometries:
                return _error_msg("选中的要素没有可用面边界。", "AOI001")
            merged_geometry = _coerce_to_areal_geometry(unary_union(geometries))
            aoi = geometry_to_processing_aoi(merged_geometry, source=AoiSource.VECTOR_FILE)
            self._ensure_current_region()
            region = self._get_state().set_current_region_aoi(aoi)
            field = str(name_field or "").strip()
            selected_geojson = {
                "type": "FeatureCollection",
                "properties": {
                    "source_file": str(path),
                    "feature_count": len(selected),
                    "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
                    "name_field": field,
                },
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            **dict(feature.get("properties") or {}),
                            "_insar_feature_index": selected_indices[i],
                            "_insar_feature_name": _aoi_feature_name(feature, field),
                        },
                        "geometry": feature["geometry"],
                    }
                    for i, feature in enumerate(selected)
                ],
            }
            bound_geojson = {
                "type": "Feature",
                "properties": dict(selected_geojson.get("properties") or {}),
                "geometry": dict(mapping(merged_geometry)),
            }
            saved_geojson = _write_region_aoi_geojson(region, bound_geojson)
            if saved_geojson is not None:
                region.aoi.geometry_path = saved_geojson
            else:
                region.aoi.geometry_path = Path(path)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        mode_label = "拆分下载" if str(download_mode).strip() == "split" else "合并下载"
        self._log_action(
            f"导入边界要素 {len(selected)} / {len(features)} "
            f"个并绑定 AOI：{Path(path).name}（{mode_label}）",
            kind="aoi",
        )
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(bound_geojson),
            "aoi_feature_count": len(selected),
            "aoi_total_feature_count": len(features),
            "download_mode": "split" if str(download_mode).strip() == "split" else "merge",
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def set_region_aoi_geojson(self, geojson: dict) -> dict:
        """Bind an AOI from an in-memory GeoJSON Feature / Geometry (map drawing)."""
        try:
            from shapely.geometry import mapping

            from insar_prep.core.enums import AoiSource
            from insar_prep.processing.aoi_import import (
                _geometry_from_geojson,
                geometry_to_processing_aoi,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("GeoJSON AOI", exc)
        if not isinstance(geojson, dict):
            return _error_msg("GeoJSON 必须是对象", "AOI001")
        try:
            geometry = _geometry_from_geojson(geojson)
            aoi = geometry_to_processing_aoi(geometry, source=AoiSource.MANUAL_BBOX)
            self._ensure_current_region()
            region = self._get_state().set_current_region_aoi(aoi)
            cleaned_geojson = {
                "type": "Feature",
                "properties": dict(geojson.get("properties") or {})
                if isinstance(geojson.get("properties"), dict)
                else {},
                "geometry": dict(mapping(geometry)),
            }
            saved_geojson = _write_region_aoi_geojson(region, cleaned_geojson)
            if saved_geojson is not None:
                region.aoi.geometry_path = saved_geojson
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        self._log_action(f"地图绘制 AOI 已绑定：{region.region_name}", kind="aoi")
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "aoi_geojson": _extract_geojson_geometry(cleaned_geojson),
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def clear_region_aoi(self) -> dict:
        """Clear only the active region AOI/boundary, keeping searched scenes."""
        region = self._get_state().current_region()
        if region is None:
            self._log_action("清除边界/AOI：当前没有已选研究区", kind="aoi")
            return {"ok": True, "cleared_aoi": False}
        try:
            from insar_prep.core.enums import AoiRole, AoiSource
            from insar_prep.core.models import Aoi

            cleared_aoi = bool(region.aoi is not None and region.aoi.bbox is not None)
            region.aoi = Aoi(
                source=AoiSource.MANUAL_BBOX,
                role=AoiRole.PROCESSING_AOI,
                bbox=None,
                geometry_path=None,
            )
            # Remove cached GeoJSON if exists
            root = Path(region.region_root) / "AOI"
            target = root / "current_aoi.geojson"
            if target.is_file():
                target.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "AOI001")
        self._save_state()
        self._log_action(f"已清除研究区边界/AOI：{region.region_name}", kind="aoi")
        return {"ok": True, "cleared_aoi": cleared_aoi}

    def _aoi_preview_response(
        self,
        path: str | Path,
        features: list[dict[str, Any]],
        *,
        source_kind: str = "path",
        include_geojson: bool = False,
    ) -> dict:
        fields = _aoi_feature_fields(features)
        display_field = _suggest_aoi_name_field(fields)
        preview_features = features
        response = {
            "ok": True,
            "path": str(path),
            "file_name": Path(path).name,
            "source_kind": source_kind,
            "total_features": len(features),
            "feature_preview_limit": len(features),
            "features_truncated": False,
            "fields": fields,
            "display_field": display_field,
            "features": [
                _aoi_feature_preview_row(index, feature, display_field)
                for index, feature in enumerate(preview_features)
            ],
        }
        if include_geojson:
            response["geojson"] = _feature_collection_from_aoi_features(preview_features, str(path))
        return response
