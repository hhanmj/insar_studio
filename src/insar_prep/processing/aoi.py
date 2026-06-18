"""AOI input processing (Task 005).

In-memory AOI helpers: manual bbox AOIs, processing/download AOI roles, and
multi-feature handling (merge / select / split). No GUI, no network, no real
vector-file reading (that is deferred), no boundary downloads, and no real SLC
footprint extraction.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from shapely import wkt as shapely_wkt
from shapely.geometry import box
from shapely.ops import unary_union

from insar_prep.core.enums import AoiRole, AoiSource, MultiFeatureMode
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.logging import get_logger
from insar_prep.core.models import Aoi, AoiFeature, BBox, BoundaryCompliance, Region
from insar_prep.core.naming import sarscape_safe_name

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry

logger = get_logger("processing.aoi")


def make_processing_aoi_from_bbox(
    west: float,
    east: float,
    south: float,
    north: float,
    *,
    crs: str = "EPSG:4326",
) -> Aoi:
    """Build a Processing AOI from manual west/east/south/north bounds."""
    bbox = BBox(west=west, east=east, south=south, north=north, crs=crs)
    return Aoi(source=AoiSource.MANUAL_BBOX, role=AoiRole.PROCESSING_AOI, bbox=bbox, crs=crs)


def make_download_aoi(processing_aoi: Aoi, buffer_degrees: float) -> Aoi:
    """Build a Download AOI by buffering a Processing AOI's bbox."""
    if processing_aoi.bbox is None:
        raise InputValidationError("processing AOI has no bbox", code=ErrorCode.AOI001)
    buffered = processing_aoi.bbox.buffer(buffer_degrees)
    return Aoi(
        source=processing_aoi.source,
        role=AoiRole.DOWNLOAD_AOI,
        bbox=buffered,
        crs=processing_aoi.crs,
        buffer=processing_aoi.buffer,
    )


def _feature_geometry(feature: AoiFeature) -> BaseGeometry:
    if feature.geometry_wkt:
        return shapely_wkt.loads(feature.geometry_wkt)
    if feature.bbox is not None:
        bbox = feature.bbox
        return box(bbox.west, bbox.south, bbox.east, bbox.north)
    raise InputValidationError(
        f"feature {feature.feature_id!r} has no geometry", code=ErrorCode.AOI001
    )


def _bbox_from_bounds(bounds: tuple[float, float, float, float]) -> BBox:
    minx, miny, maxx, maxy = bounds
    return BBox(west=minx, east=maxx, south=miny, north=maxy)


def _region_from_geometry(
    geometry: BaseGeometry,
    region_name: str,
    *,
    project_id: str,
    region_root: str | Path | None,
) -> Region:
    safe_name = sarscape_safe_name(region_name)
    root = Path(region_root) if region_root is not None else Path("regions") / safe_name
    aoi = Aoi(
        source=AoiSource.VECTOR_FILE,
        role=AoiRole.PROCESSING_AOI,
        bbox=_bbox_from_bounds(geometry.bounds),
    )
    return Region(
        project_id=project_id,
        region_name=region_name,
        region_safe_name=safe_name,
        region_root=root,
        aoi=aoi,
    )


def merge_features_to_one_region(
    features: Sequence[AoiFeature],
    region_name: str,
    *,
    project_id: str = "",
    region_root: str | Path | None = None,
) -> Region:
    """Merge all features into a single Region (manual 8.5.1)."""
    if not features:
        raise InputValidationError("no features to merge", code=ErrorCode.AOI002)
    geometry = unary_union([_feature_geometry(feature) for feature in features])
    logger.debug("merged %d features into region %r", len(features), region_name)
    return _region_from_geometry(
        geometry, region_name, project_id=project_id, region_root=region_root
    )


def select_feature(features: Sequence[AoiFeature], feature_id: str) -> AoiFeature:
    """Return the single feature matching ``feature_id`` (manual 8.5.2)."""
    matches = [feature for feature in features if feature.feature_id == feature_id]
    if len(matches) != 1:
        raise InputValidationError(
            f"expected exactly one feature with id {feature_id!r}, found {len(matches)}",
            code=ErrorCode.AOI002,
        )
    return matches[0]


def split_features_to_regions(
    features: Sequence[AoiFeature],
    *,
    name_field: str | None = None,
    project_id: str = "",
    base_root: str | Path = "regions",
) -> list[Region]:
    """Split each feature into its own Region (manual 8.5.3)."""
    if not features:
        raise InputValidationError("no features to split", code=ErrorCode.AOI002)
    regions: list[Region] = []
    for index, feature in enumerate(features):
        region_name = _feature_region_name(feature, name_field, index)
        geometry = _feature_geometry(feature)
        safe_name = sarscape_safe_name(region_name)
        regions.append(
            _region_from_geometry(
                geometry,
                region_name,
                project_id=project_id,
                region_root=Path(base_root) / safe_name,
            )
        )
    logger.debug("split %d features into %d regions", len(features), len(regions))
    return regions


def _feature_region_name(feature: AoiFeature, name_field: str | None, index: int) -> str:
    if name_field and name_field in feature.properties:
        return str(feature.properties[name_field])
    if feature.name:
        return feature.name
    return f"feature_{index}"


def build_regions(
    features: Sequence[AoiFeature],
    mode: MultiFeatureMode,
    *,
    region_name: str = "region",
    feature_id: str | None = None,
    name_field: str | None = None,
    project_id: str = "",
) -> list[Region]:
    """Dispatch multi-feature handling by ``mode`` and return regions."""
    if mode is MultiFeatureMode.MERGE_TO_ONE_REGION:
        return [merge_features_to_one_region(features, region_name, project_id=project_id)]
    if mode is MultiFeatureMode.SELECT_ONE_FEATURE:
        if feature_id is None:
            raise InputValidationError("feature_id is required to select", code=ErrorCode.AOI002)
        feature = select_feature(features, feature_id)
        name = feature.name or region_name
        return [merge_features_to_one_region([feature], name, project_id=project_id)]
    if mode is MultiFeatureMode.SPLIT_TO_REGIONS:
        return split_features_to_regions(features, name_field=name_field, project_id=project_id)
    raise InputValidationError(f"unknown multi-feature mode {mode!r}", code=ErrorCode.AOI002)


def validate_china_boundary_compliance(boundary_compliance: BoundaryCompliance) -> None:
    """Ensure a China administrative boundary carries review-number metadata.

    Raises :class:`InputValidationError` with code ``AOI003`` when the boundary
    is Chinese and requires a review number but none is provided. Non-China
    boundaries are not forced to carry a review number.
    """
    if (
        boundary_compliance.country == "China"
        and boundary_compliance.requires_review_number
        and not boundary_compliance.review_number
    ):
        logger.debug("china boundary compliance check failed: missing review number")
        msg = "China administrative boundary is missing review-number metadata"
        raise InputValidationError(msg, code=ErrorCode.AOI003)
