"""OpenTopography API-key dialog: configure the DEM-download key from the GUI.

A friendly front-end for the same OS-keyring storage used by
``insar-prep dem-auth``: the user pastes their **own** personal OpenTopography
API key (a button opens the registration page, another opens the API-key page in
the browser). The key is written only to the OS keyring via
:mod:`insar_prep.providers.dem.credentials` -- never to a project file -- and the
field uses no-echo input. No key is bundled or shared by the app: each user
brings their own free key (the free key is rate limited and tied to the account).
"""

from __future__ import annotations

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
from insar_prep.providers.dem.credentials import (
    OPENTOPO_API_KEY_URL,
    OPENTOPO_REGISTER_URL,
    clear_stored_api_key,
    opentopo_api_key_guidance,
    store_api_key,
    stored_api_key_status,
)

_INTRO_TEXT = (
    "Enter your personal OpenTopography API key to download DEMs. Each user "
    "supplies their own free key (no key is bundled, so heavy use never shares a "
    "rate limit). The key is stored only in your operating system's secret store "
    "(never in a project file)."
)


class OpenTopographyKeyDialog(QDialog):
    """Collect and store the OpenTopography API key in the OS keyring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenTopography API Key")

        self._key_edit = QLineEdit()
        self._key_edit.setObjectName("opentopo_key_edit")
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("Paste your OpenTopography API key")

        form = QFormLayout()
        form.addRow("API key:", self._key_edit)

        intro_label = QLabel(_INTRO_TEXT)
        intro_label.setWordWrap(True)
        guidance_label = QLabel(opentopo_api_key_guidance())
        guidance_label.setObjectName("opentopo_guidance_label")
        guidance_label.setWordWrap(True)

        self._register_button = QPushButton("Open registration page")
        self._register_button.setObjectName("opentopo_register_button")
        self._register_button.clicked.connect(self._open_register_page)
        self._key_page_button = QPushButton("Open API key page")
        self._key_page_button.setObjectName("opentopo_key_page_button")
        self._key_page_button.clicked.connect(self._open_key_page)
        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("opentopo_save_button")
        self._save_button.clicked.connect(self.save_key)
        self._clear_button = QPushButton("Clear stored")
        self._clear_button.setObjectName("opentopo_clear_button")
        self._clear_button.clicked.connect(self.clear_key)
        self._close_button = QPushButton("Close")
        self._close_button.setObjectName("opentopo_close_button")
        self._close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        for button in (
            self._register_button,
            self._key_page_button,
            self._save_button,
            self._clear_button,
            self._close_button,
        ):
            button_row.addWidget(button)

        self._status_label = QLabel()
        self._status_label.setObjectName("opentopo_status_label")
        self._status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro_label)
        layout.addLayout(form)
        layout.addWidget(guidance_label)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)

        self.refresh_status()

    def _set_status(self, text: str) -> None:
        # The dialog never displays the key: the input is cleared after a
        # successful save and only the non-secret status (set / none) is shown.
        self._status_label.setText(text)

    def status_text(self) -> str:
        return self._status_label.text()

    def refresh_status(self) -> None:
        """Show whether a key is currently stored (no secret value)."""
        try:
            status = stored_api_key_status()
        except CredentialError as exc:
            self._set_status(str(exc))
            return
        self._set_status(f"Stored OpenTopography API key: {status}")

    def save_key(self) -> bool:
        """Persist the entered API key to the OS keyring."""
        api_key = self._key_edit.text().strip()
        if not api_key:
            self._set_status("Enter your OpenTopography API key first.")
            return False
        try:
            store_api_key(api_key)
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        self._set_status("Saved OpenTopography API key to the OS keyring.")
        # Do not keep the secret lingering in the widget after a successful save.
        self._key_edit.clear()
        return True

    def clear_key(self) -> bool:
        """Remove any stored OpenTopography API key from the OS keyring."""
        try:
            removed = clear_stored_api_key()
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        self._set_status(
            "Cleared the stored OpenTopography API key."
            if removed
            else "No stored OpenTopography API key to clear."
        )
        return removed

    def _open_register_page(self) -> None:
        QDesktopServices.openUrl(QUrl(OPENTOPO_REGISTER_URL))

    def _open_key_page(self) -> None:
        QDesktopServices.openUrl(QUrl(OPENTOPO_API_KEY_URL))
