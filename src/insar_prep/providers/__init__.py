"""External data provider adapters (ASF, orbit, DEM, atmosphere, ...).

Task 006 implements local ASF cart/scene parsing only. Network access and
``asf_search`` integration are deferred to later tasks.
"""

from __future__ import annotations

from insar_prep.providers.capabilities import (
    ProviderCapability,
    all_provider_capabilities,
    provider_capability,
)

__all__ = [
    "ProviderCapability",
    "all_provider_capabilities",
    "provider_capability",
]
