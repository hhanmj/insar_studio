"""ASF (Alaska Satellite Facility) cart/scene parsing and SLC download.

Cart/scene parsing and the dry-run download planner are strictly offline (no
network, no credentials). Real, credentialed Sentinel-1 SLC download lives in
:class:`RealAsfDownloader` and is gated behind the optional ``download`` extra
(``requests``), explicit ``--download-mode real`` opt-in, and NASA Earthdata
credentials resolved at the auth boundary.
"""

from __future__ import annotations

from insar_prep.providers.asf.cart_parser import (
    extract_urls_from_text,
    parse_asf_cart_file,
    parse_asf_csv,
    parse_asf_geojson,
    parse_asf_python_script,
    parse_url_text,
)
from insar_prep.providers.asf.credentials import (
    EARTHDATA_TOKEN_ENV,
    CredentialSource,
    ResolvedCredential,
    resolve_credentials,
)
from insar_prep.providers.asf.download_plan import (
    ASF_PLAN_COLUMNS,
    ASF_PLAN_SUBDIR,
    SLC_SUBDIR,
    AsfDownloadPlan,
    AsfDownloadPlanItem,
    AsfPlanStatus,
    asf_download_plan_paths,
    build_asf_download_plan,
    write_asf_download_plan,
)
from insar_prep.providers.asf.downloader import (
    AsfDownloader,
    DownloadOutcome,
    DownloadRequest,
    DownloadResult,
    FakeAsfDownloader,
    RealAsfDownloader,
    build_earthdata_session,
    download_requests_from_scenes,
)
from insar_prep.providers.asf.scene_parser import deduplicate_scenes, parse_scene_name

__all__ = [
    "ASF_PLAN_COLUMNS",
    "ASF_PLAN_SUBDIR",
    "EARTHDATA_TOKEN_ENV",
    "SLC_SUBDIR",
    "AsfDownloadPlan",
    "AsfDownloadPlanItem",
    "AsfDownloader",
    "AsfPlanStatus",
    "CredentialSource",
    "DownloadOutcome",
    "DownloadRequest",
    "DownloadResult",
    "FakeAsfDownloader",
    "RealAsfDownloader",
    "ResolvedCredential",
    "asf_download_plan_paths",
    "build_asf_download_plan",
    "build_earthdata_session",
    "deduplicate_scenes",
    "download_requests_from_scenes",
    "extract_urls_from_text",
    "parse_asf_cart_file",
    "parse_asf_csv",
    "parse_asf_geojson",
    "parse_asf_python_script",
    "parse_scene_name",
    "parse_url_text",
    "resolve_credentials",
    "write_asf_download_plan",
]
