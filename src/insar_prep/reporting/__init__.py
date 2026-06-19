"""Offline data-preparation reporting (Task 014; static HTML added in Task 031).

A format-agnostic report backend that consolidates module outcomes into a
structured `DataPreparationReport`, renders Markdown plus a self-contained static
HTML page, and writes UTF-8 JSON + Markdown + HTML to a SARscape-safe
`07_reports` directory. No GUI, PDF, browser, network, or external services (the
HTML is a single static file with inline CSS and no CDN); written text is
credential-masked.
"""

from __future__ import annotations

from insar_prep.reporting.generator import (
    REPORTS_SUBDIR,
    build_data_preparation_report,
    render_report_markdown,
    save_report,
)
from insar_prep.reporting.html import (
    HTML_FILENAME_SUFFIX,
    html_report_path_for,
    render_report_html,
    save_report_html,
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
from insar_prep.reporting.warnings import (
    WARNINGS_COLUMNS,
    WARNINGS_FILENAME_SUFFIX,
    WarningRow,
    build_warning_rows,
    warnings_path_for,
    write_warnings_csv,
)

__all__ = [
    "HTML_FILENAME_SUFFIX",
    "MANIFEST_COLUMNS",
    "MANIFEST_FILENAME_SUFFIX",
    "REPORTS_SUBDIR",
    "WARNINGS_COLUMNS",
    "WARNINGS_FILENAME_SUFFIX",
    "DataPreparationReport",
    "ManifestRow",
    "ReportIssue",
    "ReportOutput",
    "ReportSection",
    "ReportStatus",
    "WarningRow",
    "build_data_preparation_report",
    "build_manifest_rows",
    "build_warning_rows",
    "html_report_path_for",
    "manifest_path_for",
    "render_report_html",
    "render_report_markdown",
    "save_report",
    "save_report_html",
    "warnings_path_for",
    "write_manifest_csv",
    "write_warnings_csv",
]
