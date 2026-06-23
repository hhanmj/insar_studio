"""Earthdata Login dialog: configure NASA EDL credentials from the GUI.

A friendly front-end for the same OS-keyring storage used by ``insar-prep auth``:
the user pastes a personal bearer token (recommended; a button opens the Earthdata
token page in the browser) or enters a username/password. Secrets are written only
to the OS keyring via :mod:`insar_prep.providers.asf.credentials` -- never to a
project file -- and the password field uses no-echo input.
"""

from __future__ import annotations

import importlib.util

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep.core.exceptions import CredentialError
from insar_prep.providers.asf.credentials import (
    EARTHDATA_TOKEN_URL,
    CredentialSource,
    clear_stored_credentials,
    resolve_credentials,
    store_login,
    store_token,
    stored_credential_status,
)

_HELP_TEXT = (
    "Sign in to NASA Earthdata to download Sentinel-1 SLCs. Paste a personal "
    "token (recommended) — click 'Open Earthdata token page' to generate one, "
    "then copy it here — or enter your username and password. Credentials are "
    "stored only in your operating system's secret store (never in a project file)."
)


class EarthdataLoginDialog(QDialog):
    """Collect and store Earthdata credentials in the OS keyring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Earthdata Login")

        self._token_edit = QLineEdit()
        self._token_edit.setObjectName("earthdata_token_edit")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText("Paste your Earthdata bearer token (recommended)")

        self._username_edit = QLineEdit()
        self._username_edit.setObjectName("earthdata_username_edit")
        self._password_edit = QLineEdit()
        self._password_edit.setObjectName("earthdata_password_edit")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Token:", self._token_edit)
        form.addRow("or Username:", self._username_edit)
        form.addRow("Password:", self._password_edit)

        help_label = QLabel(_HELP_TEXT)
        help_label.setWordWrap(True)

        self._open_page_button = QPushButton("Open Earthdata token page")
        self._open_page_button.setObjectName("earthdata_open_page_button")
        self._open_page_button.clicked.connect(self._open_token_page)
        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("earthdata_save_button")
        self._save_button.clicked.connect(self.save_credentials)
        self._test_button = QPushButton("Test connection")
        self._test_button.setObjectName("earthdata_test_button")
        self._test_button.clicked.connect(self.test_connection)
        self._clear_button = QPushButton("Clear stored")
        self._clear_button.setObjectName("earthdata_clear_button")
        self._clear_button.clicked.connect(self.clear_credentials)
        self._close_button = QPushButton("Close")
        self._close_button.setObjectName("earthdata_close_button")
        self._close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        for button in (
            self._open_page_button,
            self._save_button,
            self._test_button,
            self._clear_button,
            self._close_button,
        ):
            button_row.addWidget(button)

        self._status_label = QLabel()
        self._status_label.setObjectName("earthdata_status_label")
        self._status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)

        self.refresh_status()

    def _set_status(self, text: str) -> None:
        # The dialog never displays secrets: input fields are cleared after a
        # successful save and only the credential *type* / non-secret messages are
        # shown here, so the text is safe to display verbatim.
        self._status_label.setText(text)

    def status_text(self) -> str:
        return self._status_label.text()

    def refresh_status(self) -> None:
        """Show what is currently stored (no secret values)."""
        try:
            status = stored_credential_status()
        except CredentialError as exc:
            self._set_status(str(exc))
            return
        self._set_status(f"Stored Earthdata credential: {status}")

    def save_credentials(self) -> bool:
        """Persist the entered token or username/password to the OS keyring."""
        token = self._token_edit.text().strip()
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        try:
            if token:
                store_token(token)
                self._set_status("Saved Earthdata token to the OS keyring.")
            elif username and password:
                store_login(username, password)
                self._set_status(f"Saved Earthdata login for {username} to the OS keyring.")
            else:
                self._set_status("Enter a token, or both a username and password.")
                return False
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        # Do not keep secrets lingering in the widgets after a successful save.
        self._token_edit.clear()
        self._password_edit.clear()
        return True

    def clear_credentials(self) -> bool:
        """Remove any stored Earthdata credentials from the OS keyring."""
        try:
            removed = clear_stored_credentials()
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        self._set_status(
            "Cleared stored Earthdata credentials."
            if removed
            else "No stored Earthdata credentials to clear."
        )
        return removed

    def test_connection(self) -> None:
        """Live, opt-in authenticated reachability check against Earthdata (network)."""
        try:
            resolved = resolve_credentials(CredentialSource.AUTO)
        except CredentialError as exc:
            self._set_status(str(exc))
            return
        if importlib.util.find_spec("requests") is None:
            self._set_status("Install the 'download' extra (requests) to test the connection.")
            return
        from insar_prep.providers.asf.downloader import probe_earthdata_auth

        ok, message = probe_earthdata_auth(resolved)
        self._set_status(f"Connection test: {'OK' if ok else 'FAILED'} ({message})")

    def _open_token_page(self) -> None:
        QDesktopServices.openUrl(QUrl(EARTHDATA_TOKEN_URL))
