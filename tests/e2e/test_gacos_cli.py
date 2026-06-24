"""End-to-end tests for the GACOS request/download/auth CLI.

Dry-run is fully offline (sockets banned). The ``--submit`` and ``gacos-download``
network paths are exercised with the orchestration monkeypatched so no real GACOS
request is ever made.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

import insar_prep.cli.commands as commands
from insar_prep.cli.main import main
from insar_prep.providers.gacos.download_runner import (
    GacosDownloadRunSummary,
    GacosRequestRunSummary,
)
from insar_prep.providers.gacos.downloader import (
    GacosFetchOutcome,
    GacosFetchResult,
    GacosSubmitOutcome,
    GacosSubmitResult,
)


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_help_exits_zero() -> None:
    for command in ("gacos-request", "gacos-download", "gacos-auth"):
        with pytest.raises(SystemExit) as exc:
            main([command, "--help"])
        assert exc.value.code == 0


def test_request_dry_run_is_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        [
            "gacos-request",
            "--region-name",
            "Demo Area",
            "--output-root",
            str(tmp_path),
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            "--dates",
            "20240101,20240113",
            "--time",
            "18:30",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "GACOS request:" in out
    assert "Dry-run only" in out
    assert "UTC 18:30" in out


def test_request_submit_uses_orchestration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return GacosRequestRunSummary(
            results=[
                GacosSubmitResult(outcome=GacosSubmitOutcome.SUBMITTED, date_count=2, message="ok")
            ],
            results_path=tmp_path / "gacos_request" / "gacos_request_results.csv",
            counts={GacosSubmitOutcome.SUBMITTED: 1, GacosSubmitOutcome.FAILED: 0},
        )

    monkeypatch.setattr(commands, "_run_gacos_request", _fake_run)
    code = main(
        [
            "gacos-request",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            "--dates",
            "20240101",
            "--submit",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "GACOS request finished" in out
    assert "Watch your email" in out
    assert captured["dates"]  # the orchestration was called with the parsed dates


def test_download_uses_orchestration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_run(urls, output_directory, **kwargs):
        assert urls == ["http://www.gacos.net/data/demo.zip"]
        return GacosDownloadRunSummary(
            fetch_results=[GacosFetchResult(outcome=GacosFetchOutcome.SUCCESS, bytes_written=10)],
            import_result=None,
            results_path=Path(output_directory) / "gacos_request" / "gacos_download_results.csv",
            counts={GacosFetchOutcome.SUCCESS: 1},
        )

    monkeypatch.setattr(commands, "_run_gacos_download", _fake_run)
    code = main(
        [
            "gacos-download",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            "--url",
            "http://www.gacos.net/data/demo.zip",
        ]
    )
    assert code == 0
    assert "GACOS download finished" in capsys.readouterr().out


def test_auth_status_offline(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.setattr(commands, "stored_gacos_email_status", lambda: "none")
    code = main(["gacos-auth", "status"])
    assert code == 0
    assert "Stored GACOS email: none" in capsys.readouterr().out
