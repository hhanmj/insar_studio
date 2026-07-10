"""Provider registry for the v3 Python adapter layer."""

from __future__ import annotations

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.v3.adapters import AsfProviderAdapter, DemProviderAdapter, GacosProviderAdapter
from insar_prep.v3.contracts import (
    DataSourceKind,
    ProviderAdapter,
    ProviderCapability,
    ProviderMetadata,
)


class ProviderRegistry:
    """Small in-process registry for v3 provider adapters."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, provider: ProviderAdapter) -> str:
        metadata = provider.metadata()
        self._providers[metadata.provider_id] = provider
        return metadata.provider_id

    def get(self, provider_id: str) -> ProviderAdapter:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise InputValidationError(
                f"unknown provider {provider_id!r}",
                code=ErrorCode.GUI003,
            )
        return provider

    def metadata(self) -> list[ProviderMetadata]:
        return sorted(
            (provider.metadata() for provider in self._providers.values()),
            key=lambda item: item.provider_id,
        )

    def by_source_kind(self, source_kind: DataSourceKind) -> list[ProviderMetadata]:
        return [item for item in self.metadata() if item.source_kind is source_kind]

    def with_capability(self, capability: ProviderCapability) -> list[ProviderMetadata]:
        return [item for item in self.metadata() if capability in item.capabilities]


def default_provider_registry() -> ProviderRegistry:
    """Return the default v3 registry backed by current Python providers."""
    registry = ProviderRegistry()
    registry.register(AsfProviderAdapter())
    registry.register(DemProviderAdapter())
    registry.register(GacosProviderAdapter())
    return registry

