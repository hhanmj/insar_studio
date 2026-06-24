"""Centre panel: plan or download the current Region's DEM from OpenTopography.

GUI front-end for the real DEM download. It reuses the same offline planner as
``download-dem`` for a dry-run preview and the shared
:func:`insar_prep.providers.dem.run_dem_download` orchestration for the real,
key-authenticated transfer. The panel re-implements no download logic.

The real transfer runs on a :class:`DemDownloadWorker` background thread so the
window stays responsive and the user can cancel; the result streams back via Qt
signals. The OpenTopography API key is taken from the OS keyring / environment
(configured via the *OpenTopography API Key* dialog or ``insar-prep dem-auth
login``); this panel never reads, stores, or displays the key.
"""

from __future__ import annotations

import threading
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
from insar_prep.core.enums import DemDataset
from insar_prep.core.exceptions import CredentialError, InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.providers.dem.credentials import DemKeySource, stored_api_key_status
from insar_prep.providers.dem.download_runner import DemDownloadRunSummary, run_dem_download
from insar_prep.providers.dem.downloader import DemDownloadResult
from insar_prep.providers.dem.types import DemRequestPlan

# User-facing labels for the two download modes (value -> label).
_MODE_DRY_RUN = "dry-run"
_MODE_REAL = "real"
_MODE_LABELS: tuple[tuple[str, str], ...] = (
    (_MODE_DRY_RUN, "Dry-run (offline plan only)"),
    (_MODE_REAL, "Real download (needs OpenTopography key)"),
)


