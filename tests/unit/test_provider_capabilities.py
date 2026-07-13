from __future__ import annotations

from insar_prep.providers import all_provider_capabilities, provider_capability


def test_asf_capability_supports_burst_and_fallback() -> None:
    capability = provider_capability("ASF")
    assert capability.supports_burst_direct is True
    assert capability.supports_scene_fallback is True


def test_unknown_provider_capability_defaults_to_safe_flags() -> None:
    capability = provider_capability("custom")
    assert capability.provider == "CUSTOM"
    assert capability.supports_burst_direct is False
    assert capability.supports_scene_fallback is True


def test_all_provider_capabilities_returns_copy() -> None:
    capabilities = all_provider_capabilities()
    assert "ASF" in capabilities
