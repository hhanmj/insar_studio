"""Offline data-preparation reporting (Task 014).

A format-agnostic report backend that consolidates module outcomes into a
structured `DataPreparationReport`, renders Markdown, and writes UTF-8 JSON +
Markdown to a SARscape-safe `07_reports` directory. No GUI, PDF, HTML, browser,
network, or external services; written text is credential-masked.
"""

from __future__ import annotations

from insar_prep.reporting.generator import (
    REPORTS_SUBDIR,
    build_data_preparation_report,
    render_report_markdown,
    save_report,
)
from insar_prep.reporting.manifest import (
    MANIFEST_COLUMNS,
    MANIFEST_FILENAME_SUFFIX,
    ManifestRow,
    build_manifest_rows,
    manifest_path_for,
    write_manifest_csv,
)
from insar_prep.reporting.types import (
    DataPreparationReport,
    ReportIssue,
    ReportOutput,
    ReportSection,
    ReportStatus,
)

__all__ = [
    "MANIFEST_COLUMNS",
    "MANIFEST_FILENAME_SUFFIX",
    "REPORTS_SUBDIR",
    "DataPreparationReport",
    "ManifestRow",
    "ReportIssue",
    "ReportOutput",
    "ReportSection",
    "ReportStatus",
    "build_data_preparation_report",
    "build_manifest_rows",
    "manifest_path_for",
    "render_report_markdown",
    "save_report",
    "write_manifest_csv",
]
