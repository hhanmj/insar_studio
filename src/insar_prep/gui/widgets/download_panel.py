"""Centre panel: plan or download Sentinel-1 SLCs from the current Region.

This is the GUI front-end for the real ASF download. It reuses the same offline
planner as ``plan-asf-downloads`` for a dry-run preview and the shared
:func:`insar_prep.providers.asf.run_asf_download` orchestration for the real,
credentialed transfer. The panel re-implements no download logic.

The real transfer runs on a :class:`DownloadWorker` background thread so the
window stays responsive and the user can cancel; per-scene results stream back to
the panel via Qt signals. Credentials are taken from the OS keyring / environment
/ ``~/.netrc`` (configured via the *Earthdata Login* dialog or ``insar-prep auth
login``); this panel never reads, stores, or displays a secret.
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
from insar_prep.core.exceptions import CredentialError, InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.core.models import Scene
from insar_prep.providers.asf.credentials import CredentialSource, stored_credential_status
from insar_prep.providers.asf.download_plan import (
    AsfDownloadPlan,
    build_asf_download_plan,
    write_asf_download_plan,
)
from insar_prep.providers.asf.download_runner import DownloadRunSummary, run_asf_download
from insar_prep.providers.asf.downloader import DownloadResult
from insar_prep.providers.asf.scene_parser import deduplicate_scenes

# User-facing labels for the two download modes (value -> label).
_MODE_DRY_RUN = "dry-run"
_MODE_REAL = "real"
_MODE_LABELS: tuple[tuple[str, str], ...] = (
    (_MODE_DRY_RUN, "Dry-run (offline plan only)"),
    (_MODE_REAL, "Real download (needs Earthdata login)"),
)


class DownloadWorker(QThread):
    """Run :func:`run_asf_download` off the GUI thread, streaming results back.

    Emits :attr:`scene_done` for each completed scene, then exactly one of
    :attr:`run_finished` (with a :class:`DownloadRunSummary`) or
    :attr:`run_failed` (with a credential-safe message). Call :meth:`cancel` to
    request a clean stop between/within scenes.
    """

    scene_done = Signal(object)
    run_finished = Signal(object)
    run_failed = Signal(str)

    def __init__(
        self,
        scenes: list[Scene],
        output_dir: str | Path,
        credential_source: CredentialSource,
        *,
        max_retries: int = 3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scenes = list(scenes)
        self._output_dir = output_dir
        self._credential_source = credential_source
        self._max_retries = max_retries
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; the current scene finishes or aborts cleanly."""
        self._cancel.set()

    def run(self) -> None:
        try:
            summary = run_asf_download(
                self._scenes,
                self._output_dir,
                credential_source=self._credential_source,
                max_retries=self._max_retries,
                progress=self.scene_done.emit,
                cancel_event=self._cancel,
            )
        except InsarPrepError as exc:
            # Covers CredentialError (no/invalid credentials) and "nothing to
            # download"; the coded message is already credential-safe.
            self.run_failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never let a worker thread die silently
            self.run_failed.emit(mask_text(f"{type(exc).__name__}: {exc}"))
            return
        self.run_finished.emit(summary)


