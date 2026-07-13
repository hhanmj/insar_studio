"""Provider capability registry used by sidecar planning paths."""

from __future__ import annotations

from insar_prep.core.models import InsarBaseModel


class ProviderCapability(InsarBaseModel):
    """Declared capabilities for one provider implementation."""

    provider: str
    supports_burst_direct: bool = False
    supports_scene_fallback: bool = True


_CAPABILITIES: dict[str, ProviderCapability] = {
    "ASF": ProviderCapability(
        provider="ASF",
        supports_burst_direct=True,
        supports_scene_fallback=True,
    ),
    "OPENTOPOGRAPHY": ProviderCapability(
        provider="OPENTOPOGRAPHY",
        supports_burst_direct=False,
        supports_scene_fallback=False,
    ),
}


def provider_capability(provider: str) -> ProviderCapability:
    """Return provider capability flags, defaulting to safe fallback settings."""
    return _CAPABILITIES.get(
        provider.upper(),
        ProviderCapability(
            provider=provider.upper(),
            supports_burst_direct=False,
            supports_scene_fallback=True,
        ),
    )


def all_provider_capabilities() -> dict[str, ProviderCapability]:
    """Return a copy of all registered provider capabilities."""
    return dict(_CAPABILITIES)
