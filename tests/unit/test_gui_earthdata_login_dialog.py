"""Tests for the GUI Earthdata Login dialog.

Requires PySide6 (the ``gui`` extra); skipped otherwise. Uses the offscreen Qt
platform. The credential-store functions are monkeypatched, so the test proves the
dialog wiring (token vs username/password vs clear) without an OS keyring, secrets,
or network.
"""

from __future__ import annotations

import importlib.util

import pytest

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")

_DIALOG_MODULE = "insar_prep.gui.dialogs.earthdata_login_dialog"


@pytest.fixture(autouse=True)
def _offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application

    create_application([])


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
    monkeypatch.setattr(f"{_DIALOG_MODULE}.store_token", rec.store_token)
    monkeypatch.setattr(f"{_DIALOG_MODULE}.store_login", rec.store_login)
    monkeypatch.setattr(f"{_DIALOG_MODULE}.clear_stored_credentials", rec.clear_stored_credentials)
    monkeypatch.setattr(f"{_DIALOG_MODULE}.stored_credential_status", rec.stored_credential_status)
    return rec


def _dialog():
    from insar_prep.gui.dialogs.earthdata_login_dialog import EarthdataLoginDialog

    return EarthdataLoginDialog()


def test_dialog_shows_initial_status(store: _Recorder) -> None:
    store.status = "token"
    dialog = _dialog()
    assert "token" in dialog.status_text()


def test_save_token(store: _Recorder) -> None:
    dialog = _dialog()
    dialog._token_edit.setText("FAKE_GUI_TOKEN_1")
    assert dialog.save_credentials() is True
    assert store.token == "FAKE_GUI_TOKEN_1"
    # Secret field is cleared after a successful save.
    assert dialog._token_edit.text() == ""


def test_save_username_password(store: _Recorder) -> None:
    dialog = _dialog()
    dialog._username_edit.setText("carol")
    dialog._password_edit.setText("FAKE_GUI_PW_2")
    assert dialog.save_credentials() is True
    assert store.login == ("carol", "FAKE_GUI_PW_2")


def test_save_nothing_is_rejected(store: _Recorder) -> None:
    dialog = _dialog()
    assert dialog.save_credentials() is False
    assert store.token is None
    assert store.login is None
    assert "token" in dialog.status_text().lower()


def test_clear(store: _Recorder) -> None:
    dialog = _dialog()
    assert dialog.clear_credentials() is True
    assert store.cleared is True
