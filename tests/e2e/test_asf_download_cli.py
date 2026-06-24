"""End-to-end tests for the ``download-asf`` CLI.

Dry-run is the default and must be fully offline. The real path is exercised only
with a monkeypatched downloader/credentials so no network or real account is ever
needed; the guard paths (missing extra / missing credentials) are also covered.
"""

from __future__ import annotations

import csv
import importlib.util
import socket
from pathlib import Path

import pytest

import insar_prep.cli.commands as commands
from insar_prep.cli.main import main
from insar_prep.providers.asf.credentials import CredentialSource, ResolvedCredential
from insar_prep.providers.asf.downloader import DownloadOutcome, DownloadResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asf"
URLS_CART = FIXTURES / "urls.txt"
CSV_CART = FIXTURES / "scenes.csv"


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_download_asf_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["download-asf", "--help"])
    assert exc.value.code == 0


def test_download_asf_dry_run_is_offline_and_writes_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(["download-asf", "--cart", str(URLS_CART), "--output-dir", str(out_dir)])
    assert code == 0
    assert (out_dir / "asf_download_plan" / "asf_download_plan.json").exists()
    assert (out_dir / "asf_download_plan" / "asf_download_plan.csv").exists()
    out = capsys.readouterr().out
    assert "Dry-run only" in out
    # Nothing downloaded; no SLC archive or 02_slc directory created.
    assert not list(tmp_path.rglob("*.zip"))
    assert not (out_dir / "02_slc").exists()


def test_download_asf_dry_run_require_urls_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(
        [
            "download-asf",
            "--cart",
            str(CSV_CART),
            "--output-dir",
            str(out_dir),
            "--require-urls",
        ]
    )
    assert code == 2
    assert (out_dir / "asf_download_plan" / "asf_download_plan.json").exists()


def test_download_asf_real_missing_credentials_is_offline_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    out_dir = tmp_path / "out"
    code = main(
        [
            "download-asf",
            "--cart",
            str(URLS_CART),
            "--output-dir",
            str(out_dir),
            "--download-mode",
            "real",
            "--credential-source",
            "env-token",
        ]
    )
    # Fails cleanly (missing extra or missing token) without any network access.
    assert code != 0
    assert not list(tmp_path.rglob("*.zip"))


def test_download_asf_real_happy_path_monkeypatched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name == "requests" else real_find_spec(name, *a, **k),
    )
    monkeypatch.setattr(
        commands,
        "resolve_credentials",
        lambda source: ResolvedCredential(source=source, use_netrc=True),
    )

    class _FakeDownloader:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def download(self, request: object) -> DownloadResult:
            dest = request.destination  # type: ignore[attr-defined]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-slc")
            return DownloadResult(
                scene_id=request.scene_id,  # type: ignore[attr-defined]
                outcome=DownloadOutcome.SUCCESS,
                path=dest,
                bytes_written=8,
                message="downloaded",
            )

    monkeypatch.setattr(commands, "RealAsfDownloader", _FakeDownloader)

    out_dir = tmp_path / "out"
    code = main(
        [
            "download-asf",
            "--cart",
            str(URLS_CART),
            "--output-dir",
            str(out_dir),
            "--download-mode",
            "real",
            "--credential-source",
            "netrc",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "ASF download finished:" in out
    results_csv = out_dir / "asf_download_plan" / "asf_download_results.csv"
    assert results_csv.exists()
    with results_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["outcome"] == "success" for row in rows)
    # The fake wrote the SLCs under 02_slc/.
    assert list((out_dir / "02_slc").glob("*.zip"))


def test_download_asf_verify_happy_path_monkeypatched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name == "requests" else real_find_spec(name, *a, **k),
    )
    monkeypatch.setattr(
        commands,
        "resolve_credentials",
        lambda source: ResolvedCredential(source=source, use_netrc=True),
    )

    class _FakeDownloader:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def verify(self, request: object) -> DownloadResult:
            return DownloadResult(
                scene_id=request.scene_id,  # type: ignore[attr-defined]
                outcome=DownloadOutcome.VERIFIED,
                bytes_written=64,
                message="reachable and authenticated; remote size 4000000000 bytes",
            )

    monkeypatch.setattr(commands, "RealAsfDownloader", _FakeDownloader)

    out_dir = tmp_path / "out"
    code = main(
        [
            "download-asf",
            "--cart",
            str(URLS_CART),
            "--output-dir",
            str(out_dir),
            "--download-mode",
            "verify",
            "--credential-source",
            "netrc",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "ASF network verify finished:" in out
    assert "verified" in out
    # verify never writes an SLC archive.
    assert not list(tmp_path.rglob("*.zip"))
    results_csv = out_dir / "asf_download_plan" / "asf_download_results.csv"
    assert results_csv.exists()


def test_download_asf_verify_missing_credentials_is_offline_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    out_dir = tmp_path / "out"
    code = main(
        [
            "download-asf",
            "--cart",
            str(URLS_CART),
            "--output-dir",
            str(out_dir),
            "--download-mode",
            "verify",
            "--credential-source",
            "env-token",
        ]
    )
    assert code != 0
    assert not list(tmp_path.rglob("*.zip"))


def test_credential_source_choices_cover_all_sources() -> None:
    # Guard: all supported sources are exposed on the CLI choices.
    assert {member.value for member in CredentialSource} == {
        "auto",
        "keyring",
        "netrc",
        "env-token",
    }
