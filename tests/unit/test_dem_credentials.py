"""Tests for OpenTopography API-key resolution (real DEM download).

Only fake keys are used; nothing is read from the real environment or OS vault,
and no network is touched.
"""

from __future__ import annotations

import socket

import pytest

from insar_prep.core.exceptions import CredentialError
from insar_prep.providers.dem.credentials import (
    OPENTOPO_API_KEY_ENV,
    DemKeySource,
    ResolvedDemKey,
    clear_stored_api_key,
    resolve_dem_api_key,
    store_api_key,
    stored_api_key_status,
)

FAKE_KEY = "FAKE_OPENTOPO_KEY_ABCD1234"


class _FakeKeyring:
    """In-memory stand-in for the ``keyring`` module (no OS vault, no network)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._store:
            raise KeyError("no such entry")
        del self._store[(service, username)]


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in key resolution")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_env_key_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    resolved = resolve_dem_api_key(DemKeySource.ENV, environ={OPENTOPO_API_KEY_ENV: FAKE_KEY})
    assert resolved.source is DemKeySource.ENV
    assert resolved.api_key == FAKE_KEY


def test_env_key_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    with pytest.raises(CredentialError) as exc:
        resolve_dem_api_key(DemKeySource.ENV, environ={})
    assert exc.value.code.value == "DEM005"


def test_env_key_blank_raises() -> None:
    with pytest.raises(CredentialError):
        resolve_dem_api_key(DemKeySource.ENV, environ={OPENTOPO_API_KEY_ENV: "   "})


def test_resolved_repr_hides_key() -> None:
    resolved = ResolvedDemKey(source=DemKeySource.ENV, api_key=FAKE_KEY)
    text = repr(resolved)
    assert FAKE_KEY not in text
    assert "key=" in text


def test_keyring_store_and_resolve() -> None:
    kr = _FakeKeyring()
    store_api_key(FAKE_KEY, keyring_module=kr)
    assert stored_api_key_status(keyring_module=kr) == "set"
    resolved = resolve_dem_api_key(DemKeySource.KEYRING, keyring_module=kr)
    assert resolved.api_key == FAKE_KEY
    assert resolved.source is DemKeySource.KEYRING


def test_keyring_clear() -> None:
    kr = _FakeKeyring()
    store_api_key(FAKE_KEY, keyring_module=kr)
    assert clear_stored_api_key(keyring_module=kr) is True
    assert stored_api_key_status(keyring_module=kr) == "none"
    assert clear_stored_api_key(keyring_module=kr) is False


def test_keyring_empty_raises() -> None:
    with pytest.raises(CredentialError) as exc:
        resolve_dem_api_key(DemKeySource.KEYRING, keyring_module=_FakeKeyring())
    assert exc.value.code.value == "DEM005"


def test_store_empty_key_rejected() -> None:
    with pytest.raises(CredentialError):
        store_api_key("   ", keyring_module=_FakeKeyring())


def test_auto_prefers_keyring_then_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    kr = _FakeKeyring()
    store_api_key(FAKE_KEY, keyring_module=kr)
    resolved = resolve_dem_api_key(DemKeySource.AUTO, environ={}, keyring_module=kr)
    assert resolved.source is DemKeySource.KEYRING

    clear_stored_api_key(keyring_module=kr)
    resolved = resolve_dem_api_key(
        DemKeySource.AUTO, environ={OPENTOPO_API_KEY_ENV: FAKE_KEY}, keyring_module=kr
    )
    assert resolved.source is DemKeySource.ENV


def test_auto_none_configured_raises() -> None:
    with pytest.raises(CredentialError) as exc:
        resolve_dem_api_key(DemKeySource.AUTO, environ={}, keyring_module=_FakeKeyring())
    assert exc.value.code.value == "DEM005"
