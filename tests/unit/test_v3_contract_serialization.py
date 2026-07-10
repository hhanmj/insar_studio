from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from insar_prep.core.models import BBox, Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.v3 import (
    AssetRole,
    DataSourceKind,
    GacosProviderAdapter,
    ProductKind,
    ProviderAsset,
    ProviderCapability,
    ProviderExecutionMode,
    ProviderMetadata,
    ProviderPlan,
    ProviderPlanItem,
    ProviderProduct,
    ProviderQuery,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHAPE_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "v3_provider_contract_shape.json"
_BRIDGE_TS = _REPO_ROOT / "ui" / "src" / "lib" / "bridge.ts"


def _shape() -> dict[str, Any]:
    return json.loads(_SHAPE_FIXTURE.read_text(encoding="utf-8"))


def _assert_required_and_forbidden_keys(
    payload: dict[str, Any],
    section: dict[str, Any],
) -> None:
    for key in section["required_keys"]:
        assert key in payload
    for key in section["forbidden_keys"]:
        assert key not in payload


def _assert_sample_values(payload: dict[str, Any], sample: dict[str, Any]) -> None:
    for key, value in sample.items():
        assert payload[key] == value


def _type_block(source: str, type_name: str) -> str:
    marker = f"export type {type_name} ="
    start = source.index(marker)
    end = source.index("\n};", start)
    return source[start:end]


def _declares_property(type_block: str, key: str) -> bool:
    return any(
        line.strip().startswith(f"{key}?:") or line.strip().startswith(f"{key}:")
        for line in type_block.splitlines()
    )


def _assert_gacos_submission_matches_fixture(submission: dict[str, Any]) -> None:
    section = _shape()["gacos_submission"]
    _assert_required_and_forbidden_keys(submission, section)
    _assert_sample_values(
        {key: submission[key] for key in section["sample"]},
        section["sample"],
    )
    batches = submission["batches"]
    assert isinstance(batches, list)
    assert len(batches) == 1
    batch = batches[0]
    for key in section["batch_required_keys"]:
        assert key in batch
    assert batch["batch_id"].startswith(section["batch_id_prefix"])
    _assert_sample_values(
        {key: batch[key] for key in section["batch_sample"]},
        section["batch_sample"],
    )
    assert sorted(batch["form_fields"]) == sorted(section["form_field_keys"])


def test_v3_contract_json_uses_shared_provider_field_names() -> None:
    section = _shape()["metadata"]
    metadata = ProviderMetadata(
        provider_id=section["sample"]["provider_id"],
        display_name=section["sample"]["display_name"],
        source_kind=DataSourceKind(section["sample"]["source_kind"]),
        capabilities=[
            ProviderCapability.SEARCH,
            ProviderCapability.PLAN,
            ProviderCapability.DOWNLOAD,
            ProviderCapability.CREDENTIALS,
        ],
    ).model_dump(mode="json")

    _assert_required_and_forbidden_keys(metadata, section)
    _assert_sample_values(metadata, section["sample"])


def test_v3_product_and_plan_json_match_rust_contract_keys() -> None:
    shape = _shape()
    product_section = shape["product"]
    plan_item_section = shape["plan_item"]
    sample_product = product_section["sample"]
    sample_item = plan_item_section["sample"]
    bbox = BBox(**sample_product["footprint_bbox"])
    product = ProviderProduct(
        provider_id=sample_product["provider_id"],
        product_id=sample_product["product_id"],
        display_name=sample_product["display_name"],
        source_kind=DataSourceKind.SENTINEL1,
        product_kind=ProductKind.SAR_SLC,
        acquisition_datetime=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        footprint_bbox=bbox,
        assets=[
            ProviderAsset(
                role=AssetRole.PRIMARY,
                url=sample_product["assets"][0]["url"],
                file_name=sample_product["assets"][0]["file_name"],
                media_type=sample_product["assets"][0]["media_type"],
                size_bytes=sample_product["assets"][0]["size_bytes"],
            )
        ],
        properties=sample_product["properties"],
    ).model_dump(mode="json")
    plan = ProviderPlan(
        provider_id=sample_product["provider_id"],
        source_kind=DataSourceKind.SENTINEL1,
        output_root=Path("E:/InSAR/work"),
        items=[
            ProviderPlanItem(
                product_id=sample_item["product_id"],
                target_path=Path(sample_item["target_path"]),
                role=AssetRole.PRIMARY,
                expected_size_bytes=sample_item["expected_size_bytes"],
            )
        ],
        execution_mode=ProviderExecutionMode.DIRECT_DOWNLOAD,
    ).model_dump(mode="json")

    _assert_required_and_forbidden_keys(product, product_section)
    _assert_sample_values(
        {key: product[key] for key in sample_product},
        sample_product,
    )
    _assert_required_and_forbidden_keys(plan["items"][0], plan_item_section)
    plan_item = {
        **plan["items"][0],
        "target_path": plan["items"][0]["target_path"].replace("\\", "/"),
    }
    _assert_sample_values(plan_item, sample_item)
    assert plan["execution_mode"] == "direct_download"


def test_typescript_bridge_declares_shared_v3_contract_keys() -> None:
    shape = _shape()
    bridge = _BRIDGE_TS.read_text(encoding="utf-8")
    blocks = {
        "metadata": _type_block(bridge, "ProviderInfo"),
        "product": _type_block(bridge, "V3ProviderProduct"),
        "plan_item": _type_block(bridge, "V3PlanItem"),
    }

    for section_name, block in blocks.items():
        section = shape[section_name]
        for key in section["required_keys"]:
            assert _declares_property(block, key)
        for key in section["forbidden_keys"]:
            assert not _declares_property(block, key)
    for mode in shape["execution_modes"]:
        assert mode in bridge

    submission_block = _type_block(bridge, "V3GacosSubmission")
    batch_block = _type_block(bridge, "V3GacosSubmissionBatch")
    form_block = _type_block(bridge, "V3GacosFormFields")
    gacos = shape["gacos_submission"]
    for key in gacos["required_keys"]:
        assert _declares_property(submission_block, key)
    for key in gacos["batch_required_keys"]:
        assert _declares_property(batch_block, key)
    for key in gacos["form_field_keys"]:
        assert _declares_property(form_block, key)


def test_gacos_browser_submission_json_matches_shared_fixture() -> None:
    adapter = GacosProviderAdapter()
    query = ProviderQuery(
        processing_aoi=make_processing_aoi_from_bbox(109.5, 117.5, 20.0, 25.5),
        scenes=[
            Scene(acquisition_datetime=datetime(2024, 1, 1, 12, 0)),
            Scene(acquisition_datetime=datetime(2024, 1, 13, 12, 0)),
        ],
        output_root=Path("E:/InSAR/work"),
        region_id="r1",
        region_safe_name="demo_region",
        filters={"hour": 18, "minute": 30, "output_format": "geotiff"},
    )

    plan = adapter.plan(query).model_dump(mode="json")

    assert plan["manual_action_required"] is True
    assert plan["execution_mode"] == "browser_assisted_web_form"
    _assert_gacos_submission_matches_fixture(plan["submission"])
