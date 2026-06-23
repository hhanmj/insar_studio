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
    resolve_credentials,
)

FAKE_TOKEN = "FAKE_EARTHDATA_TOKEN_ABCD1234"


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
