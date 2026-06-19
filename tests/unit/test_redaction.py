"""Credential redaction hardening tests (Task 034).

Only fake secrets are used -- nothing real, nothing read from the environment,
and no network. These prove that strengthened ``mask_text`` keeps credentials
out of logs, reports (JSON/Markdown/HTML), and CSVs (manifest/warnings).
"""

from __future__ import annotations

from pathlib import Path

from insar_prep.core.logging import mask_secret, mask_text
from insar_prep.quality.types import CheckSeverity
from insar_prep.reporting.generator import save_report
from insar_prep.reporting.html import save_report_html
from insar_prep.reporting.manifest import ManifestRow, write_manifest_csv
from insar_prep.reporting.types import (
    DataPreparationReport,
    ReportIssue,
    ReportSection,
    ReportStatus,
)
from insar_prep.reporting.warnings import WarningRow, write_warnings_csv

# Fake secrets only (never real credentials, never from the environment).
FAKE_PASSWORD = "FAKE_PASSWORD_123456"
FAKE_TOKEN = "FAKE_TOKEN_ABCDEF7890"
FAKE_COOKIE = "FAKE_COOKIE_VALUE_9988"
FAKE_SIGNATURE = "FAKEAMZSIGNATUREZZZZ1234"
FAKE_SESSION_TOKEN = "FAKESESSIONTOKEN0001"
_ALL_FAKE = (
    FAKE_PASSWORD,
    FAKE_TOKEN,
    FAKE_COOKIE,
    FAKE_SIGNATURE,
    FAKE_SESSION_TOKEN,
)


def test_mask_secret_keeps_last_four() -> None:
    assert mask_secret("abcdef123456") == "****3456"
    assert mask_secret("abcd") == "****"
    assert mask_secret("") == "****"


def test_mask_text_keyed_forms() -> None:
    samples = (
        f"password: {FAKE_PASSWORD}",
        f"password={FAKE_PASSWORD}",
        f'"password": "{FAKE_PASSWORD}"',
        f"token={FAKE_TOKEN}",
        f"api_key={FAKE_TOKEN}",
        f"api-key: {FAKE_TOKEN}",
        f"secret={FAKE_PASSWORD}",
        f"session={FAKE_TOKEN}",
        f"sessionid={FAKE_TOKEN}",
    )
    for text in samples:
        masked = mask_text(text)
        assert FAKE_PASSWORD not in masked
        assert FAKE_TOKEN not in masked


def test_mask_text_url_query_token_and_password() -> None:
    url = f"https://datapool.asf.alaska.edu/SLC/x.zip?token={FAKE_TOKEN}&password={FAKE_PASSWORD}"
    masked = mask_text(url)
    assert FAKE_TOKEN not in masked
    assert FAKE_PASSWORD not in masked


def test_mask_text_presigned_s3_query() -> None:
    url = (
        "https://example.s3.amazonaws.com/x.zip?"
        f"X-Amz-Credential=AKIAFAKE/20240101/us-east-1&X-Amz-Signature={FAKE_SIGNATURE}"
        f"&X-Amz-Security-Token={FAKE_SESSION_TOKEN}"
    )
    masked = mask_text(url)
    assert FAKE_SIGNATURE not in masked
    assert FAKE_SESSION_TOKEN not in masked


def test_mask_text_authorization_header_preserves_scheme() -> None:
    masked = mask_text(f"Authorization: Bearer {FAKE_TOKEN}")
    assert FAKE_TOKEN not in masked
    assert "Bearer" in masked
    masked_basic = mask_text("Authorization: Basic ZmFrZXVzZXI6ZmFrZXBhc3M=")
    assert "ZmFrZXVzZXI6ZmFrZXBhc3M=" not in masked_basic


def test_mask_text_bare_bearer_token() -> None:
    masked = mask_text(f"GET /file sent header Bearer {FAKE_TOKEN} to host")
    assert FAKE_TOKEN not in masked


def test_mask_text_cookie_header() -> None:
    masked = mask_text(f"Cookie: sessionid={FAKE_COOKIE}; csrftoken=FAKECSRFVALUE123")
    assert FAKE_COOKIE not in masked
    assert "FAKECSRFVALUE123" not in masked


def test_mask_text_preserves_windows_paths() -> None:
    # No keyword is followed by a ':'/'=' separator, so paths stay intact even
    # when a directory name happens to contain 'tokens' or 'sessions'.
    paths = (
        r"C:\Users\insar\AppData\Local\Temp\out\02_slc\S1A_IW_SLC__1SDV_20240101.zip",
        r"D:\data\sessions\tokens\readme.txt",
        r"C:\Program Files\insar_prep\report.html",
    )
    for path in paths:
        assert mask_text(path) == path


def test_mask_text_preserves_non_secret_text() -> None:
    text = "Scene consistency: 2 scenes valid, 0 errors; overall status ready"
    assert mask_text(text) == text


def _report_with_secrets() -> DataPreparationReport:
    section = ReportSection(
        title="Scene consistency",
        status=ReportStatus.READY_WITH_WARNINGS,
        items=[f"diagnostic token={FAKE_TOKEN}", f"note password={FAKE_PASSWORD}"],
        issues=[
            ReportIssue(
                section="Scene consistency",
                code="DIAG",
                severity=CheckSeverity.WARNING,
                message=f"request used Authorization: Bearer {FAKE_TOKEN}",
            )
        ],
    )
    return DataPreparationReport(
        region_id="region_demo",
        region_safe_name="demo",
        title="redaction demo",
        sections=[section],
        summary={
            "overall_status": "ready_with_warnings",
            "section_count": 1,
            "error_count": 0,
            "warning_count": 1,
        },
    )


def test_report_json_and_markdown_are_masked(tmp_path: Path) -> None:
    output = save_report(_report_with_secrets(), tmp_path)
    json_text = output.json_path.read_text(encoding="utf-8")
    md_text = output.markdown_path.read_text(encoding="utf-8")
    for secret in (FAKE_TOKEN, FAKE_PASSWORD):
        assert secret not in json_text
        assert secret not in md_text


def test_report_html_is_masked(tmp_path: Path) -> None:
    html_path = tmp_path / "demo_data_preparation_report.html"
    save_report_html(_report_with_secrets(), html_path)
    html_text = html_path.read_text(encoding="utf-8")
    for secret in (FAKE_TOKEN, FAKE_PASSWORD):
        assert secret not in html_text


def test_manifest_csv_is_masked(tmp_path: Path) -> None:
    row = ManifestRow(
        section="scene",
        item_type="scene",
        item_id="S1A_demo",
        notes=f"token={FAKE_TOKEN}; password={FAKE_PASSWORD}",
    )
    path = write_manifest_csv(tmp_path / "demo_manifest.csv", [row])
    text = path.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in text
    assert FAKE_PASSWORD not in text


def test_warnings_csv_is_masked(tmp_path: Path) -> None:
    row = WarningRow(
        severity="ERROR",
        section="scene",
        item_type="scene",
        code="DIAG",
        message=f"leaked api_key={FAKE_TOKEN}",
        action=f"rotate password={FAKE_PASSWORD}",
    )
    path = write_warnings_csv(tmp_path / "demo_warnings.csv", [row])
    text = path.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in text
    assert FAKE_PASSWORD not in text


def test_no_real_secret_constants_present() -> None:
    # Guard: the fixtures used here are obviously fake.
    for secret in _ALL_FAKE:
        assert secret.startswith("FAKE")
