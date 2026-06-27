"""Tests for Earthdata credential resolution (real ASF download).

Only fake credentials are used; nothing is read from the real environment or a
real ~/.netrc, and no network is touched.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from insar_prep.core.exceptions import CredentialError
from insar_prep.providers.asf.credentials import (
    EARTHDATA_TOKEN_ENV,
    CredentialSource,
    ResolvedCredential,
    clear_stored_credentials,
    resolve_credentials,
    store_login,
    store_token,
    stored_credential_status,
)

FAKE_TOKEN = "FAKE_EARTHDATA_TOKEN_ABCD1234"
FAKE_USER = "fake_user"
FAKE_PW = "FAKE_PASSWORD_5678"


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
        raise AssertionError("network access is forbidden in credential resolution")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def _write_netrc(path: Path, *, host: str = "urs.earthdata.nasa.gov") -> Path:
    path.write_text(
        f"machine {host} login fakeuser password FAKE_NETRC_PASSWORD\n",
        encoding="utf-8",
    )
    path.chmod(0o600)  # netrc on POSIX rejects world-readable files with a password
    return path


def test_env_token_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    resolved = resolve_credentials(
        CredentialSource.ENV_TOKEN, environ={EARTHDATA_TOKEN_ENV: FAKE_TOKEN}
    )
    assert resolved.source is CredentialSource.ENV_TOKEN
    assert resolved.token == FAKE_TOKEN
    assert resolved.use_netrc is False


def test_env_token_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    with pytest.raises(CredentialError) as exc:
        resolve_credentials(CredentialSource.ENV_TOKEN, environ={})
    assert exc.value.code.value == "DL004"


def test_env_token_blank_raises() -> None:
    with pytest.raises(CredentialError):
        resolve_credentials(CredentialSource.ENV_TOKEN, environ={EARTHDATA_TOKEN_ENV: "   "})


def test_netrc_with_entry_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    netrc_path = _write_netrc(tmp_path / ".netrc")
    resolved = resolve_credentials(CredentialSource.NETRC, netrc_path=netrc_path)
    assert resolved.source is CredentialSource.NETRC
    assert resolved.use_netrc is True
    assert resolved.token is None


def test_netrc_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(CredentialError) as exc:
        resolve_credentials(CredentialSource.NETRC, netrc_path=tmp_path / "nope.netrc")
    assert exc.value.code.value == "DL004"


def test_netrc_wrong_host_raises(tmp_path: Path) -> None:
    netrc_path = _write_netrc(tmp_path / ".netrc", host="example.com")
    with pytest.raises(CredentialError):
        resolve_credentials(CredentialSource.NETRC, netrc_path=netrc_path)


def test_resolved_repr_hides_token() -> None:
    resolved = ResolvedCredential(source=CredentialSource.ENV_TOKEN, token=FAKE_TOKEN)
    text = repr(resolved)
    assert FAKE_TOKEN not in text
    assert "kind=token" in text


def test_resolved_repr_hides_login() -> None:
    resolved = ResolvedCredential(
        source=CredentialSource.KEYRING, username=FAKE_USER, password=FAKE_PW
    )
    text = repr(resolved)
    assert FAKE_PW not in text
    assert "kind=login" in text


def test_keyring_store_token_and_resolve() -> None:
    kr = _FakeKeyring()
    store_token(FAKE_TOKEN, keyring_module=kr)
    assert stored_credential_status(keyring_module=kr) == "token"
    resolved = resolve_credentials(CredentialSource.KEYRING, keyring_module=kr)
    assert resolved.token == FAKE_TOKEN
    assert resolved.source is CredentialSource.KEYRING


def test_keyring_store_login_and_resolve() -> None:
    kr = _FakeKeyring()
    store_login(FAKE_USER, FAKE_PW, keyring_module=kr)
    status = stored_credential_status(keyring_module=kr)
    assert status.startswith("login:")
    assert FAKE_USER not in status  # the full username is masked
    resolved = resolve_credentials(CredentialSource.KEYRING, keyring_module=kr)
    assert resolved.username == FAKE_USER
    assert resolved.password == FAKE_PW
    assert resolved.token is None


def test_keyring_token_and_login_are_mutually_exclusive() -> None:
    kr = _FakeKeyring()
    store_login(FAKE_USER, FAKE_PW, keyring_module=kr)
    store_token(FAKE_TOKEN, keyring_module=kr)
    assert stored_credential_status(keyring_module=kr) == "token"
    store_login(FAKE_USER, FAKE_PW, keyring_module=kr)
    status = stored_credential_status(keyring_module=kr)
    assert status.startswith("login:")
    assert FAKE_USER not in status  # the full username is masked


def test_keyring_clear() -> None:
    kr = _FakeKeyring()
    store_token(FAKE_TOKEN, keyring_module=kr)
    assert clear_stored_credentials(keyring_module=kr) is True
    assert stored_credential_status(keyring_module=kr) == "none"
    assert clear_stored_credentials(keyring_module=kr) is False


def test_keyring_empty_raises() -> None:
    with pytest.raises(CredentialError) as exc:
        resolve_credentials(CredentialSource.KEYRING, keyring_module=_FakeKeyring())
    assert exc.value.code.value == "DL004"


def test_store_empty_token_rejected() -> None:
    with pytest.raises(CredentialError):
        store_token("   ", keyring_module=_FakeKeyring())


def test_auto_prefers_keyring_then_env_then_netrc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    kr = _FakeKeyring()
    # 1) keyring wins when present.
    store_token(FAKE_TOKEN, keyring_module=kr)
    resolved = resolve_credentials(CredentialSource.AUTO, environ={}, keyring_module=kr)
    assert resolved.source is CredentialSource.KEYRING

    # 2) empty keyring -> env token.
    clear_stored_credentials(keyring_module=kr)
    resolved = resolve_credentials(
        CredentialSource.AUTO, environ={EARTHDATA_TOKEN_ENV: FAKE_TOKEN}, keyring_module=kr
    )
    assert resolved.source is CredentialSource.ENV_TOKEN

    # 3) empty keyring + no env -> netrc.
    netrc_path = _write_netrc(tmp_path / ".netrc")
    resolved = resolve_credentials(
        CredentialSource.AUTO, environ={}, netrc_path=netrc_path, keyring_module=kr
    )
    assert resolved.source is CredentialSource.NETRC


def test_auto_none_configured_raises(tmp_path: Path) -> None:
    with pytest.raises(CredentialError) as exc:
        resolve_credentials(
            CredentialSource.AUTO,
            environ={},
            netrc_path=tmp_path / "nope.netrc",
            keyring_module=_FakeKeyring(),
        )
    assert exc.value.code.value == "DL004"
