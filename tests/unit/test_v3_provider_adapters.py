"""Tests for the v3 provider adapter layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import BBox, Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.v3 import (
    AsfProviderAdapter,
    DataSourceKind,
    DemProviderAdapter,
    GacosProviderAdapter,
    ProductKind,
    ProviderCapability,
    ProviderExecutionMode,
    ProviderQuery,
    default_provider_registry,
)

_GRANULE = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
_URL = f"https://datapool.asf.alaska.edu/SLC/SA/{_GRANULE}.zip"


def test_default_registry_exposes_current_python_providers() -> None:
    registry = default_provider_registry()

    metadata = registry.metadata()
    ids = {item.provider_id for item in metadata}

    assert {"asf.sentinel1", "opentopography.dem", "gacos.atmosphere"} <= ids
    assert len(registry.by_source_kind(DataSourceKind.DEM)) == 1
    assert len(registry.with_capability(ProviderCapability.PLAN)) == 3


def test_asf_adapter_parses_sources_and_builds_legacy_plan(tmp_path: Path) -> None:
    adapter = AsfProviderAdapter()
    query = ProviderQuery(
        product_kinds=[ProductKind.SAR_SLC],
        output_root=tmp_path,
        region_safe_name="demo_region",
        filters={"scene_sources": [_URL]},
    )

    products = adapter.search(query)
    plan = adapter.plan(query, products)

    assert products[0].product_id == _GRANULE
    assert plan.provider_id == "asf.sentinel1"
    assert plan.source_kind is DataSourceKind.SENTINEL1
    assert plan.items[0].target_path == tmp_path / "SAR_Data" / "SLC" / f"{_GRANULE}.zip"
    assert plan.legacy_plan["planned_count"] == 1
    assert not (tmp_path / "SAR_Data").exists()


def test_dem_adapter_uses_existing_dem_planner(tmp_path: Path) -> None:
    adapter = DemProviderAdapter()
    query = ProviderQuery(
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        output_root=tmp_path,
        region_id="r1",
        region_safe_name="demo_region",
        filters={"dataset": "COP30"},
    )

    products = adapter.search(query)
    plan = adapter.plan(query, products)

    assert products[0].product_kind is ProductKind.DEM_RASTER
    assert plan.provider_id == "opentopography.dem"
    assert [item.properties["stage"] for item in plan.items] == [
        "raw_dem",
        "ellipsoid_dem",
        "sarscape_ready_dem",
    ]
    assert plan.legacy_plan["dataset"] == "COP30"
    assert plan.legacy_report["has_errors"] is False


def test_gacos_adapter_plans_dates_from_scenes(tmp_path: Path) -> None:
    adapter = GacosProviderAdapter()
    scenes = [
        Scene(acquisition_datetime=datetime(2024, 1, 1, 12, 0)),
        Scene(acquisition_datetime=datetime(2024, 1, 13, 12, 0)),
    ]
    query = ProviderQuery(
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        scenes=scenes,
        output_root=tmp_path,
        region_id="r1",
        region_safe_name="demo_region",
    )

    products = adapter.search(query)
    plan = adapter.plan(query, products)

    assert [product.product_id for product in products] == ["GACOS:20240101", "GACOS:20240113"]
    assert plan.manual_action_required is True
    assert plan.execution_mode is ProviderExecutionMode.BROWSER_ASSISTED_WEB_FORM
    assert len(plan.items) == 2
    assert plan.legacy_plan["scene_count"] == 2
    assert plan.legacy_report["has_errors"] is False
    assert not any(tmp_path.iterdir())


def test_gacos_adapter_exposes_browser_form_submission_payload(tmp_path: Path) -> None:
    adapter = GacosProviderAdapter()
    scenes = [
        Scene(acquisition_datetime=datetime(2024, 1, 1, 12, 0)),
        Scene(acquisition_datetime=datetime(2024, 1, 13, 12, 0)),
    ]
    query = ProviderQuery(
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        scenes=scenes,
        output_root=tmp_path,
        region_id="r1",
        region_safe_name="demo_region",
        filters={"hour": 18, "minute": 30, "output_format": "geotiff"},
    )

    plan = adapter.plan(query)

    assert plan.submission["kind"] == "web_form_submission"
    assert plan.submission["execution_mode"] == "browser_assisted_web_form"
    assert plan.submission["submit_endpoint"].endswith("/M/action_page.php")
    assert plan.submission["requires_user_confirmation"] is True
    assert plan.submission["email_field"] == "email"
    batch = plan.submission["batches"][0]
    assert batch["date_text"] == "20240101\n20240113"
    assert batch["required_sensitive_fields"] == ["email"]
    assert batch["form_fields"] == {
        "N": "25.55",
        "S": "19.95",
        "W": "109.45",
        "E": "117.55",
        "H": "18",
        "M": "30",
        "date": "20240101\n20240113",
        "type": "2",
        "seq": "OSM Map",
    }


def test_adapter_rejects_invalid_bbox() -> None:
    with pytest.raises((ValueError, InputValidationError)):
        ProviderQuery(
            bbox=BBox(west=117.5, east=109.5, south=20.0, north=25.5),
            filters={"dataset": "COP30"},
        )
