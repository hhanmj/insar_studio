"""Best-effort ASF SearchAPI metadata enrichment for Sentinel-1 scenes."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any, Callable
from urllib.parse import urlencode

from insar_prep.core.enums import OrbitDirection
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.core.models import BBox, Scene
from insar_prep.providers.asf.scene_parser import deduplicate_scenes, parse_scene_name

logger = get_logger("providers.asf.metadata")

ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
_CHUNK_SIZE = 25
_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 12
_CMR_CONNECT_TIMEOUT_SECONDS = 4
_CMR_READ_TIMEOUT_SECONDS = 8
_REQUEST_HEADERS = {"User-Agent": "InSAR-Assistant/0.1 ASF metadata search"}
ProgressCallback = Callable[[int, int, str], None]
_CMR_COLLECTIONS: dict[str, tuple[str, ...]] = {
    "SLC": (
        "C1214470488-ASF",  # SENTINEL-1A_SLC
        "C1327985661-ASF",  # SENTINEL-1B_SLC
        "C3470873558-ASF",  # SENTINEL-1C_SLC
        "C4175278193-ASF",  # SENTINEL-1D_SLC
    ),
    "GRD": (
        "C1214470533-ASF",  # SENTINEL-1A_DP_GRD_HIGH
        "C1214471521-ASF",  # SENTINEL-1A_DP_GRD_MEDIUM
        "C1214471197-ASF",  # SENTINEL-1A_DP_GRD_FULL
        "C1214470682-ASF",  # SENTINEL-1A_SP_GRD_HIGH
        "C1214472994-ASF",  # SENTINEL-1A_SP_GRD_MEDIUM
        "C1327985645-ASF",  # SENTINEL-1B_DP_GRD_HIGH
        "C1327985660-ASF",  # SENTINEL-1B_DP_GRD_MEDIUM
        "C1327985571-ASF",  # SENTINEL-1B_SP_GRD_HIGH
        "C1327985740-ASF",  # SENTINEL-1B_SP_GRD_MEDIUM
        "C3486566209-ASF",  # SENTINEL-1C_DP_GRD_HIGH
        "C3486605959-ASF",  # SENTINEL-1C_DP_GRD_MEDIUM
        "C3486646217-ASF",  # SENTINEL-1C_DP_GRD_FULL
        "C3488402208-ASF",  # SENTINEL-1C_SP_GRD_HIGH
        "C3488414315-ASF",  # SENTINEL-1C_SP_GRD_MEDIUM
        "C3488389367-ASF",  # SENTINEL-1C_SP_GRD_FULL
        "C4163054563-ASF",  # SENTINEL-1D_DP_GRD_HIGH
        "C4174076966-ASF",  # SENTINEL-1D_DP_GRD_MEDIUM
        "C4174044457-ASF",  # SENTINEL-1D_SP_GRD_HIGH
        "C4175200051-ASF",  # SENTINEL-1D_SP_GRD_MEDIUM
    ),
}
_ASF_POLARIZATION_QUERY = {
    "DV": "VV+VH",
    "DH": "HH+HV",
    "SV": "VV",
    "SH": "HH",
    "VV_VH": "VV+VH",
    "HH_HV": "HH+HV",
    "VV": "VV",
    "VH": "VH",
    "HH": "HH",
    "HV": "HV",
}


def _scene_key(value: str | None) -> str:
    text = (value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if text.lower().endswith(".zip"):
        text = text[:-4]
    for suffix in ("-SLC", "-GRD", "-RAW", "-OCN"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_direction(value: Any) -> OrbitDirection | None:
    text = str(value or "").strip().upper()
    if text.startswith("ASC"):
        return OrbitDirection.ASCENDING
    if text.startswith("DESC"):
        return OrbitDirection.DESCENDING
    return None


def _normalise_polarization(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", "_").replace("+", "_")


def _asf_polarization_param(value: str | None) -> str | None:
    pol = _normalise_polarization(value)
    if not pol:
        return None
    return _ASF_POLARIZATION_QUERY.get(pol, pol)


def _scene_matches_filters(scene: Scene, *, beam_mode: str = "", polarization: str = "") -> bool:
    beam = (beam_mode or "").strip().upper()
    if beam and str(scene.beam_mode or "").upper() != beam:
        return False
    pol = _normalise_polarization(polarization)
    if pol and _normalise_polarization(str(scene.polarization or "")) != pol:
        return False
    return True


def _walk_positions(value: Any, out: list[tuple[float, float]]) -> None:
    if not isinstance(value, list):
        return
    if (
        len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        out.append((float(value[0]), float(value[1])))
        return
    for item in value:
        _walk_positions(item, out)


def _bbox_from_geometry(geometry: Mapping[str, Any] | None) -> BBox | None:
    if not isinstance(geometry, Mapping):
        return None
    positions: list[tuple[float, float]] = []
    _walk_positions(geometry.get("coordinates"), positions)
    if not positions:
        return None
    lngs = [p[0] for p in positions]
    lats = [p[1] for p in positions]
    try:
        return BBox(
            west=min(lngs),
            east=max(lngs),
            south=min(lats),
            north=max(lats),
            crs="EPSG:4326",
        )
    except Exception as exc:  # noqa: BLE001 - invalid remote geometry should not block import
        logger.debug("could not derive ASF footprint bbox: %s", exc)
        return None


def _feature_key(feature: Mapping[str, Any]) -> str:
    props = feature.get("properties") or {}
    if not isinstance(props, Mapping):
        props = {}
    return _scene_key(
        str(
            props.get("sceneName")
            or props.get("fileName")
            or props.get("fileID")
            or props.get("granuleName")
            or ""
        )
    )


def _feature_rank(feature: Mapping[str, Any]) -> int:
    props = feature.get("properties") or {}
    if not isinstance(props, Mapping):
        return 0
    rank = 0
    if str(props.get("processingLevel") or "").upper() == "SLC":
        rank += 2
    if "FRAME" in str(props.get("granuleType") or "").upper():
        rank += 2
    if str(props.get("fileName") or "").lower().endswith(".zip"):
        rank += 1
    return rank


def _feature_updates(feature: Mapping[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    if not isinstance(props, Mapping):
        props = {}
    geometry = feature.get("geometry")
    geometry = geometry if isinstance(geometry, Mapping) else None
    updates: dict[str, Any] = {}

    direction = _to_direction(props.get("flightDirection") or props.get("orbitDirection"))
    if direction is not None:
        updates["orbit_direction"] = direction

    path = _to_int(props.get("pathNumber") or props.get("path") or props.get("relativeOrbit"))
    if path is not None:
        updates["path"] = path
        updates["relative_orbit"] = path

    frame = _to_int(props.get("frameNumber") or props.get("frame"))
    if frame is not None:
        updates["frame"] = frame

    orbit = _to_int(props.get("orbit"))
    if orbit is not None:
        updates["absolute_orbit"] = orbit

    size = _to_int(props.get("bytes") or props.get("fileSize"))
    if size is not None:
        updates["file_size_remote"] = size

    url = props.get("url")
    if isinstance(url, str) and url.strip():
        updates["url"] = url.strip()

    sensor = props.get("sensor")
    if isinstance(sensor, str) and sensor.strip():
        updates["sensor"] = sensor.strip()

    bbox = _bbox_from_geometry(geometry)
    if bbox is not None:
        updates["footprint_bbox"] = bbox
    if geometry is not None:
        updates["footprint_geojson"] = dict(geometry)

    return updates


def _metadata_query_ids(scenes: Iterable[Scene]) -> list[str]:
    query_ids: list[str] = []
    seen: set[str] = set()
    for scene in scenes:
        base = _scene_key(scene.scene_id)
        if not base:
            continue
        level = str(scene.product_type or "").upper()
        candidates = [base]
        if level == "SLC":
            candidates.insert(0, f"{base}-SLC")
        elif level in {"GRD", "RAW", "OCN"}:
            candidates.append(f"{base}-{level}")
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                query_ids.append(candidate)
    return query_ids


def _fetch_features(
    scene_ids: list[str],
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Mapping[str, Any]]:
    try:
        import requests  # noqa: PLC0415 - optional download extra
    except ImportError as exc:
        raise InputValidationError(
            "ASF 元数据查询需要 requests；请安装 download extra",
            code=ErrorCode.ASF001,
        ) from exc

    features: dict[str, Mapping[str, Any]] = {}
    total = max(1, (len(scene_ids) + _CHUNK_SIZE - 1) // _CHUNK_SIZE)
    for start in range(0, len(scene_ids), _CHUNK_SIZE):
        batch = start // _CHUNK_SIZE + 1
        if progress is not None:
            progress(batch - 1, total, f"正在查询 ASF 元数据批次 {batch}/{total}")
        chunk = scene_ids[start : start + _CHUNK_SIZE]
        query = urlencode({"granule_list": ",".join(chunk), "output": "geojson"})
        response = requests.get(
            f"{ASF_SEARCH_URL}?{query}",
            headers=_REQUEST_HEADERS,
            timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        data = response.json()
        for feature in data.get("features", []) if isinstance(data, dict) else []:
            if not isinstance(feature, Mapping):
                continue
            key = _feature_key(feature)
            if key:
                current = features.get(key)
                if current is None or _feature_rank(feature) >= _feature_rank(current):
                    features[key] = feature
        if progress is not None:
            progress(batch, total, f"已完成 ASF 元数据批次 {batch}/{total}")
    return features


def _bbox_to_wkt(bbox: BBox) -> str:
    """Return an ASF SearchAPI WKT polygon for a WGS84 bbox."""
    return (
        "POLYGON(("
        f"{bbox.west} {bbox.south},"
        f"{bbox.east} {bbox.south},"
        f"{bbox.east} {bbox.north},"
        f"{bbox.west} {bbox.north},"
        f"{bbox.west} {bbox.south}"
        "))"
    )


def _asf_datetime(value: str | None, *, end: bool = False) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if "T" in text:
        return text
    suffix = "23:59:59Z" if end else "00:00:00Z"
    return f"{text}T{suffix}"


def _first_feature_source(feature: Mapping[str, Any]) -> str | None:
    props = feature.get("properties") or {}
    if not isinstance(props, Mapping):
        return None
    for key in ("url", "fileName", "sceneName", "fileID", "granuleName"):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _asf_request_failure_message(exc: BaseException) -> str:
    """Return a user-facing Chinese message without leaking raw transport text."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "proxy" in name or "proxy" in text:
        return "ASF 元数据检索失败：代理连接失败。请检查设置中的网络代理地址、端口和认证信息。"
    if "ssl" in name or "ssl" in text or "eof occurred" in text or "tls" in text:
        return (
            "ASF 元数据检索失败：TLS/SSL 连接被中断。常见原因是代理、防火墙、"
            "网络链路不稳定或 ASF 服务临时不可达；请配置代理或稍后重试。"
        )
    if "name resolution" in text or "getaddrinfo" in text or "dns" in text:
        return "ASF 元数据检索失败：无法解析 ASF 服务域名。请检查 DNS、网络连接或代理设置。"
    if "connection" in name or "connection" in text or "connect" in text:
        return "ASF 元数据检索失败：无法连接 ASF 服务。请检查网络、代理设置，或稍后重试。"
    return "ASF 元数据检索失败：网络请求未完成。请检查网络或代理设置，稍后重试。"


