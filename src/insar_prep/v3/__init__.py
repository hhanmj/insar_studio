"""v3 service contracts and provider adapters.

This package is a staged migration layer. It exposes a unified provider
contract while the existing Python desktop API and UI bridge remain stable.
"""

from insar_prep.v3.adapters import AsfProviderAdapter, DemProviderAdapter, GacosProviderAdapter
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
    TimeRange,
)
from insar_prep.v3.registry import ProviderRegistry, default_provider_registry

__all__ = [
    "AsfProviderAdapter",
    "AssetRole",
    "DataSourceKind",
    "DemProviderAdapter",
    "GacosProviderAdapter",
    "ProductKind",
    "ProviderAsset",
    "ProviderCapability",
    "ProviderExecutionMode",
    "ProviderMetadata",
    "ProviderPlan",
    "ProviderPlanItem",
    "ProviderProduct",
    "ProviderQuery",
    "ProviderRegistry",
    "TimeRange",
    "default_provider_registry",
]
