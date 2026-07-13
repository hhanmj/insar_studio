from __future__ import annotations

from insar_prep.providers.dem.routing import (
    DemRouteRequest,
    DemSource,
    default_source_profiles,
    rank_dem_sources,
)


def test_default_profiles_include_open_sources() -> None:
    profiles = default_source_profiles()
    sources = {profile.source for profile in profiles}
    assert DemSource.COPERNICUS in sources
    assert DemSource.SRTM in sources
    assert DemSource.NASADEM in sources
    assert DemSource.FABDEM in sources


def test_rank_dem_sources_prefers_proxy_and_preference() -> None:
    request = DemRouteRequest(
        dataset="COP30",
        country_code="CN",
        proxy_enabled=True,
        preferred_sources=[DemSource.NASADEM],
    )
    plan = rank_dem_sources(request)

    assert plan.candidates
    assert plan.chosen in {candidate.source for candidate in plan.candidates}
    assert plan.candidates[0].score >= plan.candidates[-1].score


def test_rank_dem_sources_penalizes_regional_sources() -> None:
    request = DemRouteRequest(dataset="COP30", country_code="CN", proxy_enabled=False)
    plan = rank_dem_sources(request)

    ranked_sources = [candidate.source for candidate in plan.candidates[:3]]
    assert DemSource.ARCTICDEM not in ranked_sources
    assert DemSource.REMA not in ranked_sources
