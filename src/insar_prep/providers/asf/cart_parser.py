"""ASF cart / URL file parsing (Task 006).

Parses locally exported ASF inputs (Vertex Python download scripts, URL text,
CSV, GeoJSON) into Sentinel-1 :class:`~insar_prep.core.models.Scene` lists.

Strictly local and side-effect free: the Python download script is parsed with
regex only and is never executed (no ``exec``/``eval``). No network access, no
``asf_search``, no credentials.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.core.models import Scene
from insar_prep.providers.asf.scene_parser import parse_scene_name

logger = get_logger("providers.asf.cart")

_URL_RE = re.compile(r"https?://[^\s'\"<>]+")
_ASF_HOST = "asf.alaska.edu"

_CSV_URL_KEYS = ("url", "download url")
_CSV_NAME_KEYS = ("file name", "granule name", "scene name", "filename", "granulename", "scenename")
_GEOJSON_URL_KEYS = ("url",)
_GEOJSON_NAME_KEYS = ("filename", "file name", "granulename", "scenename")


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
    """Parse an ASF CSV into scenes (URL or scene-name columns, case-insensitive)."""
    reader = csv.DictReader(io.StringIO(_read_text(path)))
    sources: list[str] = []
    for row in reader:
        normalized = {(k or "").strip().lower(): v for k, v in row.items()}
        source = _first_value(normalized, _CSV_URL_KEYS) or _first_value(normalized, _CSV_NAME_KEYS)
        if source:
            sources.append(source)
    return _scenes_from_sources(sources)


def parse_asf_geojson(path: str | Path) -> list[Scene]:
    """Parse an ASF GeoJSON into scenes from ``features[*].properties``."""
    data = json.loads(_read_text(path))
    features = data.get("features", []) if isinstance(data, dict) else []
    if not features:
        raise InputValidationError("GeoJSON contains no features", code=ErrorCode.ASF001)
    sources: list[str] = []
    for feature in features:
        properties = feature.get("properties") or {}
        normalized = {str(k).strip().lower(): v for k, v in properties.items()}
        source = _first_value(normalized, _GEOJSON_URL_KEYS) or _first_value(
            normalized, _GEOJSON_NAME_KEYS
        )
        if source:
            sources.append(source)
    return _scenes_from_sources(sources)


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
    else:
        raise InputValidationError(
            f"unsupported cart file extension: {suffix!r}", code=ErrorCode.ASF001
        )
    if not scenes:
        raise InputValidationError(
            f"no Sentinel-1 SLC scenes found in {file_path}", code=ErrorCode.ASF001
        )
    log_event(
        logger,
        EventType.ASF_CART_IMPORTED,
        f"parsed {len(scenes)} Sentinel-1 SLC scenes",
        module="asf",
        payload={"scene_count": len(scenes), "source": file_path.name},
    )
    return scenes
