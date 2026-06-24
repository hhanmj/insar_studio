"""Centre panel: submit a real GACOS request and download the emailed result.

GUI front-end for the real GACOS client. GACOS has no API: this panel reuses the
shared :func:`insar_prep.providers.gacos.run_gacos_request` (POST the web form in
<=20-date batches) and :func:`insar_prep.providers.gacos.run_gacos_download`
(fetch the emailed result link[s] and import the products). Both run on a
background thread so the window stays responsive; results stream back via Qt
signals. The delivery email is taken from the OS keyring / ``GACOS_EMAIL`` env
(configured via the *GACOS Email* dialog or ``insar-prep gacos-auth login``);
this panel never stores or displays the full address.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from insar_prep import i18n
from insar_prep.core.exceptions import CredentialError, InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.core.models import BBox
from insar_prep.providers.gacos.credentials import GacosEmailSource, stored_gacos_email_status
from insar_prep.providers.gacos.download_runner import (
    GacosDownloadRunSummary,
    GacosRequestRunSummary,
    run_gacos_download,
    run_gacos_request,
)
from insar_prep.providers.gacos.downloader import (
    GacosFetchResult,
    GacosOutputFormat,
    GacosSubmitResult,
)


def _parse_date_lines(text: str) -> list[date]:
    """Parse YYYYMMDD tokens (newline/comma/space separated) into dates."""
    tokens = [tok for tok in text.replace(",", " ").split() if tok]
    parsed: list[date] = []
    for token in tokens:
        try:
            parsed.append(datetime.strptime(token, "%Y%m%d").date())
        except ValueError:
            continue
    return sorted(set(parsed))


class GacosRequestWorker(QThread):
    """Run :func:`run_gacos_request` off the GUI thread."""

    batch_done = Signal(object)
    run_finished = Signal(object)
    run_failed = Signal(str)

    def __init__(
        self,
        *,
        region_safe_name: str,
        bbox: BBox,
        dates: list[date],
        email: str,
        output_root: str | Path,
        hour: int,
        minute: int,
        output_format: GacosOutputFormat,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kwargs = {
            "region_safe_name": region_safe_name,
            "bbox": bbox,
            "dates": dates,
            "email": email,
            "output_root": output_root,
            "hour": hour,
            "minute": minute,
            "output_format": output_format,
            "email_source": GacosEmailSource.AUTO,
        }

    def run(self) -> None:
        try:
            summary = run_gacos_request(progress=self.batch_done.emit, **self._kwargs)
        except InsarPrepError as exc:
            self.run_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            self.run_failed.emit(mask_text(f"{type(exc).__name__}: {exc}"))
            return
        self.run_finished.emit(summary)


class GacosFetchWorker(QThread):
    """Run :func:`run_gacos_download` off the GUI thread."""

    fetch_done = Signal(object)
    run_finished = Signal(object)
    run_failed = Signal(str)

    def __init__(
        self,
        *,
        urls: list[str],
        output_directory: str | Path,
        expected_dates: list[date] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._urls = urls
        self._output_directory = output_directory
        self._expected_dates = expected_dates
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            summary = run_gacos_download(
                self._urls,
                self._output_directory,
                expected_dates=self._expected_dates,
                email_source=GacosEmailSource.AUTO,
                progress=self.fetch_done.emit,
                cancel_event=self._cancel,
            )
        except InsarPrepError as exc:
            self.run_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            self.run_failed.emit(mask_text(f"{type(exc).__name__}: {exc}"))
            return
        self.run_finished.emit(summary)


class GacosDownloadPanel(QGroupBox):
    """Submit a real GACOS request and fetch the emailed result archive(s)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(i18n.tr("gacos.title"), parent)
        self.setObjectName("gacos_download_panel")

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("gacos_output_dir")
        self.output_dir_edit.setPlaceholderText(
            "Output root (products under <root>/<region>/05_atmosphere/gacos)"
        )
        self.browse_button = QPushButton(i18n.tr("common.browse"))
        self.browse_button.setObjectName("gacos_browse_button")
        self.browse_button.clicked.connect(self._on_browse)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(self.browse_button)

        self.time_edit = QLineEdit("00:00")
        self.time_edit.setObjectName("gacos_time_edit")
        self.time_edit.setPlaceholderText("UTC HH:MM")

        self.format_combo = QComboBox()
        self.format_combo.setObjectName("gacos_format_combo")
        for fmt in GacosOutputFormat:
            self.format_combo.addItem(fmt.value, fmt.value)

        self.dates_label = QLabel(i18n.tr("gacos.dates_label"))
        self.dates_text = QPlainTextEdit()
        self.dates_text.setObjectName("gacos_dates_text")
        self.dates_text.setPlaceholderText("Leave empty to use the imported scene dates")
        self.dates_text.setFixedHeight(60)

        self.url_label = QLabel(i18n.tr("gacos.url_label"))
        self.url_text = QPlainTextEdit()
        self.url_text.setObjectName("gacos_url_text")
        self.url_text.setPlaceholderText("Paste the GACOS download link(s) from your email")
        self.url_text.setFixedHeight(60)

        self.email_status_label = QLabel("GACOS email: unknown")
        self.email_status_label.setObjectName("gacos_email_status")
        self.email_status_label.setWordWrap(True)
        self.email_button = QPushButton(i18n.tr("gacos.email_button"))
        self.email_button.setObjectName("gacos_email_button")
        email_row = QHBoxLayout()
        email_row.addWidget(self.email_status_label, 1)
        email_row.addWidget(self.email_button)

        self.submit_button = QPushButton(i18n.tr("gacos.submit"))
        self.submit_button.setObjectName("gacos_submit_button")
        self.download_button = QPushButton(i18n.tr("gacos.fetch"))
        self.download_button.setObjectName("gacos_fetch_button")
        self.cancel_button = QPushButton(i18n.tr("common.cancel"))
        self.cancel_button.setObjectName("gacos_cancel_button")
        self.cancel_button.setEnabled(False)
        button_row = QHBoxLayout()
        button_row.addWidget(self.submit_button)
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.cancel_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("gacos_progress")
        self.progress_bar.setVisible(False)

        self.result_label = QLabel("GACOS: not started")
        self.result_label.setObjectName("gacos_result")
        self.result_label.setWordWrap(True)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("gacos_log")
        self.log_view.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Output root:", output_row)
        form.addRow("UTC time:", self.time_edit)
        form.addRow("Format:", self.format_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.dates_label)
        layout.addWidget(self.dates_text)
        layout.addLayout(email_row)
        layout.addWidget(self.url_label)
        layout.addWidget(self.url_text)
        layout.addLayout(button_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.result_label)
        layout.addWidget(self.log_view)

        self.refresh_email_status()

    # --- inputs ---------------------------------------------------------------

    def output_dir(self) -> str:
        return self.output_dir_edit.text().strip()

    def manual_dates(self) -> list[date]:
        """Parse the optional YYYYMMDD date override (empty list if none)."""
        return _parse_date_lines(self.dates_text.toPlainText())

    def result_urls(self) -> list[str]:
        """Return the GACOS result link(s) entered for downloading."""
        return [line.strip() for line in self.url_text.toPlainText().splitlines() if line.strip()]

    def selected_format(self) -> GacosOutputFormat:
        return GacosOutputFormat(str(self.format_combo.currentData()))

    def selected_time(self) -> tuple[int, int]:
        """Parse the UTC ``HH:MM`` field into ``(hour, minute)`` (clamped)."""
        text = self.time_edit.text().strip() or "00:00"
        hour_str, _, minute_str = text.partition(":")
        try:
            hour = max(0, min(23, int(hour_str)))
            minute = max(0, min(59, int(minute_str or "0")))
        except ValueError:
            return 0, 0
        return hour, minute

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select output root")
        if chosen:
            self.output_dir_edit.setText(chosen)

    # --- email status ---------------------------------------------------------

    def refresh_email_status(self) -> None:
        """Show whether a GACOS email is stored (masked), no full address."""
        try:
            status = stored_gacos_email_status()
        except CredentialError as exc:
            self.email_status_label.setText(str(exc))
            return
        self.email_status_label.setText(f"GACOS email: {status}")

    def email_status_text(self) -> str:
        return self.email_status_label.text()

    # --- run lifecycle --------------------------------------------------------

    def begin_run(self, message: str) -> None:
        """Prepare the panel for a background request/download."""
        self.set_running(True)
        self.progress_bar.setRange(0, 0)
        self.result_label.setText(message)
        self.log_view.clear()

    def set_running(self, running: bool) -> None:
        self.submit_button.setEnabled(not running)
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.progress_bar.setVisible(running)

    def on_batch_done(self, result: GacosSubmitResult) -> None:
        suffix = f" [{result.error_code}]" if result.error_code else ""
        self.log_view.appendPlainText(
            f"batch {result.batch_index}/{result.batch_count}: {result.outcome.value}"
            f" ({result.date_count} date(s)){suffix} - {mask_text(result.message)}"
        )

    def on_fetch_done(self, result: GacosFetchResult) -> None:
        suffix = f" [{result.error_code}]" if result.error_code else ""
        self.log_view.appendPlainText(
            f"fetch: {result.outcome.value} ({result.bytes_written} bytes){suffix}"
        )

    def set_request_summary(self, summary: GacosRequestRunSummary) -> None:
        self.set_running(False)
        self.progress_bar.setRange(0, 1)
        self.result_label.setText(f"GACOS request: {summary.summary_line()}")
        if summary.results_path is not None:
            self.log_view.appendPlainText(f"Results: {summary.results_path}")
        if summary.submitted:
            self.log_view.appendPlainText(
                "Watch your email for the download link, then paste it above and click "
                f"'{i18n.tr('gacos.fetch')}'."
            )

    def set_download_summary(self, summary: GacosDownloadRunSummary) -> None:
        self.set_running(False)
        self.progress_bar.setRange(0, 1)
        self.result_label.setText(f"GACOS download: {summary.summary_line()}")
        if summary.results_path is not None:
            self.log_view.appendPlainText(f"Results: {summary.results_path}")

    def set_failed(self, message: str) -> None:
        self.set_running(False)
        self.progress_bar.setRange(0, 1)
        self.result_label.setText(f"GACOS failed: {message}")

    # --- i18n -----------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("gacos.title"))
        self.browse_button.setText(i18n.tr("common.browse"))
        self.email_button.setText(i18n.tr("gacos.email_button"))
        self.submit_button.setText(i18n.tr("gacos.submit"))
        self.download_button.setText(i18n.tr("gacos.fetch"))
        self.cancel_button.setText(i18n.tr("common.cancel"))
        self.dates_label.setText(i18n.tr("gacos.dates_label"))
        self.url_label.setText(i18n.tr("gacos.url_label"))
