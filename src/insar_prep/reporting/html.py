"""Offline single-file HTML data-preparation report (Task 031).

Renders a :class:`~insar_prep.reporting.types.DataPreparationReport` as a
self-contained, static HTML5 page for non-technical users to browse. Uses only
the Python standard library (``html.escape`` plus string building) -- no Jinja2,
Markdown, pandas, plotly, or any new dependency; no external CSS/JS/CDN; no
network; no PDF. The HTML mirrors the JSON/Markdown report (it never re-runs any
business logic); every user-controllable value is HTML-escaped, and the final
document is credential-masked via ``mask_text`` before it is written.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import ReportError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.naming import is_sarscape_safe_name
from insar_prep.reporting.types import DataPreparationReport, ReportSection

logger = get_logger("reporting.html")

HTML_FILENAME_SUFFIX = "_data_preparation_report.html"

# Minimal inline CSS (no external stylesheet/CDN). Keep every line <= 100 chars.
_CSS = """
:root { color-scheme: light dark; }
body { font-family: Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0;
       padding: 0 1.5rem 3rem; line-height: 1.5; color: #1b1b1b; background: #fafafa; }
header { padding: 1.5rem 0 1rem; border-bottom: 2px solid #ccc; }
h1 { margin: 0 0 .25rem; font-size: 1.5rem; }
.meta { color: #555; font-size: .9rem; }
.cards { display: flex; flex-wrap: wrap; gap: .75rem; margin: 1.25rem 0; }
.card { flex: 1 1 9rem; border: 1px solid #ddd; border-radius: 8px; padding: .75rem 1rem;
        background: #fff; }
.card .label { font-size: .75rem; text-transform: uppercase; color: #777; }
.card .value { font-size: 1.4rem; font-weight: 600; }
section { margin: 1.5rem 0; }
h2 { font-size: 1.15rem; border-bottom: 1px solid #e0e0e0; padding-bottom: .25rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0; background: #fff; }
th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top;
         font-size: .9rem; }
th { background: #f0f0f0; }
ul { margin: .5rem 0; padding-left: 1.25rem; }
.status { display: inline-block; padding: .1rem .5rem; border-radius: 4px; font-weight: 600;
          font-size: .8rem; }
.status-ready { background: #e3f5e3; color: #1d6b1d; }
.status-ready_with_warnings { background: #fdf3d8; color: #8a6d1a; }
.status-blocked { background: #fbe0e0; color: #a11111; }
.status-not_available { background: #ececec; color: #555; }
.sev-ERROR { color: #a11111; font-weight: 600; }
.sev-WARNING { color: #8a6d1a; font-weight: 600; }
.sev-INFO { color: #555; }
footer { margin-top: 2rem; color: #777; font-size: .8rem; }
"""


def html_report_path_for(report_dir: Path | str, region_safe_name: str) -> Path:
    """Return the HTML report path inside ``report_dir`` for a safe region name."""
    if not is_sarscape_safe_name(region_safe_name):
        raise ReportError(
            f"region_safe_name {region_safe_name!r} is not SARscape-safe",
            code=ErrorCode.REP001,
        )
    return Path(report_dir) / f"{region_safe_name}{HTML_FILENAME_SUFFIX}"


def _summary_cards(report: DataPreparationReport) -> str:
    summary = report.summary
    cards = [
        ("Overall status", summary.get("overall_status", "-")),
        ("Sections", summary.get("section_count", len(report.sections))),
        ("Errors", summary.get("error_count", 0)),
        ("Warnings", summary.get("warning_count", 0)),
    ]
    items = "".join(
        f'<div class="card"><div class="label">{escape(str(label))}</div>'
        f'<div class="value">{escape(str(value))}</div></div>'
        for label, value in cards
    )
    return f'<div class="cards">{items}</div>\n'


def _section_html(section: ReportSection) -> str:
    status = section.status.value
    parts = [
        "<section>\n",
        f"<h2>{escape(section.title)}</h2>\n",
        f'<p>Status: <span class="status status-{escape(status)}">{escape(status)}</span></p>\n',
    ]
    if section.items:
        lis = "".join(f"<li>{escape(item)}</li>" for item in section.items)
        parts.append(f"<ul>{lis}</ul>\n")
    if section.issues:
        rows = "".join(
            "<tr>"
            f'<td class="sev-{escape(issue.severity.value)}">{escape(issue.severity.value)}</td>'
            f"<td>{escape(issue.code)}</td>"
            f"<td>{escape(issue.message)}</td>"
            "</tr>"
            for issue in section.issues
        )
        parts.append(
            "<table><thead><tr><th>Severity</th><th>Code</th><th>Message</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>\n"
        )
    parts.append("</section>\n")
    return "".join(parts)


def render_report_html(report: DataPreparationReport) -> str:
    """Render a self-contained, static HTML5 view of a report."""
    title = report.title or "INSAR Prep Data Preparation Report"
    overall = str(report.summary.get("overall_status", "-"))
    head = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
    )
    header = (
        "<header>\n"
        f"<h1>{escape(title)}</h1>\n"
        '<div class="meta">'
        f"Project: {escape(report.project_id or '-')} &middot; "
        f"Region: {escape(report.region_safe_name)} ({escape(report.region_id)}) &middot; "
        f"Generated: {escape(report.created_at.isoformat())} &middot; "
        f"Overall status: {escape(overall)}"
        "</div>\n"
        "</header>\n"
    )
    sections = "".join(_section_html(section) for section in report.sections)
    footer = (
        "<footer>Static offline report generated by insar-prep. "
        "No network, scripts, or external resources are used.</footer>\n"
    )
    return head + header + _summary_cards(report) + sections + footer + "</body>\n</html>\n"


def save_report_html(report: DataPreparationReport, output_path: Path | str) -> Path:
    """Write the HTML report to ``output_path`` (UTF-8, credential-masked)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mask_text(render_report_html(report)), encoding="utf-8")
    logger.debug("saved HTML report to %s", path)
    return path
