"""DEM request planning (offline) and optional real download (Task 010 / 052).

Task 010 plans DEM acquisitions without downloading, calling external APIs, or
converting vertical datums. Task 052 adds an *optional*, opt-in real download via
the OpenTopography Global DEM API (behind the ``download`` extra); the offline
planning above never touches the network.
"""

from __future__ import annotations

from insar_prep.providers.dem.conversion_planner import (
    create_dem_conversion_plan,
    requires_geoid_conversion,
    suggest_geoid_model,
    validate_dem_conversion_plan,
)
from insar_prep.providers.dem.convert_runner import (
    DemConvertRunSummary,
    run_dem_conversion,
    write_dem_convert_results_csv,
)
from insar_prep.providers.dem.converter import (
    DemConversionOutcome,
    DemConversionResult,
    DemConverter,
    FakeDemConverter,
    RealDemConverter,
    dataset_source_vertical_datum,
    default_geoid_model_for,
)
from insar_prep.providers.dem.credentials import (
    DemKeySource,
    ResolvedDemKey,
    resolve_dem_api_key,
)
from insar_prep.providers.dem.download_runner import (
    DemDownloadRunSummary,
    run_dem_download,
    write_dem_download_results_csv,
)
from insar_prep.providers.dem.downloader import (
    DemDownloader,
    DemDownloadOutcome,
    DemDownloadRequest,
    DemDownloadResult,
    FakeDemDownloader,
    RealDemDownloader,
    dem_download_request_from_plan,
    opentopo_demtype,
)
from insar_prep.providers.dem.planner import (
    create_dem_download_task,
    create_dem_request_plan,
    validate_dem_request_plan,
)
from insar_prep.providers.dem.types import (
    DemConversionPlan,
    DemConversionReport,
    DemConversionStep,
    DemConversionStepType,
    DemPlanningIssue,
    DemPlanningReport,
    DemProvider,
    DemRequestPlan,
)

__all__ = [
    "DemConversionOutcome",
    "DemConversionPlan",
    "DemConversionReport",
    "DemConversionResult",
    "DemConversionStep",
    "DemConversionStepType",
    "DemConvertRunSummary",
    "DemConverter",
    "DemDownloadOutcome",
    "DemDownloadRequest",
    "DemDownloadResult",
    "DemDownloadRunSummary",
    "DemDownloader",
    "DemKeySource",
    "DemPlanningIssue",
    "DemPlanningReport",
    "DemProvider",
    "DemRequestPlan",
    "FakeDemConverter",
    "FakeDemDownloader",
    "RealDemConverter",
    "RealDemDownloader",
    "ResolvedDemKey",
    "create_dem_conversion_plan",
    "create_dem_download_task",
    "create_dem_request_plan",
    "dataset_source_vertical_datum",
    "default_geoid_model_for",
    "dem_download_request_from_plan",
    "opentopo_demtype",
    "requires_geoid_conversion",
    "resolve_dem_api_key",
    "run_dem_conversion",
    "run_dem_download",
    "suggest_geoid_model",
    "validate_dem_conversion_plan",
    "validate_dem_request_plan",
    "write_dem_convert_results_csv",
    "write_dem_download_results_csv",
]
