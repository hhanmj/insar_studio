"""Desktop-facing v3 Provider orchestration.

This module is the narrow compatibility boundary between the pywebview API and
the staged v3 provider layer. It knows how to enrich a frontend request with the
current workspace/region context, but it does not know anything about UI
widgets, activity logging, or download execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insar_prep.v3 import ProviderProduct, ProviderQuery, default_provider_registry
from insar_prep.v3.contracts import ProviderAdapter, ProviderMetadata, ProviderPlan


class V3ProviderDesktopService:
    """Resolve v3 providers and adapt desktop context into ProviderQuery data."""

    def __init__(self, state: Any) -> None:
        self._state = state

    def provider_metadata(self) -> list[ProviderMetadata]:
        """Return metadata for all registered v3 providers."""
        return default_provider_registry().metadata()

    def search_provider(
        self,
        provider_id: str,
        query: dict | None = None,
    ) -> list[ProviderProduct]:
        """Search one provider using explicit query data plus desktop context."""
        provider, parsed = self._provider_and_query(provider_id, query)
        return provider.search(parsed)

    def plan_provider(
        self,
        provider_id: str,
        query: dict | None = None,
        products: list[dict] | None = None,
    ) -> ProviderPlan:
        """Build an offline provider plan without executing downloads."""
        provider, parsed = self._provider_and_query(provider_id, query)
        product_models = (
            [ProviderProduct.model_validate(item) for item in products]
            if products is not None
            else None
        )
        return provider.plan(parsed, product_models)

    def query_data(self, provider_id: str, query: dict | None = None) -> dict[str, Any]:
        """Build ProviderQuery input from JS data plus current desktop state."""
        clean_provider_id = str(provider_id or "").strip()
        raw = dict(query or {})
        canonical = {
            "provider_id",
            "source_kind",
            "product_kinds",
            "bbox",
            "processing_aoi",
            "scenes",
            "time_range",
            "max_results",
            "region_id",
            "region_safe_name",
            "output_root",
            "output_dir",
            "filters",
        }
        filters = raw.get("filters")
        filter_data = dict(filters) if isinstance(filters, dict) else {}
        for key, value in raw.items():
            if key not in canonical:
                filter_data[key] = value

        data: dict[str, Any] = {"provider_id": clean_provider_id, "filters": filter_data}
        for key in (
            "source_kind",
            "product_kinds",
            "bbox",
            "processing_aoi",
            "scenes",
            "time_range",
            "max_results",
            "region_id",
            "region_safe_name",
        ):
            if key in raw:
                data[key] = raw[key]

        output_root = raw.get("output_root") or raw.get("output_dir") or self._default_output()
        if output_root:
            data["output_root"] = Path(str(output_root))

        region = self._state.current_region()
        if region is not None:
            data.setdefault("region_id", region.region_id)
            data.setdefault("region_safe_name", region.region_safe_name)
            if "processing_aoi" not in data and "bbox" not in data and region.aoi is not None:
                data["processing_aoi"] = region.aoi
            if "scenes" not in data and region.scenes:
                data["scenes"] = region.scenes
        return data

    def _provider_and_query(
        self,
        provider_id: str,
        query: dict | None = None,
    ) -> tuple[ProviderAdapter, ProviderQuery]:
        clean_provider_id = str(provider_id or "").strip()
        provider = default_provider_registry().get(clean_provider_id)
        return provider, ProviderQuery.model_validate(self.query_data(clean_provider_id, query))

    def _default_output(self) -> str:
        region = self._state.current_region()
        if region is not None:
            return str(region.region_root)
        project = self._state.current_project()
        if project is not None:
            return str(project.project_root)
        workspace = self._state.workspace
        return str(workspace.workspace_root) if workspace is not None else ""
