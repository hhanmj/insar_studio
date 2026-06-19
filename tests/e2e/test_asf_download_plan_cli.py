"""End-to-end tests for the offline ``plan-asf-downloads`` CLI (Task 033)."""

from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

import pytest

from insar_prep.cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asf"
URLS_CART = FIXTURES / "urls.txt"
CSV_CART = FIXTURES / "scenes.csv"

_EXPECTED_HEADER = (
    "scene_id,platform,acquisition_datetime,product,beam,polarization,"
    "url_status,expected_filename,planned_path,status,credential_required,notes"
)


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in the offline planner")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_plan_asf_downloads_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["plan-asf-downloads", "--help"])
    assert exc.value.code == 0


def test_plan_asf_downloads_writes_json_and_csv(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(["plan-asf-downloads", "--cart", str(URLS_CART), "--output-dir", str(out_dir)])
    assert code == 0

    json_path = out_dir / "asf_download_plan" / "asf_download_plan.json"
    csv_path = out_dir / "asf_download_plan" / "asf_download_plan.csv"
    assert json_path.exists()
    assert csv_path.exists()

    out = capsys.readouterr().out
    assert "ASF download plan written:" in out
    assert "JSON:" in out
    assert str(json_path) in out
    assert "CSV:" in out
    assert str(csv_path) in out

    with csv_path.open(encoding="utf-8", newline="") as handle:
        assert handle.readline().strip() == _EXPECTED_HEADER
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2  # urls.txt lists two scenes
    assert all(row["status"] == "PLANNED" for row in rows)
    assert all(row["credential_required"] == "yes" for row in rows)
    assert all(row["expected_filename"].endswith(".zip") for row in rows)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["scene_count"] == 2
    assert data["planned_count"] == 2
    assert data["missing_url_count"] == 0


def test_plan_asf_downloads_no_large_files_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(["plan-asf-downloads", "--cart", str(URLS_CART), "--output-dir", str(out_dir)])
    assert code == 0
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.SAFE"))
    assert not list(tmp_path.rglob("*.tif"))
    # The planner records the intended 02_slc path but never creates it.
    assert not (out_dir / "02_slc").exists()


def test_plan_asf_downloads_missing_url_is_ok_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(["plan-asf-downloads", "--cart", str(CSV_CART), "--output-dir", str(out_dir)])
    assert code == 0
    csv_path = out_dir / "asf_download_plan" / "asf_download_plan.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    statuses = {row["status"] for row in rows}
    assert "MISSING_URL" in statuses


def test_plan_asf_downloads_require_urls_exits_two_but_writes_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    out_dir = tmp_path / "out"
    code = main(
        [
            "plan-asf-downloads",
            "--cart",
            str(CSV_CART),
            "--output-dir",
            str(out_dir),
            "--require-urls",
        ]
    )
    assert code == 2
    # The plan is still produced so the user can see which scenes lack a URL.
    assert (out_dir / "asf_download_plan" / "asf_download_plan.json").exists()
    assert (out_dir / "asf_download_plan" / "asf_download_plan.csv").exists()


def test_plan_asf_downloads_missing_cart_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    code = main(
        [
            "plan-asf-downloads",
            "--cart",
            str(tmp_path / "nope.txt"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code != 0
