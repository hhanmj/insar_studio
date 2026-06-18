"""Enumerations for the InSAR Data Preparation Assistant core data models.

All values are plain strings (``StrEnum``) so the models serialize cleanly to
JSON without custom encoders. Members follow ``DEVELOPMENT_MANUAL.md`` sections
7, 10, 11, 12, and 14.
"""

from __future__ import annotations

from enum import StrEnum


class TargetSoftware(StrEnum):
    """Target processing software a project prepares data for."""

    SARSCAPE = "SARSCAPE"


class TaskStatus(StrEnum):
    """Status of a single download/processing task (manual section 12.3)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    WAITING_FOR_USER = "WAITING_FOR_USER"


class JobStatus(StrEnum):
    """Status of a job (a group of tasks; manual section 12.4)."""

    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"
    CANCELLED = "CANCELLED"


class CoverageStatus(StrEnum):
    """AOI coverage status (manual section 10.2)."""

    COVERED = "COVERED"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"
    NOT_COVERED = "NOT_COVERED"
    UNKNOWN = "UNKNOWN"


class OrbitDirection(StrEnum):
    """Sentinel-1 orbit direction."""

    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"
    UNKNOWN = "UNKNOWN"


class Platform(StrEnum):
    """Sentinel-1 platform (manual section 11.4)."""

    S1A = "S1A"
    S1B = "S1B"
    S1C = "S1C"
    S1D = "S1D"
    UNKNOWN = "UNKNOWN"


class ProductType(StrEnum):
    """SAR product type (phase one targets SLC)."""

    RAW = "RAW"
    SLC = "SLC"
    GRD = "GRD"
    OCN = "OCN"


class BeamMode(StrEnum):
    """SAR beam mode (phase one targets IW)."""

    SM = "SM"
    IW = "IW"
    EW = "EW"
    WV = "WV"


class Polarization(StrEnum):
    """SAR polarization.

    Includes channel-style values (manual section 11.4) and the Sentinel-1
    product polarization codes (``SH``/``SV``/``DH``/``DV``) so dual-pol products
    are never collapsed to a single channel.
    """

    VV = "VV"
    VH = "VH"
    VV_VH = "VV_VH"
    HH = "HH"
    HV = "HV"
    SH = "SH"
    SV = "SV"
    DH = "DH"
    DV = "DV"
    UNKNOWN = "UNKNOWN"


class Provider(StrEnum):
    """External data provider for a task or product."""

    ASF = "ASF"
    OPENTOPOGRAPHY = "OPENTOPOGRAPHY"
    GACOS = "GACOS"
    ERA5 = "ERA5"
    USER_LOCAL = "USER_LOCAL"


class TaskType(StrEnum):
    """Type of a download/processing task."""

    DOWNLOAD_SLC = "DOWNLOAD_SLC"
    DOWNLOAD_ORBIT = "DOWNLOAD_ORBIT"
    DOWNLOAD_DEM = "DOWNLOAD_DEM"
    MATCH_ORBIT = "MATCH_ORBIT"
    IMPORT_GACOS = "IMPORT_GACOS"


class AoiSource(StrEnum):
    """How a region's AOI was provided (manual section 8.2)."""

    MANUAL_BBOX = "MANUAL_BBOX"
    VECTOR_FILE = "VECTOR_FILE"
    ADMIN_BOUNDARY = "ADMIN_BOUNDARY"
    MAP_DRAW = "MAP_DRAW"
    COPIED = "COPIED"


class VerticalDatum(StrEnum):
    """DEM vertical datum (manual section 14.3)."""

    WGS84_ELLIPSOID = "WGS84_ELLIPSOID"
    EGM96 = "EGM96"
    EGM2008 = "EGM2008"
    ORTHOMETRIC = "ORTHOMETRIC"
    UNKNOWN = "UNKNOWN"


class DemDataset(StrEnum):
    """Supported DEM datasets (manual section 14.1)."""

    COP30 = "COP30"
    COP90 = "COP90"
    SRTM_GL1 = "SRTM_GL1"
    SRTM_GL1_ELLIPSOIDAL = "SRTM_GL1_ELLIPSOIDAL"
    NASADEM = "NASADEM"
    AW3D30 = "AW3D30"
    AW3D30_ELLIPSOIDAL = "AW3D30_ELLIPSOIDAL"
    USER_LOCAL = "USER_LOCAL"


class AoiRole(StrEnum):
    """The role an AOI plays in the workflow (manual section 8.1)."""

    SLC_FOOTPRINT = "SLC_FOOTPRINT"
    PROCESSING_AOI = "PROCESSING_AOI"
    DOWNLOAD_AOI = "DOWNLOAD_AOI"


class MultiFeatureMode(StrEnum):
    """How to turn a multi-feature vector input into regions (manual 8.5)."""

    MERGE_TO_ONE_REGION = "MERGE_TO_ONE_REGION"
    SELECT_ONE_FEATURE = "SELECT_ONE_FEATURE"
    SPLIT_TO_REGIONS = "SPLIT_TO_REGIONS"
