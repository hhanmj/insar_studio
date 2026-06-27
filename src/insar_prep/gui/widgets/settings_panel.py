"""Settings page: language, appearance, and account/key configuration (Task 056).

Groups the cross-cutting configuration in one place (mirroring the "Settings" tab
of modern desktop tools): the UI language, the light/dark theme, and one-click
buttons that open the existing credential dialogs (Earthdata, OpenTopography,
GACOS email). The panel holds no business logic -- the main window wires its
controls to the same handlers used elsewhere.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.gui import theme as theme_module


class SettingsPanel(QWidget):
    """Language / appearance / accounts settings for the GUI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settings_panel")

        # --- appearance card (language + theme) ---
        self.appearance_box = QGroupBox(i18n.tr("settings.appearance"))
        self.appearance_box.setObjectName("settings_appearance_box")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("settings_language_combo")
        for code, name in i18n.available_languages():
            self.language_combo.addItem(name, code)
        self._select_combo_data(self.language_combo, i18n.get_language())

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("settings_theme_combo")
        for name in theme_module.THEMES:
            self.theme_combo.addItem(i18n.tr(f"theme.{name}"), name)
        self._select_combo_data(self.theme_combo, theme_module.DEFAULT_THEME)

        self.language_label = QLabel(i18n.tr("settings.language"))
        self.theme_label = QLabel(i18n.tr("settings.theme"))
        appearance_form = QFormLayout(self.appearance_box)
        appearance_form.addRow(self.language_label, self.language_combo)
        appearance_form.addRow(self.theme_label, self.theme_combo)

        # --- accounts & keys card ---
        self.credentials_box = QGroupBox(i18n.tr("settings.credentials.title"))
        self.credentials_box.setObjectName("settings_credentials_box")
        self.credentials_subtitle = QLabel(i18n.tr("settings.credentials.subtitle"))
        self.credentials_subtitle.setObjectName("page_subtitle")
        self.credentials_subtitle.setWordWrap(True)
        self.earthdata_button = QPushButton(i18n.tr("settings.earthdata"))
        self.earthdata_button.setObjectName("settings_earthdata_button")
        self.opentopo_button = QPushButton(i18n.tr("settings.opentopo"))
        self.opentopo_button.setObjectName("settings_opentopo_button")
        self.gacos_email_button = QPushButton(i18n.tr("settings.gacos"))
        self.gacos_email_button.setObjectName("settings_gacos_button")
        button_row = QHBoxLayout()
        button_row.addWidget(self.earthdata_button)
        button_row.addWidget(self.opentopo_button)
        button_row.addWidget(self.gacos_email_button)
        button_row.addStretch(1)
        credentials_layout = QVBoxLayout(self.credentials_box)
        credentials_layout.addWidget(self.credentials_subtitle)
        credentials_layout.addLayout(button_row)

        layout = QVBoxLayout(self)
        layout.addWidget(self.appearance_box)
        layout.addWidget(self.credentials_box)
        layout.addStretch(1)

    @staticmethod
    def _select_combo_data(combo: QComboBox, data: str) -> None:
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    def selected_language(self) -> str:
        return str(self.language_combo.currentData())

    def selected_theme(self) -> str:
        return str(self.theme_combo.currentData())

    def sync_language(self, code: str) -> None:
        """Reflect the active language in the combo without emitting a change."""
        self.language_combo.blockSignals(True)
        self._select_combo_data(self.language_combo, code)
        self.language_combo.blockSignals(False)

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.appearance_box.setTitle(i18n.tr("settings.appearance"))
        self.language_label.setText(i18n.tr("settings.language"))
        self.theme_label.setText(i18n.tr("settings.theme"))
        self.credentials_box.setTitle(i18n.tr("settings.credentials.title"))
        self.credentials_subtitle.setText(i18n.tr("settings.credentials.subtitle"))
        self.earthdata_button.setText(i18n.tr("settings.earthdata"))
        self.opentopo_button.setText(i18n.tr("settings.opentopo"))
        self.gacos_email_button.setText(i18n.tr("settings.gacos"))
        # Theme combo labels are translatable; preserve the current selection.
        current = self.selected_theme()
        self.theme_combo.blockSignals(True)
        for i in range(self.theme_combo.count()):
            name = self.theme_combo.itemData(i)
            self.theme_combo.setItemText(i, i18n.tr(f"theme.{name}"))
        self._select_combo_data(self.theme_combo, current)
        self.theme_combo.blockSignals(False)
