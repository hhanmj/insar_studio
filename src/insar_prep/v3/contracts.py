"""Unified provider contracts for the v3 backend migration.

The classes here intentionally mirror the Rust ``insar-core`` skeleton closely,
but stay in Python/Pydantic so the current desktop API can adopt them
incrementally before any native bridge is introduced.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from insar_prep.core.models import Aoi, BBox, InsarBaseModel, Scene


class DataSourceKind(StrEnum):
    """High-level source families supported by the v3 provider registry."""

    SENTINEL1 = "sentinel1"
    SENTINEL2 = "sentinel2"
    SENTINEL3 = "sentinel3"
    DEM = "dem"
    GACOS = "gacos"
    PLANET = "planet"
    USER_LOCAL = "user_local"


class ProductKind(StrEnum):
    """Normalized product categories across providers."""

    SAR_SLC = "sar_slc"
    SAR_GRD = "sar_grd"
    OPTICAL_SCENE = "optical_scene"
    DEM_RASTER = "dem_raster"
    ATMOSPHERE_DELAY = "atmosphere_delay"
    ORBIT_FILE = "orbit_file"
    LOCAL_FILE = "local_file"


class ProviderCapability(StrEnum):
    """Provider capabilities used for registry filtering."""

    SEARCH = "search"
    PLAN = "plan"
    DOWNLOAD = "download"
    IMPORT = "import"
    CREDENTIALS = "credentials"
    LOCAL_FILES = "local_files"
    ATMOSPHERIC_CORRECTION = "atmospheric_correction"


class ProviderExecutionMode(StrEnum):
    """How a provider plan can be executed by the app shell."""

    DIRECT_DOWNLOAD = "direct_download"
    MANUAL_WEB_FORM = "manual_web_form"
    BROWSER_ASSISTED_WEB_FORM = "browser_assisted_web_form"
    LOCAL_IMPORT = "local_import"


class AssetRole(StrEnum):
    """Role of a file or URL attached to a product or plan item."""

    PRIMARY = "primary"
    METADATA = "metadata"
    THUMBNAIL = "thumbnail"
    BROWSE = "browse"
    AUXILIARY = "auxiliary"
    DERIVED = "derived"


class TimeRange(InsarBaseModel):
    """Inclusive time range for provider queries."""

    start: datetime | None = None
    end: datetime | None = None


class ProviderMetadata(InsarBaseModel):
    """Static provider description."""

    provider_id: str
    display_name: str
    source_kind: DataSourceKind
    version: str = "0.1.0"
    capabilities: list[ProviderCapability] = Field(default_factory=list)


class ProviderAsset(InsarBaseModel):
    """A URL or local file-like asset associated with a normalized product."""

    role: AssetRole
    url: str | None = None
    file_name: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None


class ProviderProduct(InsarBaseModel):
    """Provider-neutral product summary."""

    provider_id: str
    product_id: str
    display_name: str
    source_kind: DataSourceKind
    product_kind: ProductKind
    acquisition_datetime: datetime | None = None
    footprint_bbox: BBox | None = None
    assets: list[ProviderAsset] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProviderQuery(InsarBaseModel):
    """Provider-neutral query and planning input.

    ``processing_aoi`` and ``scenes`` are Python migration fields. They let the
    v3 adapters reuse the existing Pydantic core models without changing the UI
    bridge yet. Later bridge contracts can serialize them explicitly.
    """

    provider_id: str | None = None
    source_kind: DataSourceKind | None = None
    product_kinds: list[ProductKind] = Field(default_factory=list)
    bbox: BBox | None = None
    processing_aoi: Aoi | None = None
    scenes: list[Scene] = Field(default_factory=list)
    time_range: TimeRange | None = None
    max_results: int | None = Field(default=None, ge=1)
    region_id: str = "region"
    region_safe_name: str = "region"
    output_root: Path | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class ProviderPlanItem(InsarBaseModel):
    """One normalized planned output item."""

    product_id: str
    target_path: Path
    role: AssetRole = AssetRole.PRIMARY
    expected_size_bytes: int | None = None
    status: str = "planned"
    properties: dict[str, Any] = Field(default_factory=dict)


class ProviderPlan(InsarBaseModel):
    """Provider-neutral planning result.

    ``legacy_plan`` and ``legacy_report`` keep the current mature planner output
    available while the UI and task runner migrate to normalized fields.
    """

    provider_id: str
    source_kind: DataSourceKind
    output_root: Path
    items: list[ProviderPlanItem] = Field(default_factory=list)
    requires_credentials: bool = False
    manual_action_required: bool = False
    execution_mode: ProviderExecutionMode = ProviderExecutionMode.DIRECT_DOWNLOAD
    submission: dict[str, Any] = Field(default_factory=dict)
    legacy_plan: dict[str, Any] = Field(default_factory=dict)
    legacy_report: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Unified provider adapter interface for current Python providers."""

    def metadata(self) -> ProviderMetadata:
        """Return static provider metadata."""
        ...

    def search(self, query: ProviderQuery) -> list[ProviderProduct]:
        """Return normalized product summaries without executing downloads."""
        ...

    def plan(
        self,
        query: ProviderQuery,
        products: list[ProviderProduct] | None = None,
    ) -> ProviderPlan:
        """Return a normalized offline plan."""
        ...
