"""Core data models for the InSAR Data Preparation Assistant (Task 002).

These are in-memory data structures only. They model the multi-region hierarchy
``Workspace -> Project -> Region -> Job -> Task`` plus per-region products
(scenes, DEMs, atmospheric products). They contain no GUI, network, download, or
logging logic.

Validation is provided natively by pydantic v2: unknown fields, invalid enum
values, out-of-range coordinates, malformed ``safe_name`` values, and invalid
SARscape DEM filenames all raise ``pydantic.ValidationError``.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from insar_prep.core.enums import (
    AoiRole,
    AoiSource,
    BeamMode,
    CoverageStatus,
    JobStatus,
    OrbitDirection,
    Platform,
    Polarization,
    ProductType,
    Provider,
    TargetSoftware,
    TaskStatus,
    TaskType,
    VerticalDatum,
)

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry

# A SARscape-safe snake_case name: lowercase letters/digits, single underscores
# between groups, no leading/trailing/double underscores. Generation of such
# names is intentionally deferred to Task 003; here we only validate.
SAFE_NAME_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
SafeName = Annotated[str, StringConstraints(pattern=SAFE_NAME_PATTERN)]


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(tz=UTC)


def generate_id(prefix: str) -> str:
    """Return a reasonably unique identifier such as ``ws_20260618_a1b2c3``."""
    return f"{prefix}_{_utcnow():%Y%m%d}_{secrets.token_hex(3)}"


class InsarBaseModel(BaseModel):
    """Base model: forbids unknown fields and validates on assignment."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (datetime -> ISO, enum -> value, Path -> str)."""
        return self.model_dump(mode="json")

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a JSON string representation."""
        return self.model_dump_json(indent=indent)


class BBox(InsarBaseModel):
    """A geographic bounding box in lon/lat degrees."""

    west: float
    east: float
    south: float
    north: float
    crs: str = "EPSG:4326"

    @field_validator("west", "east")
    @classmethod
    def _check_longitude(cls, value: float) -> float:
        if not -180.0 <= value <= 180.0:
            raise ValueError("longitude must be within [-180, 180]")
        return value

    @field_validator("south", "north")
    @classmethod
    def _check_latitude(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError("latitude must be within [-90, 90]")
        return value

    @model_validator(mode="after")
    def _check_ordering(self) -> BBox:
        if self.west >= self.east:
            raise ValueError("west must be strictly less than east")
        if self.south >= self.north:
            raise ValueError("south must be strictly less than north")
        return self

    def to_polygon(self) -> BaseGeometry:
        """Return this bbox as a shapely rectangle polygon."""
        from shapely.geometry import box

        return box(self.west, self.south, self.east, self.north)

    def buffer(self, degrees: float) -> BBox:
        """Return a new bbox expanded by ``degrees`` on each side (clamped)."""
        if degrees < 0:
            raise ValueError("buffer degrees must be non-negative")
        return BBox(
            west=max(-180.0, self.west - degrees),
            east=min(180.0, self.east + degrees),
            south=max(-90.0, self.south - degrees),
            north=min(90.0, self.north + degrees),
            crs=self.crs,
        )


class AoiBuffer(InsarBaseModel):
    """Auxiliary-product download buffers in degrees (manual section 8.6)."""

    dem: float = Field(default=0.02, ge=0.0)
    gacos: float = Field(default=0.05, ge=0.0)
    era5: float = Field(default=0.25, ge=0.0)


class Aoi(InsarBaseModel):
    """A region's processing area of interest."""

    source: AoiSource
    role: AoiRole = AoiRole.PROCESSING_AOI
    bbox: BBox | None = None
    geometry_path: Path | None = None
    crs: str = "EPSG:4326"
    buffer: AoiBuffer = Field(default_factory=AoiBuffer)


class BoundaryCompliance(InsarBaseModel):
    """Administrative boundary provenance metadata (manual section 9.3)."""

    country: str | None = None
    requires_review_number: bool = False
    boundary_source: str | None = None
    provider: str | None = None
    review_number: str | None = None
    import_date: date | None = None
    license_or_terms: str | None = None
    admin_level: str | None = None
    name_field: str | None = None
    crs: str | None = None
    file_path: Path | None = None
    notes: str = ""


