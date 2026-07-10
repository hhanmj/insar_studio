"""Adapters from current Python providers to the v3 provider contract."""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

from insar_prep.core.enums import DemDataset, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.models import Aoi, BBox, Scene
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.providers.asf.download_plan import AsfPlanStatus, build_asf_download_plan
from insar_prep.providers.asf.scene_parser import deduplicate_scenes, parse_scene_name
from insar_prep.providers.dem.planner import create_dem_request_plan, validate_dem_request_plan
from insar_prep.providers.gacos.downloader import GACOS_BASE_URL, GACOS_SUBMIT_ENDPOINT
from insar_prep.providers.gacos.planner import (
    create_gacos_request_plan,
    extract_gacos_dates_from_scenes,
    validate_gacos_request_plan,
)
from insar_prep.v3.contracts import (
    AssetRole,
    DataSourceKind,
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

_GACOS_FORM_TYPE_BY_OUTPUT_FORMAT = {
    "geotiff": "2",
    "binary": "1",
}


def _require_output_root(query: ProviderQuery) -> Path:
    if query.output_root is None:
        raise InputValidationError("provider planning requires output_root", code=ErrorCode.GUI003)
    return Path(query.output_root)


def _processing_aoi_from_query(query: ProviderQuery) -> Aoi:
    if query.processing_aoi is not None:
        return query.processing_aoi
    if query.bbox is not None:
        bbox = query.bbox
        return make_processing_aoi_from_bbox(bbox.west, bbox.east, bbox.south, bbox.north)
    raise InputValidationError(
        "provider planning requires processing_aoi or bbox",
        code=ErrorCode.AOI001,
    )


def _bbox_from_query(query: ProviderQuery) -> BBox | None:
    if query.bbox is not None:
        return query.bbox
    if query.processing_aoi is not None:
        return query.processing_aoi.bbox
    return None


def _validate_bbox(query: ProviderQuery) -> None:
    bbox = _bbox_from_query(query)
    if bbox is None:
        return
    if not (-180 <= bbox.west < bbox.east <= 180 and -90 <= bbox.south < bbox.north <= 90):
        raise InputValidationError(
            "query bbox is outside valid lon/lat bounds",
            code=ErrorCode.AOI001,
        )


def _filter_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _scene_product_kind(scene: Scene) -> ProductKind:
    product = str(getattr(scene.product_type, "value", scene.product_type)).upper()
    if product == "GRD":
        return ProductKind.SAR_GRD
    return ProductKind.SAR_SLC


def _scene_to_product(scene: Scene, provider_id: str) -> ProviderProduct:
    file_name = f"{scene.scene_id}.zip"
    return ProviderProduct(
        provider_id=provider_id,
        product_id=scene.scene_id,
        display_name=scene.scene_id,
        source_kind=DataSourceKind.SENTINEL1,
        product_kind=_scene_product_kind(scene),
        acquisition_datetime=scene.acquisition_datetime,
        footprint_bbox=scene.footprint_bbox,
        assets=[
            ProviderAsset(
                role=AssetRole.PRIMARY,
                url=scene.url,
                file_name=file_name,
                media_type="application/zip",
                size_bytes=scene.file_size_remote,
            )
        ],
        properties={
            "platform": str(getattr(scene.platform, "value", scene.platform)),
            "product_type": str(getattr(scene.product_type, "value", scene.product_type)),
            "beam_mode": str(getattr(scene.beam_mode, "value", scene.beam_mode)),
            "polarization": str(getattr(scene.polarization, "value", scene.polarization)),
            "orbit_direction": str(getattr(scene.orbit_direction, "value", scene.orbit_direction)),
            "relative_orbit": scene.relative_orbit,
            "absolute_orbit": scene.absolute_orbit,
        },
        payload={"scene": scene.model_dump(mode="json")},
    )


def _scene_from_product(product: ProviderProduct) -> Scene:
    raw = product.payload.get("scene")
    if isinstance(raw, dict):
        return Scene.model_validate(raw)
    source = next((asset.url for asset in product.assets if asset.url), product.product_id)
    return parse_scene_name(source)


def _dataset_from_query_or_product(
    query: ProviderQuery,
    products: list[ProviderProduct] | None,
) -> str:
    if query.filters.get("dataset"):
        return str(query.filters["dataset"])
    if products:
        dataset = products[0].properties.get("dataset")
        if dataset:
            return str(dataset)
    return DemDataset.COP30.value


def _vertical_datum(value: object, fallback: VerticalDatum) -> VerticalDatum:
    if isinstance(value, VerticalDatum):
        return value
    if value is None or str(value).strip() == "":
        return fallback
    return VerticalDatum(str(value).strip())


def _gacos_int_filter(
    query: ProviderQuery,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = query.filters.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(
            f"GACOS {key} must be an integer",
            code=ErrorCode.GAC003,
        ) from exc
    if not minimum <= value <= maximum:
        raise InputValidationError(
            f"GACOS {key} must be {minimum}-{maximum}",
            code=ErrorCode.GAC003,
        )
    return value


def _gacos_output_format(query: ProviderQuery) -> str:
    value = str(query.filters.get("output_format", "geotiff")).strip().lower()
    if value not in _GACOS_FORM_TYPE_BY_OUTPUT_FORMAT:
        raise InputValidationError(
            "GACOS output_format must be 'geotiff' or 'binary'",
            code=ErrorCode.GAC003,
        )
    return value


def _gacos_submission_payload(batches_payload: list[dict], *, output_format: str) -> dict:
    return {
        "kind": "web_form_submission",
        "provider": "gacos",
        "execution_mode": ProviderExecutionMode.BROWSER_ASSISTED_WEB_FORM.value,
        "portal_url": GACOS_BASE_URL,
        "submit_endpoint": GACOS_SUBMIT_ENDPOINT,
        "method": "POST",
        "content_type": "application/x-www-form-urlencoded",
        "output_format": output_format,
        "requires_user_confirmation": True,
        "requires_email_delivery": True,
        "email_field": "email",
        "result_delivery": "email_link",
        "download_link_handling": "paste_email_link_then_import",
        "batches": batches_payload,
    }


class AsfProviderAdapter:
    """v3 adapter for current ASF Sentinel-1 parsing and download planning."""

    provider_id = "asf.sentinel1"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            display_name="ASF Sentinel-1",
            source_kind=DataSourceKind.SENTINEL1,
            capabilities=[
                ProviderCapability.SEARCH,
                ProviderCapability.PLAN,
                ProviderCapability.DOWNLOAD,
                ProviderCapability.CREDENTIALS,
                ProviderCapability.LOCAL_FILES,
            ],
        )

    def search(self, query: ProviderQuery) -> list[ProviderProduct]:
        _validate_bbox(query)
        scenes = list(query.scenes)
        if not scenes:
            sources = []
            sources.extend(_filter_text_list(query.filters.get("scene_sources")))
            sources.extend(_filter_text_list(query.filters.get("scene_names")))
            sources.extend(_filter_text_list(query.filters.get("scene_text")))
            scenes = [parse_scene_name(source) for source in sources]
        unique, _duplicates = deduplicate_scenes(scenes)
        if query.max_results is not None:
            unique = unique[: query.max_results]
        return [_scene_to_product(scene, self.provider_id) for scene in unique]

    def plan(
        self,
        query: ProviderQuery,
        products: list[ProviderProduct] | None = None,
    ) -> ProviderPlan:
        output_root = _require_output_root(query)
        product_list = products if products is not None else self.search(query)
        scenes = [_scene_from_product(product) for product in product_list]
        plan = build_asf_download_plan(
            scenes=scenes,
            output_dir=output_root,
            region_safe_name=query.region_safe_name,
        )
        items = [
            ProviderPlanItem(
                product_id=item.scene_id,
                target_path=Path(item.planned_path),
                role=AssetRole.PRIMARY,
                status=item.status.value.lower(),
                properties={
                    "url_status": item.url_status,
                    "expected_filename": item.expected_filename,
                    "credential_required": item.credential_required,
                },
            )
            for item in plan.items
            if item.status in {AsfPlanStatus.PLANNED, AsfPlanStatus.MISSING_URL}
        ]
        return ProviderPlan(
            provider_id=self.provider_id,
            source_kind=DataSourceKind.SENTINEL1,
            output_root=output_root,
            items=items,
            requires_credentials=True,
            manual_action_required=False,
            legacy_plan=plan.model_dump(mode="json"),
        )


class DemProviderAdapter:
    """v3 adapter for current DEM request planning."""

    provider_id = "opentopography.dem"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            display_name="OpenTopography DEM",
            source_kind=DataSourceKind.DEM,
            capabilities=[
                ProviderCapability.SEARCH,
                ProviderCapability.PLAN,
                ProviderCapability.DOWNLOAD,
                ProviderCapability.CREDENTIALS,
            ],
        )

    def search(self, query: ProviderQuery) -> list[ProviderProduct]:
        _validate_bbox(query)
        bbox = _bbox_from_query(query)
        dataset = _dataset_from_query_or_product(query, None)
        return [
            ProviderProduct(
                provider_id=self.provider_id,
                product_id=f"DEM:{dataset}",
                display_name=f"{dataset} DEM",
                source_kind=DataSourceKind.DEM,
                product_kind=ProductKind.DEM_RASTER,
                footprint_bbox=bbox,
                assets=[
                    ProviderAsset(
                        role=AssetRole.PRIMARY,
                        file_name=f"{dataset}.tif",
                        media_type="image/tiff",
                    )
                ],
                properties={"dataset": dataset, "provider": "OPENTOPOGRAPHY"},
            )
        ]

    def plan(
        self,
        query: ProviderQuery,
        products: list[ProviderProduct] | None = None,
    ) -> ProviderPlan:
        output_root = _require_output_root(query)
        dataset = _dataset_from_query_or_product(query, products)
        processing_aoi = _processing_aoi_from_query(query)
        buffer_degrees = float(query.filters.get("buffer_degrees", 0.05))
        source_vertical_datum = _vertical_datum(
            query.filters.get("source_vertical_datum"),
            VerticalDatum.EGM2008,
        )
        target_vertical_datum = _vertical_datum(
            query.filters.get("target_vertical_datum"),
            VerticalDatum.WGS84_ELLIPSOID,
        )
        plan = create_dem_request_plan(
            region_id=query.region_id,
            region_safe_name=query.region_safe_name,
            processing_aoi=processing_aoi,
            output_root=output_root,
            dataset=dataset,
            buffer_degrees=buffer_degrees,
            source_vertical_datum=source_vertical_datum,
            target_vertical_datum=target_vertical_datum,
        )
        report = validate_dem_request_plan(plan)
        items = [
            ProviderPlanItem(
                product_id=f"DEM:{dataset}:raw",
                target_path=plan.raw_dem_path,
                role=AssetRole.PRIMARY,
                properties={"stage": "raw_dem", "dataset": dataset},
            ),
            ProviderPlanItem(
                product_id=f"DEM:{dataset}:ellipsoid",
                target_path=plan.ellipsoid_dem_path,
                role=AssetRole.DERIVED,
                properties={"stage": "ellipsoid_dem", "dataset": dataset},
            ),
            ProviderPlanItem(
                product_id=f"DEM:{dataset}:sarscape",
                target_path=plan.sarscape_ready_dem_path,
                role=AssetRole.DERIVED,
                properties={"stage": "sarscape_ready_dem", "dataset": dataset},
            ),
        ]
        return ProviderPlan(
            provider_id=self.provider_id,
            source_kind=DataSourceKind.DEM,
            output_root=output_root,
            items=items,
            requires_credentials=True,
            manual_action_required=False,
            legacy_plan=plan.model_dump(mode="json"),
            legacy_report=report.model_dump(mode="json"),
        )