def _request_asf_geojson(requests_module: Any, params: Mapping[str, str], *, method: str) -> dict[str, Any]:
    method = method.upper()
    if method == "POST":
        response = requests_module.post(
            ASF_SEARCH_URL,
            files={key: (None, value) for key, value in dict(params).items()},
            headers=_REQUEST_HEADERS,
            timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
        )
    else:
        response = requests_module.get(
            ASF_SEARCH_URL,
            params=dict(params),
            headers=_REQUEST_HEADERS,
            timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
        )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("ASF SearchAPI returned non-object JSON")
    return data


def _get_asf_geojson(params: Mapping[str, str]) -> dict[str, Any]:
    try:
        import requests  # noqa: PLC0415 - optional download extra
    except ImportError as exc:
        raise InputValidationError(
            "ASF 检索需要 requests；请安装 download extra",
            code=ErrorCode.ASF002,
        ) from exc

    timeout_error: BaseException | None = None
    request_error: BaseException | None = None
    http_status: int | None = None
    value_error: BaseException | None = None

    for method in ("GET", "POST"):
        for attempt in range(1):
            try:
                return _request_asf_geojson(requests, params, method=method)
            except requests.Timeout as exc:
                timeout_error = exc
                time.sleep(1.2 * (attempt + 1))
                continue
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                http_status = int(status) if isinstance(status, int) else None
                if http_status in {429, 502, 503, 504}:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise InputValidationError(
                    f"ASF 元数据检索失败：服务器返回 HTTP {status or '错误'}。请检查查询条件。",
                    code=ErrorCode.ASF002,
                ) from exc
            except requests.RequestException as exc:
                raise InputValidationError(
                    _asf_request_failure_message(exc),
                    code=ErrorCode.ASF002,
                ) from exc
            except ValueError as exc:
                value_error = exc
                break

    if timeout_error is not None:
        raise InputValidationError(
            (
                "ASF 元数据检索超时。常见原因是网络到 api.daac.asf.alaska.edu 较慢、"
                "代理未配置，或查询范围/时间跨度过大；请缩小 AOI、减少日期范围，"
                "或在设置中配置网络代理后重试。"
            ),
            code=ErrorCode.ASF002,
        ) from timeout_error
    if http_status is not None:
        raise InputValidationError(
            f"ASF 元数据检索失败：服务器返回 HTTP {http_status}。已尝试 GET 与 POST，请稍后重试或缩小查询条件。",
            code=ErrorCode.ASF002,
        )
    if request_error is not None:
        raise InputValidationError(
            _asf_request_failure_message(request_error),
            code=ErrorCode.ASF002,
        ) from request_error
    if value_error is not None:
        raise InputValidationError(
            "ASF 元数据检索失败：服务器返回内容不是有效 JSON。",
            code=ErrorCode.ASF002,
        ) from value_error
    raise InputValidationError("ASF 元数据检索失败：服务器返回格式异常。", code=ErrorCode.ASF002)


