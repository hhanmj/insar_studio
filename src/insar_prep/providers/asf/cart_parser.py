"""ASF cart / URL file parsing (Task 006).

Parses locally exported ASF inputs (Vertex Python download scripts, Metalink,
URL text, CSV, GeoJSON) into Sentinel-1 :class:`~insar_prep.core.models.Scene`
lists.

Strictly local and side-effect free: the Python download script is parsed with
regex only and is never executed (no ``exec``/``eval``). No network access, no
``asf_search``, no credentials.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from insar_prep.core.enums import OrbitDirection
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import BBox, Scene
from insar_prep.providers.asf.scene_parser import parse_scene_name

logger = get_logger("providers.asf.cart")

_URL_RE = re.compile(r"https?://[^\s'\"<>]+")
_ASF_HOST = "asf.alaska.edu"

_CSV_URL_KEYS = ("url", "download url")
_CSV_NAME_KEYS = ("file name", "granule name", "scene name", "filename", "granulename", "scenename")
_GEOJSON_URL_KEYS = ("url",)
_GEOJSON_NAME_KEYS = ("filename", "file name", "granulename", "scenename")

# Extra ASF metadata columns (Vertex CSV + asf_search GeoJSON property variants)
# used to enrich a scene with track/frame/flight-direction beyond the granule name.
_PATH_KEYS = ("path number", "pathnumber", "path", "relative orbit", "relativeorbit")
_FRAME_KEYS = ("frame number", "framenumber", "frame")
_DIRECTION_KEYS = (
    "ascending or descending?",
    "ascending or descending",
    "flight direction",
    "flightdirection",
    "orbit direction",
    "orbitdirection",
    "direction",
)


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_direction(value: str | None) -> OrbitDirection | None:
    if not value:
        return None
    text = str(value).strip().upper()
    if text.startswith("ASC") or text == "A":
        return OrbitDirection.ASCENDING
    if text.startswith("DESC") or text == "D":
        return OrbitDirection.DESCENDING
    return None


def _enrich_scene(scene: Scene, mapping: Mapping[str, Any]) -> Scene:
    """Return ``scene`` with track/frame/direction filled from ASF columns."""
    update: dict[str, Any] = {}
    path = _to_int(_first_value(mapping, _PATH_KEYS))
    if path is not None:
        update["relative_orbit"] = path
    frame = _to_int(_first_value(mapping, _FRAME_KEYS))
    if frame is not None:
        update["frame"] = frame
    direction = _to_direction(_first_value(mapping, _DIRECTION_KEYS))
    if direction is not None:
        update["orbit_direction"] = direction
    return scene.model_copy(update=update) if update else scene


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


def _footprint_updates(geometry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(geometry, Mapping):
        return {}
    positions: list[tuple[float, float]] = []
    _walk_positions(geometry.get("coordinates"), positions)
    if not positions:
        return {"footprint_geojson": dict(geometry)}
    lngs = [p[0] for p in positions]
    lats = [p[1] for p in positions]
    return {
        "footprint_geojson": dict(geometry),
        "footprint_bbox": BBox(
            west=min(lngs),
            east=max(lngs),
            south=min(lats),
            north=max(lats),
            crs="EPSG:4326",
        ),
    }


def extract_urls_from_text(text: str) -> list[str]:
    """Return ASF download URLs found in arbitrary text (non-ASF URLs ignored)."""
    seen: set[str] = set()
    urls: list[str] = []
    for url in _URL_RE.findall(text):
        if _ASF_HOST in url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _read_text(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise InputValidationError(f"file not found: {file_path}", code=ErrorCode.ASF001)
    return file_path.read_text(encoding="utf-8")


def parse_asf_python_script(path: str | Path) -> list[str]:
    """Extract ASF URLs from a Vertex Python script without executing it."""
    return extract_urls_from_text(_read_text(path))


def parse_url_text(path: str | Path) -> list[str]:
    """Read a URL-per-line text file, ignoring blank lines and ``#`` comments."""
    urls: list[str] = []
    for line in _read_text(path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls


def _first_value(mapping: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value:
            return str(value).strip()
    return None


def _scenes_from_sources(sources: Iterable[str]) -> list[Scene]:
    scenes: list[Scene] = []
    for source in sources:
        try:
            scenes.append(parse_scene_name(source))
        except InputValidationError:
            logger.warning("skipping unparseable ASF entry: %r", source)
    return scenes


def parse_asf_csv(path: str | Path) -> list[Scene]:
    """Parse an ASF CSV into scenes (URL or scene-name columns, case-insensitive).

    Track/frame/flight-direction columns, when present, are merged onto each scene.
    """
    reader = csv.DictReader(io.StringIO(_read_text(path)))
    scenes: list[Scene] = []
    for row in reader:
        normalized = {(k or "").strip().lower(): v for k, v in row.items()}
        source = _first_value(normalized, _CSV_URL_KEYS) or _first_value(normalized, _CSV_NAME_KEYS)
        if not source:
            continue
        try:
            scene = parse_scene_name(source)
        except InputValidationError:
            logger.warning("skipping unparseable ASF entry: %r", source)
            continue
        scenes.append(_enrich_scene(scene, normalized))
    return scenes


def parse_asf_geojson(path: str | Path) -> list[Scene]:
    """Parse an ASF GeoJSON into scenes from ``features[*].properties``.

    Track/frame/flight-direction properties, when present, are merged onto each scene.
    """
    data = json.loads(_read_text(path))
    features = data.get("features", []) if isinstance(data, dict) else []
    if not features:
        raise InputValidationError("GeoJSON contains no features", code=ErrorCode.ASF001)
    scenes: list[Scene] = []
    for feature in features:
        properties = feature.get("properties") or {}
        normalized = {str(k).strip().lower(): v for k, v in properties.items()}
        geometry = feature.get("geometry")
        geometry = geometry if isinstance(geometry, Mapping) else None
        source = _first_value(normalized, _GEOJSON_URL_KEYS) or _first_value(
            normalized, _GEOJSON_NAME_KEYS
        )
        if not source:
            continue
        try:
            scene = parse_scene_name(source)
        except InputValidationError:
            logger.warning("skipping unparseable ASF entry: %r", source)
            continue
        scene = _enrich_scene(scene, normalized)
        updates = _footprint_updates(geometry)
        scenes.append(scene.model_copy(update=updates) if updates else scene)
    return scenes


def _xml_name(tag: str) -> str:
    """Return an XML tag's local name without a namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def parse_asf_metalink(path: str | Path) -> list[Scene]:
    """Parse an ASF-exported Metalink XML file into scenes.

    ASF metalink files usually carry both ``<file name="...">`` and one or more
    ``<url>`` children. Prefer the ASF URL when present so downloads can run;
    fall back to the file name when the URL is absent or non-ASF.
    """
    text = _read_text(path)
    scenes: list[Scene] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return _scenes_from_sources(extract_urls_from_text(text))

    for file_node in root.iter():
        if _xml_name(file_node.tag) != "file":
            continue
        name = str(file_node.attrib.get("name") or "").strip()
        urls: list[str] = []
        for child in file_node.iter():
            if _xml_name(child.tag) != "url":
                continue
            url = (child.text or "").strip()
            if url and _ASF_HOST in url:
                urls.append(url)
        source = urls[0] if urls else name
        if not source:
            continue
        try:
            scene = parse_scene_name(source)
        except InputValidationError:
            logger.warning("skipping unparseable ASF metalink entry: %r", source)
            continue
        if scene.url is None and urls:
            scene = scene.model_copy(update={"url": urls[0]})
        scenes.append(scene)

    if scenes:
        return scenes
    return _scenes_from_sources(extract_urls_from_text(text))


def parse_asf_cart_file(path: str | Path) -> list[Scene]:
    """Parse an ASF cart file into scenes, dispatching on the file extension."""
    file_path = Path(path)
    if not file_path.exists():
        raise InputValidationError(f"file not found: {file_path}", code=ErrorCode.ASF001)
    suffix = file_path.suffix.lower()
    if suffix == ".py":
        scenes = _scenes_from_sources(parse_asf_python_script(file_path))
    elif suffix == ".txt":
        scenes = _scenes_from_sources(parse_url_text(file_path))
    elif suffix == ".csv":
        scenes = parse_asf_csv(file_path)
    elif suffix in (".geojson", ".json"):
        scenes = parse_asf_geojson(file_path)
    elif suffix == ".metalink":
        scenes = parse_asf_metalink(file_path)
    elif suffix in (".metadata", ".meta", ".met"):
        scenes = _parse_asf_metadata_file(file_path)
    else:
        raise InputValidationError(
            f"unsupported cart file extension: {suffix!r}", code=ErrorCode.ASF001
        )
    if not scenes:
        raise InputValidationError(
            f"no Sentinel-1 scenes found in {file_path}", code=ErrorCode.ASF001
        )
    log_event(
        logger,
        EventType.ASF_CART_IMPORTED,
        f"parsed {len(scenes)} Sentinel-1 scenes",
        module="asf",
        payload={"scene_count": len(scenes), "source": file_path.name},
    )
    return scenes


def _parse_asf_metadata_file(path: Path) -> list[Scene]:
    """Best-effort parser for ASF-exported metadata files with generic suffixes."""
    text = _read_text(path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and data.get("features"):
        return parse_asf_geojson(path)
    lines = text.splitlines()
    if lines and "," in lines[0]:
        scenes = parse_asf_csv(path)
        if scenes:
            return scenes
    scenes = _scenes_from_sources(extract_urls_from_text(text) or text.splitlines())
    if scenes:
        return scenes
    raise InputValidationError(
        f"no Sentinel-1 scenes found in metadata file {path}", code=ErrorCode.ASF001
    )
