"""Routing helpers for choosing the fastest available DEM source."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from insar_prep.core.models import InsarBaseModel


class DemSource(StrEnum):
    """Open DEM sources that can be integrated in routing."""

    OPENTOPOGRAPHY = "OPENTOPOGRAPHY"
    COPERNICUS = "COPERNICUS_GLO30_GLO90"
    SRTM = "SRTMGL1_SRTMGL3"
    NASADEM = "NASADEM"
    ASTER = "ASTER_GDEM_V3"
    AW3D30 = "ALOS_AW3D30"
    FABDEM = "FABDEM"
    ARCTICDEM = "ARCTICDEM"
    REMA = "REMA"


class DemSourceProfile(InsarBaseModel):
    """Runtime characteristics used to rank a DEM source."""

    source: DemSource
    supports_proxy: bool = True
    supports_global_coverage: bool = True
    priority: int = 100
    median_latency_ms_cn: int = 1200
    notes: str = ""


class DemRouteRequest(InsarBaseModel):
    """Input contract for DEM source routing."""

    dataset: str
    country_code: str = "CN"
    proxy_enabled: bool = False
    preferred_sources: list[DemSource] = Field(default_factory=list)


class DemRouteCandidate(InsarBaseModel):
    """One ranked candidate source."""

    source: DemSource
    score: int
    reason: str


class DemRoutePlan(InsarBaseModel):
    """Routing output with one chosen source and ranked candidates."""

    chosen: DemSource
    candidates: list[DemRouteCandidate]


def default_source_profiles() -> list[DemSourceProfile]:
    """Return baseline routing defaults tuned for broad public access."""
    return [
        DemSourceProfile(
            source=DemSource.COPERNICUS,
            priority=10,
            median_latency_ms_cn=700,
            notes="preferred baseline source for global DEM and better mirrors",
        ),
        DemSourceProfile(source=DemSource.SRTM, priority=20, median_latency_ms_cn=850),
        DemSourceProfile(source=DemSource.NASADEM, priority=30, median_latency_ms_cn=950),
        DemSourceProfile(source=DemSource.FABDEM, priority=35, median_latency_ms_cn=900),
        DemSourceProfile(source=DemSource.OPENTOPOGRAPHY, priority=40, median_latency_ms_cn=1400),
        DemSourceProfile(source=DemSource.ASTER, priority=50, median_latency_ms_cn=1300),
        DemSourceProfile(source=DemSource.AW3D30, priority=60, median_latency_ms_cn=1500),
        DemSourceProfile(
            source=DemSource.ARCTICDEM,
            supports_global_coverage=False,
            priority=70,
            median_latency_ms_cn=1100,
            notes="regional source, mostly polar regions",
        ),
        DemSourceProfile(
            source=DemSource.REMA,
            supports_global_coverage=False,
            priority=80,
            median_latency_ms_cn=1100,
            notes="regional source, mostly Antarctic",
        ),
    ]


def rank_dem_sources(
    request: DemRouteRequest,
    *,
    profiles: list[DemSourceProfile] | None = None,
) -> DemRoutePlan:
    """Rank DEM sources for speed and resilience in the current network profile."""
    active = profiles or default_source_profiles()
    preferred = set(request.preferred_sources)
    candidates: list[DemRouteCandidate] = []

    for profile in active:
        score = 1000 - profile.priority
        score -= int(profile.median_latency_ms_cn / 10)
        if request.country_code.upper() == "CN" and profile.source is DemSource.OPENTOPOGRAPHY:
            score -= 40
        if request.proxy_enabled and profile.supports_proxy:
            score += 50
        if profile.source in preferred:
            score += 120
        if not profile.supports_global_coverage:
            score -= 80
        candidates.append(
            DemRouteCandidate(
                source=profile.source,
                score=score,
                reason=profile.notes or "ranked by latency, availability, and policy",
            )
        )

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    return DemRoutePlan(chosen=ranked[0].source, candidates=ranked)