class DownloadPanel(QGroupBox):
    """Plan (dry-run) or download (real) the current Region's Sentinel-1 SLCs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ASF SLC Download", parent)
        self.setObjectName("download_panel")

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("download_output_dir")
        self.output_dir_edit.setPlaceholderText("Output root (SLCs go under <root>/02_slc)")
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setObjectName("download_browse_button")
        self.browse_button.clicked.connect(self._on_browse)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(self.browse_button)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("download_mode_combo")
        for value, label in _MODE_LABELS:
            self.mode_combo.addItem(label, value)

        self.credential_source_combo = QComboBox()
        self.credential_source_combo.setObjectName("download_credential_source_combo")
        for source in CredentialSource:
            self.credential_source_combo.addItem(source.value, source.value)

        self.credential_status_label = QLabel("Earthdata credential: unknown")
        self.credential_status_label.setObjectName("download_credential_status")
        self.credential_status_label.setWordWrap(True)
        self.login_button = QPushButton("Earthdata Login…")
        self.login_button.setObjectName("download_login_button")
        credential_row = QHBoxLayout()
        credential_row.addWidget(self.credential_status_label, 1)
        credential_row.addWidget(self.login_button)

        self.download_button = QPushButton("Run")
        self.download_button.setObjectName("download_run_button")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("download_cancel_button")
        self.cancel_button.setEnabled(False)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.download_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("download_progress")
        self.progress_bar.setVisible(False)

        self.result_label = QLabel("Download: not started")
        self.result_label.setObjectName("download_result")
        self.result_label.setWordWrap(True)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("download_log")
        self.log_view.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Output root:", output_row)
        form.addRow("Mode:", self.mode_combo)
        form.addRow("Credentials:", self.credential_source_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(credential_row)
        layout.addLayout(button_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.result_label)
        layout.addWidget(self.log_view)

        self.refresh_credential_status()

    # --- inputs ---------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Re-apply translatable text for the active language."""
        self.setTitle(i18n.tr("download.title"))
        self.browse_button.setText(i18n.tr("common.browse"))
        self.login_button.setText(i18n.tr("download.login"))
        self.download_button.setText(i18n.tr("common.run"))
        self.cancel_button.setText(i18n.tr("common.cancel"))

    def output_dir(self) -> str:
        """Return the entered output root (stripped)."""
        return self.output_dir_edit.text().strip()

    def selected_mode(self) -> str:
        """Return the selected mode value (``"dry-run"`` or ``"real"``)."""
        return str(self.mode_combo.currentData())

    def selected_credential_source(self) -> CredentialSource:
        """Return the selected credential source."""
        return CredentialSource(str(self.credential_source_combo.currentData()))

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select output root")
        if chosen:
            self.output_dir_edit.setText(chosen)

    # --- offline dry-run ------------------------------------------------------

    def plan_only(self, scenes: list[Scene], output_dir: Path | str) -> AsfDownloadPlan:
        """Build and write the offline dry-run plan (no network); show a summary."""
        unique_scenes, _duplicates = deduplicate_scenes(list(scenes))
        plan = build_asf_download_plan(scenes=unique_scenes, output_dir=output_dir)
        json_path, csv_path = write_asf_download_plan(plan, output_dir)
        self.result_label.setText(
            f"Dry-run plan: {plan.planned_count} planned, "
            f"{plan.missing_url_count} missing URL (no files downloaded)"
        )
        self.log_view.setPlainText(f"Plan JSON: {json_path}\nPlan CSV: {csv_path}")
        return plan

    # --- credential status ----------------------------------------------------

    def refresh_credential_status(self) -> None:
        """Show the stored credential type (token / login:<user> / none), no secret."""
        try:
            status = stored_credential_status()
        except CredentialError as exc:
            self.credential_status_label.setText(str(exc))
            return
        self.credential_status_label.setText(f"Earthdata credential: {status}")

    def credential_status_text(self) -> str:
        return self.credential_status_label.text()

    # --- run lifecycle (driven by the worker, all on the GUI thread) ----------

    def begin_run(self, total: int) -> None:
        """Prepare the panel for a real run of ``total`` scenes."""
        self.set_running(True)
        self.progress_bar.setRange(0, max(0, total))
        self.progress_bar.setValue(0)
        self.result_label.setText(f"Downloading {total} scene(s)…")
        self.log_view.clear()

    def set_running(self, running: bool) -> None:
        """Toggle the controls between idle and an in-progress download."""
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.browse_button.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.credential_source_combo.setEnabled(not running)
        self.output_dir_edit.setReadOnly(running)
        self.progress_bar.setVisible(running)

    def on_scene_done(self, result: DownloadResult) -> None:
        """Append one completed scene to the log and advance the progress bar."""
        suffix = f" [{result.error_code}]" if result.error_code else ""
        self.log_view.appendPlainText(
            f"{mask_text(result.scene_id)}: {result.outcome.value}"
            f" ({result.bytes_written} bytes){suffix}"
        )
        self.progress_bar.setValue(self.progress_bar.value() + 1)

    def set_download_summary(self, summary: DownloadRunSummary) -> None:
        """Show the final, credential-safe counts after a real run."""
        self.set_running(False)
        prefix = "Download cancelled" if summary.cancelled else "Download finished"
        self.result_label.setText(f"{prefix}: {summary.summary_line()}")
        if summary.results_path is not None:
            self.log_view.appendPlainText(f"Results: {summary.results_path}")

    def set_failed(self, message: str) -> None:
        """Show a credential-safe failure message and reset the controls."""
        self.set_running(False)
        self.result_label.setText(f"Download failed: {message}")