class DemDownloadWorker(QThread):
    """Run :func:`run_dem_download` off the GUI thread, streaming the result back.

    Emits :attr:`dem_done` for the completed DEM, then exactly one of
    :attr:`run_finished` (with a :class:`DemDownloadRunSummary`) or
    :attr:`run_failed` (with a credential-safe message). Call :meth:`cancel` to
    request a clean stop.
    """

    dem_done = Signal(object)
    run_finished = Signal(object)
    run_failed = Signal(str)

    def __init__(
        self,
        plan: DemRequestPlan,
        output_dir: str | Path,
        key_source: DemKeySource,
        *,
        max_retries: int = 3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._plan = plan
        self._output_dir = output_dir
        self._key_source = key_source
        self._max_retries = max_retries
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; the transfer aborts cleanly."""
        self._cancel.set()

    def run(self) -> None:
        try:
            summary = run_dem_download(
                [self._plan],
                self._output_dir,
                key_source=self._key_source,
                max_retries=self._max_retries,
                progress=self.dem_done.emit,
                cancel_event=self._cancel,
            )
        except InsarPrepError as exc:
            self.run_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            self.run_failed.emit(mask_text(f"{type(exc).__name__}: {exc}"))
            return
        self.run_finished.emit(summary)


class DemDownloadPanel(QGroupBox):
    """Plan (dry-run) or download (real) the current Region's DEM."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("DEM Download (OpenTopography)", parent)
        self.setObjectName("dem_download_panel")

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("dem_download_output_dir")
        self.output_dir_edit.setPlaceholderText(
            "Output root (DEM goes under <root>/<region>/04_dem)"
        )
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setObjectName("dem_download_browse_button")
        self.browse_button.clicked.connect(self._on_browse)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(self.browse_button)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("dem_download_mode_combo")
        for value, label in _MODE_LABELS:
            self.mode_combo.addItem(label, value)

        self.dataset_combo = QComboBox()
        self.dataset_combo.setObjectName("dem_download_dataset_combo")
        for dataset in DemDataset:
            self.dataset_combo.addItem(dataset.value, dataset.value)
        self._select_default_dataset()

        self.key_status_label = QLabel("OpenTopography API key: unknown")
        self.key_status_label.setObjectName("dem_download_key_status")
        self.key_status_label.setWordWrap(True)
        self.key_button = QPushButton("OpenTopography API Key…")
        self.key_button.setObjectName("dem_download_key_button")
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_status_label, 1)
        key_row.addWidget(self.key_button)

        self.download_button = QPushButton("Run")
        self.download_button.setObjectName("dem_download_run_button")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dem_download_cancel_button")
        self.cancel_button.setEnabled(False)
        button_row = QHBoxLayout()
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.cancel_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("dem_download_progress")
        self.progress_bar.setVisible(False)

        self.result_label = QLabel("DEM download: not started")
        self.result_label.setObjectName("dem_download_result")
        self.result_label.setWordWrap(True)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("dem_download_log")
        self.log_view.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Output root:", output_row)
        form.addRow("Mode:", self.mode_combo)
        form.addRow("Dataset:", self.dataset_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(key_row)
        layout.addLayout(button_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.result_label)
        layout.addWidget(self.log_view)

        self.refresh_key_status()

    def _select_default_dataset(self) -> None:
        index = self.dataset_combo.findData(DemDataset.COP30.value)
        if index >= 0:
            self.dataset_combo.setCurrentIndex(index)

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("dem.title"))
        self.browse_button.setText(i18n.tr("common.browse"))
        self.key_button.setText(i18n.tr("dem.key_button"))
        self.download_button.setText(i18n.tr("common.run"))
        self.cancel_button.setText(i18n.tr("common.cancel"))

    # --- inputs ---------------------------------------------------------------

    def output_dir(self) -> str:
        """Return the entered output root (stripped)."""
        return self.output_dir_edit.text().strip()

    def selected_mode(self) -> str:
        """Return the selected mode value (``"dry-run"`` or ``"real"``)."""
        return str(self.mode_combo.currentData())

    def selected_dataset(self) -> str:
        """Return the selected DEM dataset value (e.g. ``"COP30"``)."""
        return str(self.dataset_combo.currentData())

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select output root")
        if chosen:
            self.output_dir_edit.setText(chosen)

    # --- offline dry-run ------------------------------------------------------

    def plan_summary(self, plan: DemRequestPlan) -> None:
        """Show the offline dry-run plan (dataset / bbox / destination); no network."""
        bbox = plan.request_bbox
        self.result_label.setText(
            f"Dry-run plan: {plan.dataset} over "
            f"[{bbox.west}, {bbox.south}, {bbox.east}, {bbox.north}] (no file downloaded)"
        )
        self.log_view.setPlainText(f"Planned DEM destination: {plan.raw_dem_path}")

    # --- key status -----------------------------------------------------------

    def refresh_key_status(self) -> None:
        """Show whether an OpenTopography key is stored (set / none), no secret."""
        try:
            status = stored_api_key_status()
        except CredentialError as exc:
            self.key_status_label.setText(str(exc))
            return
        self.key_status_label.setText(f"OpenTopography API key: {status}")

    def key_status_text(self) -> str:
        return self.key_status_label.text()

    # --- run lifecycle (driven by the worker, all on the GUI thread) ----------

    def begin_run(self) -> None:
        """Prepare the panel for a real DEM download."""
        self.set_running(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.result_label.setText("Downloading DEM…")
        self.log_view.clear()

    def set_running(self, running: bool) -> None:
        """Toggle the controls between idle and an in-progress download."""
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.dataset_combo.setEnabled(not running)
        self.output_dir_edit.setReadOnly(running)
        self.progress_bar.setVisible(running)

    def on_dem_done(self, result: DemDownloadResult) -> None:
        """Append the completed DEM to the log and advance the progress bar."""
        suffix = f" [{result.error_code}]" if result.error_code else ""
        self.log_view.appendPlainText(
            f"{result.region_safe_name} ({result.dataset}): {result.outcome.value}"
            f" ({result.bytes_written} bytes){suffix}"
        )
        self.progress_bar.setValue(1)

    def set_dem_summary(self, summary: DemDownloadRunSummary) -> None:
        """Show the final, credential-safe counts after a real run."""
        self.set_running(False)
        prefix = "DEM download cancelled" if summary.cancelled else "DEM download finished"
        self.result_label.setText(f"{prefix}: {summary.summary_line()}")
        if summary.results_path is not None:
            self.log_view.appendPlainText(f"Results: {summary.results_path}")

    def set_failed(self, message: str) -> None:
        """Show a credential-safe failure message and reset the controls."""
        self.set_running(False)
        self.result_label.setText(f"DEM download failed: {message}")
