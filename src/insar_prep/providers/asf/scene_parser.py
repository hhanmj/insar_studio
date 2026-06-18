"""Sentinel-1 SLC scene-name parsing (Task 006).

Parses Sentinel-1 SLC granule names (from a bare name or a download URL) into a
:class:`~insar_prep.core.models.Scene`. No network access and no script
execution. Non Sentinel-1 / non-SLC names raise ``InputValidationError``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from insar_prep.core.enums import BeamMode, Platform, Polarization, ProductType
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.core.models import Scene

logger = get_logger("providers.asf.scene")

# Sentinel-1 IW SLC product identifier, e.g.
# S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234
_S1_SLC_RE = re.compile(
    r"^S1(?P<sat>[ABC])_IW_SLC(?P<res>[FHM_])_(?P<level>\d)(?P<cls>[SA])(?P<pol>SH|SV|DH|DV)"
    r"_(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_(?P<orbit>\d{6})"
    r"_(?P<datatake>[0-9A-Fa-f]{6})(?:_(?P<unique>[0-9A-Fa-f]{4}))?$"
)

# Sentinel-1 polarization codes -> available Polarization enum members.
# Note: the project Polarization enum has no HH+HV member, so "DH" maps to HH.
_POL_MAP = {
    "SV": Polarization.VV,
    "SH": Polarization.HH,
    "DV": Polarization.VV_VH,
    "DH": Polarization.HH,
}

_EXTENSIONS = (".zip", ".SAFE", ".safe")


def _granule_base(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        candidate = candidate.split("?", 1)[0].rsplit("/", 1)[-1]
    else:
        candidate = candidate.replace("\\", "/").rsplit("/", 1)[-1]
    for extension in _EXTENSIONS:
        if candidate.endswith(extension):
            return candidate[: -len(extension)]
    return candidate


def parse_scene_name(scene_name_or_url: str) -> Scene:
    """Parse a Sentinel-1 SLC granule name or URL into a :class:`Scene`."""
    base = _granule_base(scene_name_or_url)
    match = _S1_SLC_RE.match(base)
    if match is None:
        raise InputValidationError(
            f"not a Sentinel-1 IW SLC granule: {scene_name_or_url!r}",
            code=ErrorCode.ASF001,
        )
    url = scene_name_or_url.strip() if "://" in scene_name_or_url else None
    acquired = datetime.strptime(match["start"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    logger.debug("parsed Sentinel-1 SLC granule %r", base)
    return Scene(
        scene_id=base,
        platform=Platform(f"S1{match['sat']}"),
        product_type=ProductType.SLC,
        beam_mode=BeamMode.IW,
        polarization=_POL_MAP.get(match["pol"], Polarization.VV),
        acquisition_datetime=acquired,
        absolute_orbit=int(match["orbit"]),
        url=url,
    )


def deduplicate_scenes(scenes: list[Scene]) -> tuple[list[Scene], list[str]]:
    """Drop scenes with duplicate ``scene_id``; return (unique, duplicate_ids)."""
    seen: set[str] = set()
    unique: list[Scene] = []
    duplicates: list[str] = []
    for scene in scenes:
        if scene.scene_id in seen:
            duplicates.append(scene.scene_id)
        else:
            seen.add(scene.scene_id)
            unique.append(scene)
    return unique, duplicates