def _cmr_datetime_range(start: str | None, end: str | None) -> str | None:
    start_value = _asf_datetime(start)
    end_value = _asf_datetime(end, end=True)
    if not start_value and not end_value:
        return None
    return f"{start_value or ''},{end_value or ''}"


def _cmr_bbox(bbox: BBox | None) -> str | None:
    if bbox is None:
        return None
    return f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}"


def _cmr_feature_url(entry: Mapping[str, Any]) -> str | None:
    links = entry.get("links")
    if not isinstance(links, list):
        return None
    for link in links:
        if not isinstance(link, Mapping):
            continue
        href = link.get("href")
        if not isinstance(href, str) or not href.startswith("https://"):
            continue
        rel = str(link.get("rel") or "")
        title = str(link.get("title") or "").lower()
        if "data#" in rel or "direct download" in title or href.lower().endswith(".zip"):
            return href
    return None


def _cmr_polygon_geometry(entry: Mapping[str, Any]) -> tuple[dict[str, Any] | None, BBox | None]:
    polygons = entry.get("polygons")
    if not isinstance(polygons, list):
        return None, None
    rings: list[list[list[float]]] = []
    positions: list[tuple[float, float]] = []
    for polygon in polygons:
        raw = polygon[0] if isinstance(polygon, list) and polygon else polygon
        if not isinstance(raw, str):
            continue
        nums = [float(part) for part in raw.replace(",", " ").split() if _is_float_text(part)]
        if len(nums) < 6:
            continue
        ring: list[list[float]] = []
        for idx in range(0, len(nums) - 1, 2):
            lat, lng = nums[idx], nums[idx + 1]
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                ring.append([lng, lat])
                positions.append((lng, lat))
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
    if not rings or not positions:
        return None, None
    lngs = [item[0] for item in positions]
    lats = [item[1] for item in positions]
    try:
        bbox = BBox(west=min(lngs), east=max(lngs), south=min(lats), north=max(lats), crs="EPSG:4326")
    except Exception:
        bbox = None
    geometry: dict[str, Any]
    if len(rings) == 1:
        geometry = {"type": "Polygon", "coordinates": [rings[0]]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    return geometry, bbox


def _is_float_text(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _cmr_entry_to_scene(entry: Mapping[str, Any]) -> Scene | None:
    source = str(
        entry.get("producer_granule_id")
        or entry.get("title")
        or entry.get("id")
        or ""
    ).strip()
    if source.endswith("-SLC"):
        source = source[:-4]
    if not source:
        return None
    try:
        scene = parse_scene_name(source)
    except InputValidationError:
        logger.debug("skipping unparseable CMR granule: %r", source)
        return None
    updates: dict[str, Any] = {}
    url = _cmr_feature_url(entry)
    if url:
        updates["url"] = url
    size = _to_int(entry.get("granule_size"))
    if size is not None:
        # CMR ECHO granule_size is MB for ASF Sentinel products.
        updates["file_size_remote"] = size * 1024 * 1024
    domains = entry.get("orbit_calculated_spatial_domains")
    if isinstance(domains, list) and domains:
        first = domains[0]
        if isinstance(first, Mapping):
            orbit = _to_int(first.get("orbit_number"))
            if orbit is not None:
                updates["absolute_orbit"] = orbit
    geometry, bbox = _cmr_polygon_geometry(entry)
    if geometry is not None:
        updates["footprint_geojson"] = geometry
    if bbox is not None:
        updates["footprint_bbox"] = bbox
    return scene.model_copy(update=updates) if updates else scene


def _search_scenes_from_cmr(
    *,
    bbox: BBox | None,
    start: str | None,
    end: str | None,
    product_type: str,
    beam_mode: str = "",
    polarization: str = "",
    max_results: int,
) -> list[Scene]:
    try:
        import requests  # noqa: PLC0415 - optional download extra
    except ImportError as exc:
        raise InputValidationError(
            "CMR 备用检索需要 requests；请安装 download extra",
            code=ErrorCode.ASF002,
        ) from exc

    level = (product_type or "SLC").strip().upper()
    collection_ids = _CMR_COLLECTIONS.get(level)
    if not collection_ids:
        raise InputValidationError(f"CMR 备用检索暂不支持 {product_type}", code=ErrorCode.ASF002)

    limit = max(1, min(int(max_results or 50), 500))
    scenes: list[Scene] = []
    last_error: BaseException | None = None
    checked = 0
    for collection_id in collection_ids:
        if len(scenes) >= limit:
            break
        checked += 1
        params: dict[str, str] = {
            "collection_concept_id": collection_id,
            "page_size": str(min(100, limit - len(scenes))),
            "sort_key": "-start_date",
        }
        temporal = _cmr_datetime_range(start, end)
        if temporal:
            params["temporal"] = temporal
        bbox_text = _cmr_bbox(bbox)
        if bbox_text:
            params["bounding_box"] = bbox_text
        try:
            response = requests.get(
                CMR_GRANULES_URL,
                params=params,
                headers=_REQUEST_HEADERS,
                timeout=(_CMR_CONNECT_TIMEOUT_SECONDS, _CMR_READ_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            last_error = exc
            if checked >= 2:
                break
            continue
        except ValueError as exc:
            last_error = exc
            if checked >= 2:
                break
            continue
        entries = (((data or {}).get("feed") or {}).get("entry") or []) if isinstance(data, dict) else []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            scene = _cmr_entry_to_scene(entry)
            if scene is not None and _scene_matches_filters(
                scene,
                beam_mode=beam_mode,
                polarization=polarization,
            ):
                scenes.append(scene)
                if len(scenes) >= limit:
                    break
    if not scenes and last_error is not None:
        raise InputValidationError(
            f"CMR 备用检索也未完成：{_asf_request_failure_message(last_error)}",
            code=ErrorCode.ASF002,
        ) from last_error
    unique, _ = deduplicate_scenes(scenes)
    logger.info("CMR fallback returned %d scenes (%s)", len(unique), level)
    return unique


def _plain_error_message(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    return str(message or exc)


def search_scenes_from_asf(
    *,
    bbox: BBox | None = None,
    start: str | None = None,
    end: str | None = None,
    product_type: str = "SLC",
    beam_mode: str = "IW",
    polarization: str = "",
    orbit_direction: str = "",
    relative_orbit: int | None = None,
    frame: int | None = None,
    max_results: int = 50,
    progress: ProgressCallback | None = None,
) -> list[Scene]:
    """Query ASF SearchAPI and return Sentinel-1 scenes with metadata.

    This is a public metadata query only. Download still uses the authenticated
    ASF/Earthdata downloader, so credentials are not needed at search time.
    """
    level = (product_type or "SLC").strip().upper()
    if level not in {"SLC", "GRD", "RAW", "OCN"}:
        raise InputValidationError(f"不支持的 Sentinel-1 产品类型：{product_type}", code=ErrorCode.ASF002)

    limit = max(1, min(int(max_results or 50), 500))
    params: dict[str, str] = {
        "platform": "Sentinel-1",
        "processingLevel": level,
        "output": "geojson",
        "maxResults": str(limit),
    }
    beam = (beam_mode or "").strip().upper()
    if beam:
        params["beamMode"] = beam
    polarization_param = _asf_polarization_param(polarization)
    if polarization_param:
        params["polarization"] = polarization_param
    start_value = _asf_datetime(start)
    end_value = _asf_datetime(end, end=True)
    if start_value:
        params["start"] = start_value
    if end_value:
        params["end"] = end_value
    if bbox is not None:
        params["intersectsWith"] = _bbox_to_wkt(bbox)
    direction = (orbit_direction or "").strip().upper()
    if direction in {"ASCENDING", "DESCENDING"}:
        params["flightDirection"] = direction
    if relative_orbit is not None:
        params["relativeOrbit"] = str(int(relative_orbit))
    if frame is not None:
        params["frame"] = str(int(frame))

    if progress is not None:
        progress(0, 1, "正在请求 ASF 检索接口")
    try:
        data = _get_asf_geojson(params)
    except InputValidationError as primary_error:
        if progress is not None:
            progress(0, 1, "ASF 检索失败，正在切换 CMR 备用检索")
        try:
            return _search_scenes_from_cmr(
                bbox=bbox,
                start=start,
                end=end,
                product_type=level,
                beam_mode=beam,
                polarization=polarization,
                max_results=limit,
            )
        except InputValidationError as fallback_error:
            raise InputValidationError(
                f"{_plain_error_message(primary_error)}；CMR 备用检索也失败：{_plain_error_message(fallback_error)}",
                code=ErrorCode.ASF002,
            ) from fallback_error
    features = data.get("features", []) if isinstance(data, dict) else []
    if progress is not None:
        progress(1, 1, f"ASF 返回 {len(features)} 条结果，正在解析元数据")
    scenes: list[Scene] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        source = _first_feature_source(feature)
        if not source:
            continue
        try:
            scene = parse_scene_name(source)
        except InputValidationError:
            logger.debug("skipping unparseable ASF search result: %r", source)
            continue
        updates = _feature_updates(feature)
        scene = scene.model_copy(update=updates) if updates else scene
        if _scene_matches_filters(scene, beam_mode=beam, polarization=polarization):
            scenes.append(scene)
    unique, _ = deduplicate_scenes(scenes)
    logger.info("ASF search returned %d scenes (%s)", len(unique), level)
    return unique


def enrich_scenes_from_asf_search(
    scenes: Iterable[Scene],
    *,
    progress: ProgressCallback | None = None,
) -> list[Scene]:
    """Return scenes enriched with public ASF SearchAPI metadata when available.

    The function performs a public metadata lookup only; it does not authenticate
    and it does not download SLC archives. If ASF is unreachable, callers should
    keep using the original parsed scenes.
    """
    scene_list = list(scenes)
    ids = _metadata_query_ids(scene_list)
    if not ids:
        return scene_list
    features = _fetch_features(ids, progress=progress)
    enriched: list[Scene] = []
    for scene in scene_list:
        feature = features.get(_scene_key(scene.scene_id))
        if feature is None:
            enriched.append(scene)
            continue
        updates = _feature_updates(feature)
        enriched.append(scene.model_copy(update=updates) if updates else scene)
    logger.info("enriched %d/%d scenes with ASF metadata", len(features), len(scene_list))
    return enriched
