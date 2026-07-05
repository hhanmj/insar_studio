"""Tests for GACOS email resolution (real GACOS request/download).

Only fake emails are used; nothing is read from the real environment or OS vault,
and no network is touched.
"""

from __future__ import annotations

import socket

import pytest

from insar_prep.core.exceptions import CredentialError
from insar_prep.providers.gacos.credentials import (
    GACOS_EMAIL_ENV,
    GacosEmailSource,
    clear_stored_gacos_email,
    is_valid_email,
    mask_email,
    resolve_gacos_email,
    store_gacos_email,
    stored_gacos_email_status,
)

FAKE_EMAIL = "tester@example.com"


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
        raise AssertionError("network access is forbidden in email resolution")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_mask_email_keeps_first_char_and_domain() -> None:
    assert mask_email("tester@example.com") == "t***@example.com"
    assert mask_email("a@b.co") == "a***@b.co"
    assert mask_email("not-an-email") == "***"


def test_is_valid_email() -> None:
    assert is_valid_email("tester@example.com")
    assert not is_valid_email("nope")
    assert not is_valid_email("a@b")


def test_env_email_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    resolved = resolve_gacos_email(GacosEmailSource.ENV, environ={GACOS_EMAIL_ENV: FAKE_EMAIL})
    assert resolved.source is GacosEmailSource.ENV
    assert resolved.email == FAKE_EMAIL


def test_env_email_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    with pytest.raises(CredentialError):
        resolve_gacos_email(GacosEmailSource.ENV, environ={})


def test_keyring_store_status_resolve_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    kr = _FakeKeyring()
    store_gacos_email(FAKE_EMAIL, keyring_module=kr)
    assert stored_gacos_email_status(keyring_module=kr) == "t***@example.com"
    resolved = resolve_gacos_email(GacosEmailSource.KEYRING, keyring_module=kr)
    assert resolved.email == FAKE_EMAIL
    assert clear_stored_gacos_email(keyring_module=kr) is True
    assert stored_gacos_email_status(keyring_module=kr) == "none"


def test_store_rejects_bad_email(monkeypatch: pytest.MonkeyPatch) -> None:
    kr = _FakeKeyring()
    with pytest.raises(CredentialError):
        store_gacos_email("not-an-email", keyring_module=kr)


def test_resolved_repr_masks_email() -> None:
    resolved = resolve_gacos_email(GacosEmailSource.ENV, environ={GACOS_EMAIL_ENV: FAKE_EMAIL})
    assert FAKE_EMAIL not in repr(resolved)
    assert "t***@example.com" in repr(resolved)


def test_auto_prefers_keyring_then_env() -> None:
    kr = _FakeKeyring()
    # Empty keyring -> falls through to env.
    resolved = resolve_gacos_email(
        GacosEmailSource.AUTO, environ={GACOS_EMAIL_ENV: FAKE_EMAIL}, keyring_module=kr
    )
    assert resolved.source is GacosEmailSource.ENV
    kr.set_password("insar-prep:gacos", "email", "kr@example.com")
    resolved = resolve_gacos_email(
        GacosEmailSource.AUTO, environ={GACOS_EMAIL_ENV: FAKE_EMAIL}, keyring_module=kr
    )
    assert resolved.source is GacosEmailSource.KEYRING
    assert resolved.email == "kr@example.com"