class GacosProviderAdapter:
    """v3 adapter for current GACOS request planning."""

    provider_id = "gacos.atmosphere"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            display_name="GACOS Atmospheric Delay",
            source_kind=DataSourceKind.GACOS,
            capabilities=[
                ProviderCapability.SEARCH,
                ProviderCapability.PLAN,
                ProviderCapability.CREDENTIALS,
                ProviderCapability.ATMOSPHERIC_CORRECTION,
            ],
        )

    def search(self, query: ProviderQuery) -> list[ProviderProduct]:
        _validate_bbox(query)
        bbox = _bbox_from_query(query)
        products: list[ProviderProduct] = []
        for day in extract_gacos_dates_from_scenes(query.scenes):
            exact_time = time.min
            for scene in query.scenes:
                dt = scene.acquisition_datetime
                if dt is not None and dt.date() == day:
                    exact_time = dt.time()
                    break

            products.append(
                ProviderProduct(
                    provider_id=self.provider_id,
                    product_id=f"GACOS:{day:%Y%m%d}",
                    display_name=f"GACOS ZTD {day:%Y-%m-%d}",
                    source_kind=DataSourceKind.GACOS,
                    product_kind=ProductKind.ATMOSPHERE_DELAY,
                    acquisition_datetime=datetime.combine(day, exact_time),
                    footprint_bbox=bbox,
                    assets=[
                        ProviderAsset(
                            role=AssetRole.PRIMARY,
                            file_name=f"{day:%Y%m%d}.ztd",
                            media_type="application/octet-stream",
                        )
                    ],
                    properties={"date": day.isoformat()},
                )
            )
        if query.max_results is not None:
            products = products[: query.max_results]
        return products

    def plan(
        self,
        query: ProviderQuery,
        products: list[ProviderProduct] | None = None,
    ) -> ProviderPlan:
        output_root = _require_output_root(query)
        processing_aoi = _processing_aoi_from_query(query)
        scenes = list(query.scenes)
        if not scenes:
            dates_list = []
            if "dates" in query.filters:
                dates_val = query.filters["dates"]
                if isinstance(dates_val, list):
                    dates_list.extend(dates_val)
            if "date_text" in query.filters:
                dt_val = query.filters["date_text"]
                if isinstance(dt_val, str):
                    import re
                    dates_list.extend(re.findall(r"\b\d{8}\b", dt_val))

            for d in dates_list:
                if len(d) == 8:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(d, "%Y%m%d")
                        scenes.append(Scene(acquisition_datetime=dt))
                    except (ValueError, TypeError):
                        pass

        if not scenes and products:
            scenes = [
                Scene(acquisition_datetime=product.acquisition_datetime)
                for product in products
                if product.acquisition_datetime is not None
            ]

        if not scenes:
            raise InputValidationError(
                "GACOS planning requires at least one scene",
                code=ErrorCode.GAC001,
            )

        # 1. Determine time grouping
        has_manual_time = "hour" in query.filters and "minute" in query.filters
        if has_manual_time:
            hour = _gacos_int_filter(query, "hour", default=0, minimum=0, maximum=23)
            minute = _gacos_int_filter(query, "minute", default=0, minimum=0, maximum=59)
            time_groups = {(hour, minute): scenes}
        else:
            time_groups = {}
            for scene in scenes:
                if scene.acquisition_datetime is not None:
                    h = scene.acquisition_datetime.hour
                    m = scene.acquisition_datetime.minute
                    time_groups.setdefault((h, m), []).append(scene)

            if not time_groups:
                raise InputValidationError(
                    "GACOS ZTD requires UTC hour and minute when no scenes are available "
                    "or scene acquisition datetimes are missing",
                    code=ErrorCode.GAC003,
                )

        output_format = _gacos_output_format(query)
        buffer_degrees = float(query.filters.get("buffer_degrees", 0.05))
        max_dates_per_batch = int(query.filters.get("max_dates_per_batch", 20))

        # 2. Plan for each time group
        sorted_keys = sorted(time_groups.keys())
        sub_plans = []
        for h, m in sorted_keys:
            scenes_in_group = time_groups[(h, m)]
            sub_plan = create_gacos_request_plan(
                region_id=query.region_id,
                region_safe_name=query.region_safe_name,
                processing_aoi=processing_aoi,
                scenes=scenes_in_group,
                output_root=output_root,
                buffer_degrees=buffer_degrees,
                max_dates_per_batch=max_dates_per_batch,
            )
            sub_plans.append((sub_plan, h, m))

        total_batch_count = sum(len(sp.batches) for sp, _, _ in sub_plans)
        batches_payload = []
        global_batch_index = 1

        for sub_plan, h, m in sub_plans:
            for batch in sub_plan.batches:
                date_text = "\n".join(day.strftime("%Y%m%d") for day in batch.dates)
                form_fields = {
                    "N": f"{batch.bbox.north}",
                    "S": f"{batch.bbox.south}",
                    "W": f"{batch.bbox.west}",
                    "E": f"{batch.bbox.east}",
                    "H": f"{h}",
                    "M": f"{m}",
                    "date": date_text,
                    "type": _GACOS_FORM_TYPE_BY_OUTPUT_FORMAT[output_format],
                    "seq": "OSM Map",
                }
                batches_payload.append({
                    "batch_id": batch.batch_id,
                    "batch_index": global_batch_index,
                    "batch_count": total_batch_count,
                    "date_count": batch.date_count,
                    "dates": [day.isoformat() for day in batch.dates],
                    "date_text": date_text,
                    "bbox": batch.bbox.model_dump(mode="json"),
                    "method": "POST",
                    "endpoint": GACOS_SUBMIT_ENDPOINT,
                    "content_type": "application/x-www-form-urlencoded",
                    "form_fields": form_fields,
                    "required_sensitive_fields": ["email"],
                })
                global_batch_index += 1

        # Combine unique dates and output items
        unique_dates = []
        for sub_plan, _, _ in sub_plans:
            for day in sub_plan.unique_dates:
                if day not in unique_dates:
                    unique_dates.append(day)
        unique_dates.sort()

        # Build merged GacosRequestPlan and GacosPlanningReport for legacy and warning checks
        from insar_prep.providers.gacos.types import GacosRequestPlan
        output_directory = sub_plans[0][0].output_directory
        merged_plan = GacosRequestPlan(
            region_id=query.region_id,
            region_safe_name=query.region_safe_name,
            processing_bbox=processing_aoi.bbox,
            request_bbox=sub_plans[0][0].request_bbox,
            buffer_degrees=buffer_degrees,
            unique_dates=unique_dates,
            batches=[b for sp, _, _ in sub_plans for b in sp.batches],
            manual_submission_required=True,
            output_directory=output_directory,
            expected_file_patterns=list(sub_plans[0][0].expected_file_patterns),
            max_dates_per_batch=max_dates_per_batch,
            scene_count=len(scenes),
            scene_missing_date_count=sum(sp.scene_missing_date_count for sp, _, _ in sub_plans),
        )
        report = validate_gacos_request_plan(merged_plan)

        items = [
            ProviderPlanItem(
                product_id=f"GACOS:{day:%Y%m%d}",
                target_path=output_directory / f"{day:%Y%m%d}.ztd",
                role=AssetRole.PRIMARY,
                properties={
                    "date": day.isoformat(),
                    "paired_rsc": f"{day:%Y%m%d}.ztd.rsc",
                    "submission_source": "gacos_web_form",
                },
            )
            for day in unique_dates
        ]

        return ProviderPlan(
            provider_id=self.provider_id,
            source_kind=DataSourceKind.GACOS,
            output_root=output_root,
            items=items,
            requires_credentials=True,
            manual_action_required=True,
            execution_mode=ProviderExecutionMode.BROWSER_ASSISTED_WEB_FORM,
            submission=_gacos_submission_payload(
                batches_payload,
                output_format=output_format,
            ),
            legacy_plan=merged_plan.model_dump(mode="json"),
            legacy_report=report.model_dump(mode="json"),
        )
