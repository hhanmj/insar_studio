"""GACOS email dialog: configure the GACOS delivery email from the GUI.

A friendly front-end for the same OS-keyring storage used by
``insar-prep gacos-auth``: the user enters the email address GACOS delivers
result links to (a button opens the GACOS portal in the browser). The email is
not a password, so it is shown in clear text, but it is stored only in the OS
keyring via :mod:`insar_prep.providers.gacos.credentials` (never in a project
file) and shown masked in the status line.
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
from insar_prep.providers.gacos.credentials import (
    GACOS_PORTAL_URL,
    clear_stored_gacos_email,
    store_gacos_email,
    stored_gacos_email_status,
)

_INTRO_TEXT = (
    "Enter the email address GACOS should deliver result links to. GACOS has no "
    "API key: a request is a web-form submission, and the products are emailed to "
    "this address. It is stored only in your operating system's secret store "
    "(never in a project file)."
)


class GacosEmailDialog(QDialog):
    """Collect and store the GACOS delivery email in the OS keyring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GACOS Email")

        self._email_edit = QLineEdit()
        self._email_edit.setObjectName("gacos_email_edit")
        self._email_edit.setPlaceholderText("you@example.com")

        form = QFormLayout()
        form.addRow("Email:", self._email_edit)

        intro_label = QLabel(_INTRO_TEXT)
        intro_label.setWordWrap(True)

        self._portal_button = QPushButton("Open GACOS website")
        self._portal_button.setObjectName("gacos_portal_button")
        self._portal_button.clicked.connect(self._open_portal)
        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("gacos_email_save_button")
        self._save_button.clicked.connect(self.save_email)
        self._clear_button = QPushButton("Clear stored")
        self._clear_button.setObjectName("gacos_email_clear_button")
        self._clear_button.clicked.connect(self.clear_email)
        self._close_button = QPushButton("Close")
        self._close_button.setObjectName("gacos_email_close_button")
        self._close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        for button in (
            self._portal_button,
            self._save_button,
            self._clear_button,
            self._close_button,
        ):
            button_row.addWidget(button)

        self._status_label = QLabel()
        self._status_label.setObjectName("gacos_email_status_label")
        self._status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro_label)
        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self._status_label)

        self.refresh_status()

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def status_text(self) -> str:
        return self._status_label.text()

    def refresh_status(self) -> None:
        """Show whether an email is stored (masked; no full address)."""
        try:
            status = stored_gacos_email_status()
        except CredentialError as exc:
            self._set_status(str(exc))
            return
        self._set_status(f"Stored GACOS email: {status}")

    def save_email(self) -> bool:
        """Persist the entered email to the OS keyring."""
        email = self._email_edit.text().strip()
        if not email:
            self._set_status("Enter your GACOS email first.")
            return False
        try:
            store_gacos_email(email)
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        self._set_status("Saved GACOS email to the OS keyring.")
        return True

    def clear_email(self) -> bool:
        """Remove any stored GACOS email from the OS keyring."""
        try:
            removed = clear_stored_gacos_email()
        except CredentialError as exc:
            self._set_status(str(exc))
            return False
        self._set_status(
            "Cleared the stored GACOS email." if removed else "No stored GACOS email to clear."
        )
        return removed

    def _open_portal(self) -> None:
        QDesktopServices.openUrl(QUrl(GACOS_PORTAL_URL))
