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

from insar_prep import i18n
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


class EarthdataLoginDialog(QDialog):
    """Collect and store Earthdata credentials in the OS keyring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("dlg.earthdata.title"))

        self._token_edit = QLineEdit()
        self._token_edit.setObjectName("earthdata_token_edit")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText(i18n.tr("dlg.earthdata.token_ph"))

        self._username_edit = QLineEdit()
        self._username_edit.setObjectName("earthdata_username_edit")
        self._password_edit = QLineEdit()
        self._password_edit.setObjectName("earthdata_password_edit")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow(i18n.tr("dlg.earthdata.token"), self._token_edit)
        form.addRow(i18n.tr("dlg.earthdata.username"), self._username_edit)
        form.addRow(i18n.tr("dlg.earthdata.password"), self._password_edit)

        help_label = QLabel(i18n.tr("dlg.earthdata.help"))
        help_label.setWordWrap(True)

        self._open_page_button = QPushButton(i18n.tr("dlg.earthdata.open_page"))
        self._open_page_button.setObjectName("earthdata_open_page_button")
        self._open_page_button.clicked.connect(self._open_token_page)
        self._save_button = QPushButton(i18n.tr("common.save"))
        self._save_button.setObjectName("earthdata_save_button")
        self._save_button.clicked.connect(self.save_credentials)
        self._test_button = QPushButton(i18n.tr("dlg.earthdata.test"))
        self._test_button.setObjectName("earthdata_test_button")
        self._test_button.clicked.connect(self.test_connection)
        self._clear_button = QPushButton(i18n.tr("common.clear_stored"))
        self._clear_button.setObjectName("earthdata_clear_button")
        self._clear_button.clicked.connect(self.clear_credentials)
        self._close_button = QPushButton(i18n.tr("common.close"))
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
        self._set_status(i18n.tr("dlg.earthdata.status", status=status))

    def save_credentials(self) -> bool:
        """Persist the entered token or username/password to the OS keyring."""
        token = self._token_edit.text().strip()
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        try:
            if token:
                store_token(token)
                self._set_status(i18n.tr("dlg.earthdata.saved_token"))
            elif username and password:
                # The username is intentionally NOT echoed back here.
                store_login(username, password)
                self._set_status(i18n.tr("dlg.earthdata.saved_login"))
            else:
                self._set_status(i18n.tr("dlg.earthdata.need_input"))
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
            i18n.tr("dlg.earthdata.cleared") if removed else i18n.tr("dlg.earthdata.none_to_clear")
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
            self._set_status(i18n.tr("dlg.earthdata.need_extra"))
            return
        from insar_prep.providers.asf.downloader import probe_earthdata_auth

        ok, message = probe_earthdata_auth(resolved)
        key = "dlg.earthdata.test_ok" if ok else "dlg.earthdata.test_fail"
        self._set_status(i18n.tr(key, msg=message))

    def _open_token_page(self) -> None:
        QDesktopServices.openUrl(QUrl(EARTHDATA_TOKEN_URL))
