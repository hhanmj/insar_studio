"""End-to-end tests for the ``download-dem`` and ``dem-auth`` CLIs.

Dry-run is the default and must be fully offline. The verify/real paths are
exercised only with a monkeypatched key resolver / downloader so no network or
real OpenTopography key is ever needed; the guard paths (missing AOI,
not-downloadable dataset) are also covered.
"""

from __future__ import annotations

import io
import socket
from pathlib import Path

import pytest

import insar_prep.cli.commands as commands
from insar_prep.cli.main import main
from insar_prep.providers.dem.credentials import DemKeySource, ResolvedDemKey
from insar_prep.providers.dem.downloader import DemDownloadOutcome, DemDownloadResult

_BBOX = ["--bbox", "110.1", "30.8", "110.6", "31.2"]
_FAKE_KEY = ResolvedDemKey(source=DemKeySource.ENV, api_key="FAKE_KEY_XYZ")


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_download_dem_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["download-dem", "--help"])
    assert exc.value.code == 0


def test_dry_run_is_offline_and_prints_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        ["download-dem", "--region-name", "Demo Area", "--output-root", str(tmp_path), *_BBOX]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "DEM request plan" in out
    assert "COP30" in out
    assert "Dry-run only" in out
    assert not list(tmp_path.rglob("*.tif"))


def test_missing_aoi_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["download-dem", "--region-name", "demo", "--output-root", str(tmp_path)])
    assert code == 2
    assert "AOI001" in capsys.readouterr().err


def test_user_local_real_not_downloadable_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        [
            "download-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--dem-dataset",
            "USER_LOCAL",
            "--download-mode",
            "real",
        ]
    )
    assert code == 2
    assert "DEM001" in capsys.readouterr().err


def test_real_path_uses_runner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _Summary:
        results_path = tmp_path / "dem_download" / "dem_download_results.csv"
        has_failures = False

        def summary_line(self) -> str:
            return "1 downloaded, 0 skipped, 0 failed, 0 interrupted"

    def _fake_resolve(source: DemKeySource) -> ResolvedDemKey:
        captured["source"] = source
        return _FAKE_KEY

    def _fake_run(plans, output_dir, **kwargs):  # noqa: ANN001, ANN003
        captured["plans"] = list(plans)
        return _Summary()

    monkeypatch.setattr(commands, "resolve_dem_api_key", _fake_resolve)
    monkeypatch.setattr(commands, "run_dem_download", _fake_run)

    code = main(
        [
            "download-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--download-mode",
            "real",
        ]
    )
    assert code == 0
    assert captured["source"] is DemKeySource.AUTO
    assert len(captured["plans"]) == 1
    assert "DEM download finished" in capsys.readouterr().out


def test_verify_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeDownloader:
        def __init__(self, **kwargs: object) -> None:
            pass

        def verify(self, request: object) -> DemDownloadResult:
            return DemDownloadResult(
                region_safe_name="demo",
                dataset="COP30",
                outcome=DemDownloadOutcome.VERIFIED,
                message="key valid and OpenTopography reachable",
            )

    monkeypatch.setattr(commands, "resolve_dem_api_key", lambda source: _FAKE_KEY)
    monkeypatch.setattr(commands, "RealDemDownloader", _FakeDownloader)

    code = main(
        [
            "download-dem",
            "--region-name",
            "demo",
            "--output-root",
            str(tmp_path),
            *_BBOX,
            "--download-mode",
            "verify",
        ]
    )
    assert code == 0
    assert "verified" in capsys.readouterr().out


def test_dem_auth_status(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commands, "stored_api_key_status", lambda: "none")
    code = main(["dem-auth", "status"])
    assert code == 0
    assert "none" in capsys.readouterr().out


def test_dem_auth_login_stdin(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    stored: dict[str, str] = {}
    monkeypatch.setattr(commands, "store_api_key", lambda key: stored.update(key=key))
    monkeypatch.setattr("sys.stdin", io.StringIO("FAKE_KEY_FROM_STDIN\n"))
    code = main(["dem-auth", "login", "--key-stdin"])
    assert code == 0
    assert stored["key"] == "FAKE_KEY_FROM_STDIN"
    assert "Stored OpenTopography API key" in capsys.readouterr().out
