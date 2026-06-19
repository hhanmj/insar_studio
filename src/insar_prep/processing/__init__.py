"""Processing utilities.

Task 005 implements the AOI processing helpers. Download/DEM/GACOS/orbit
processing are added in later tasks.
"""

from __future__ import annotations

from insar_prep.processing.aoi import (
    build_regions,
    make_download_aoi,
    make_processing_aoi_from_bbox,
    merge_features_to_one_region,
    select_feature,
    split_features_to_regions,
    validate_china_boundary_compliance,
)
from insar_prep.processing.aoi_import import (
    geometry_to_processing_aoi,
    load_aoi_from_geojson,
    load_aoi_from_wkt,
)

__all__ = [
    "build_regions",
    "geometry_to_processing_aoi",
    "load_aoi_from_geojson",
    "load_aoi_from_wkt",
    "make_download_aoi",
    "make_processing_aoi_from_bbox",
    "merge_features_to_one_region",
    "select_feature",
    "split_features_to_regions",
    "validate_china_boundary_compliance",
]