class AoiFeature(InsarBaseModel):
    """A lightweight AOI feature (geometry kept as WKT/bbox for serialization)."""

    feature_id: str = Field(default_factory=lambda: generate_id("feature"))
    name: str = ""
    geometry_wkt: str | None = None
    bbox: BBox | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class Scene(InsarBaseModel):
    """A single SAR scene (manual section 7.4)."""

    scene_id: str = Field(default_factory=lambda: generate_id("scene"))
    platform: Platform = Platform.UNKNOWN
    sensor: str = ""
    product_type: ProductType = ProductType.SLC
    beam_mode: BeamMode = BeamMode.IW
    polarization: Polarization = Polarization.VV
    acquisition_datetime: datetime | None = None
    orbit_direction: OrbitDirection = OrbitDirection.UNKNOWN
    relative_orbit: int | None = None
    absolute_orbit: int | None = None
    frame: int | None = None
    path: int | None = None
    url: str | None = None
    local_path: Path | None = None
    file_size_remote: int | None = None
    file_size_local: int | None = None
    checksum: str | None = None
    download_status: TaskStatus = TaskStatus.PENDING
    zip_valid: bool | None = None
    processing_aoi_id: str | None = None
    processing_aoi_name: str | None = None
    asf_footprint_coverage: CoverageStatus = CoverageStatus.UNKNOWN
    safe_metadata_coverage: CoverageStatus = CoverageStatus.UNKNOWN
    coverage_warning: str | None = None


class DemProduct(InsarBaseModel):
    """A DEM product record (manual section 7.6)."""

    dem_id: str = Field(default_factory=lambda: generate_id("dem"))
    region_id: str
    source: Provider
    dataset: str
    resolution: float | None = None
    original_vertical_datum: VerticalDatum = VerticalDatum.UNKNOWN
    target_vertical_datum: VerticalDatum = VerticalDatum.WGS84_ELLIPSOID
    geoid_model: str | None = None
    is_dsm: bool = False
    is_ellipsoidal: bool = False
    input_path: Path | None = None
    ellipsoid_output_path: Path | None = None
    sarscape_ready_path: Path | None = None
    aoi_bbox: BBox | None = None
    crs: str | None = None
    nodata: float | None = None
    min_elevation: float | None = None
    max_elevation: float | None = None
    mean_elevation: float | None = None
    processing_log: Path | None = None

    @field_validator("sarscape_ready_path")
    @classmethod
    def _check_dem_suffix(cls, value: Path | None) -> Path | None:
        # Validation only; renaming/path generation belongs to Task 003 / DEM adapter.
        if value is not None and not value.name.endswith("_dem.tif"):
            raise ValueError("SARscape-ready DEM filename must end with '_dem.tif'")
        return value


class AtmosphericProduct(InsarBaseModel):
    """An atmospheric (e.g. GACOS) product record (manual section 7.7)."""

    atmo_id: str = Field(default_factory=lambda: generate_id("atmo"))
    region_id: str
    provider: Provider
    method: str
    date: date
    input_path: Path | None = None
    output_path: Path | None = None
    coverage_status: CoverageStatus = CoverageStatus.UNKNOWN
    matched_scene_ids: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    notes: str = ""


class DownloadTask(InsarBaseModel):
    """The smallest executable unit: one download/processing task (section 7.5)."""

    task_id: str = Field(default_factory=lambda: generate_id("task"))
    job_id: str
    region_id: str
    provider: Provider
    task_type: TaskType
    priority: int = 0
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    local_path: Path | None = None
    status: TaskStatus = TaskStatus.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    retry_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class Job(InsarBaseModel):
    """A user-initiated group of tasks (manual sections 2 and 12.4)."""

    job_id: str = Field(default_factory=lambda: generate_id("job"))
    project_id: str
    name: str
    status: JobStatus = JobStatus.NOT_STARTED
    region_ids: list[str] = Field(default_factory=list)
    tasks: list[DownloadTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    notes: str = ""


class Region(InsarBaseModel):
    """A concrete processing region within a project (manual section 7.3)."""

    region_id: str = Field(default_factory=lambda: generate_id("region"))
    project_id: str
    region_name: str
    region_safe_name: SafeName
    region_root: Path
    aoi: Aoi
    boundary_compliance: BoundaryCompliance | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    scenes: list[Scene] = Field(default_factory=list)
    dem_products: list[DemProduct] = Field(default_factory=list)
    atmospheric_products: list[AtmosphericProduct] = Field(default_factory=list)


class Project(InsarBaseModel):
    """A research theme or one data-preparation effort (manual section 7.2)."""

    project_id: str = Field(default_factory=lambda: generate_id("proj"))
    workspace_id: str
    project_name: str
    safe_name: SafeName
    project_root: Path
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    target_software: TargetSoftware = TargetSoftware.SARSCAPE
    regions: list[Region] = Field(default_factory=list)
    jobs: list[Job] = Field(default_factory=list)
    notes: str = ""


class Workspace(InsarBaseModel):
    """A top-level workspace holding multiple projects (manual section 7.1)."""

    workspace_id: str = Field(default_factory=lambda: generate_id("ws"))
    workspace_root: Path
    cache_root: Path | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    global_settings: dict[str, Any] = Field(default_factory=dict)
    projects: list[Project] = Field(default_factory=list)
