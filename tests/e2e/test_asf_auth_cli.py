"""End-to-end tests for the ``auth`` CLI (Earthdata credential management).

No real keyring backend, no real getpass prompt, and no network: the credential
store functions and the password prompt are monkeypatched, so the tests prove the
CLI wiring (which action calls which store/clear) without persisting any secret.
"""

from __future__ import annotations

import getpass
import io

import pytest

import insar_prep.cli.commands as commands
from insar_prep.cli.main import main


class _Recorder:
    def __init__(self) -> None:
        self.token: str | None = None
        self.login: tuple[str, str] | None = None
        self.cleared = False
        self.status = "none"

    def store_token(self, token: str) -> None:
        self.token = token

    def store_login(self, username: str, password: str) -> None:
        self.login = (username, password)

    def clear_stored_credentials(self) -> bool:
        self.cleared = True
        return True

    def stored_credential_status(self) -> str:
        return self.status


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(commands, "store_token", rec.store_token)
    monkeypatch.setattr(commands, "store_login", rec.store_login)
    monkeypatch.setattr(commands, "clear_stored_credentials", rec.clear_stored_credentials)
    monkeypatch.setattr(commands, "stored_credential_status", rec.stored_credential_status)
    return rec


def test_auth_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["auth", "--help"])
    assert exc.value.code == 0


def test_auth_login_token_via_stdin(store: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("FAKE_TOKEN_STDIN_1\n"))
    code = main(["auth", "login", "--token-stdin"])
    assert code == 0
    assert store.token == "FAKE_TOKEN_STDIN_1"


def test_auth_login_token_interactive(store: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "FAKE_TOKEN_PROMPT_2")
    code = main(["auth", "login"])
    assert code == 0
    assert store.token == "FAKE_TOKEN_PROMPT_2"
    assert store.login is None


def test_auth_login_username_password(store: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "FAKE_PW_3")
    code = main(["auth", "login", "--username", "alice"])
    assert code == 0
    assert store.login == ("alice", "FAKE_PW_3")
    assert store.token is None


def test_auth_login_blank_token_falls_back_to_login(
    store: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = iter(["", "FAKE_PW_4"])  # token prompt blank, then password
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: next(prompts))
    monkeypatch.setattr("builtins.input", lambda *a, **k: "bob")
    code = main(["auth", "login"])
    assert code == 0
    assert store.login == ("bob", "FAKE_PW_4")


def test_auth_status(store: _Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    store.status = "token"
    code = main(["auth", "status"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Stored Earthdata credential: token" in out


def test_auth_logout(store: _Recorder, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["auth", "logout"])
    assert code == 0
    assert store.cleared is True
    assert "Cleared stored Earthdata credentials." in capsys.readouterr().out
