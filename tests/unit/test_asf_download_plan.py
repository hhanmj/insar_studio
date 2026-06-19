"""Tests for the offline ASF download dry-run planner (Task 033)."""

from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

from insar_prep.providers.asf.download_plan import (
    ASF_PLAN_COLUMNS,
    AsfPlanStatus,
    asf_download_plan_paths,
    build_asf_download_plan,
    write_asf_download_plan,
)
from insar_prep.providers.asf.scene_parser import parse_scene_name

_GRANULE = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
_URL = f"https://datapool.asf.alaska.edu/SLC/SA/{_GRANULE}.zip"
# A URL carrying credential-like query params; these must never reach the plan.
_URL_WITH_TOKEN = f"{_URL}?token=SECRETTOKEN123&password=HUNTER2"


def _ban_network(monkeypatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in the offline planner")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_scene_with_url_is_planned(tmp_path: Path) -> None:
    plan = build_asf_download_plan(scenes=[parse_scene_name(_URL)], output_dir=tmp_path)
    assert plan.scene_count == 1
    assert plan.planned_count == 1
    assert plan.missing_url_count == 0
    item = plan.items[0]
    assert item.status is AsfPlanStatus.PLANNED
    assert item.url_status == "present"
    assert item.credential_required is True


def test_scene_without_url_is_missing_url(tmp_path: Path) -> None:
    plan = build_asf_download_plan(scenes=[parse_scene_name(_GRANULE)], output_dir=tmp_path)
    item = plan.items[0]
    assert item.status is AsfPlanStatus.MISSING_URL
    assert item.url_status == "missing"
    assert plan.missing_url_count == 1


def test_expected_filename_and_planned_path(tmp_path: Path) -> None:
    plan = build_asf_download_plan(scenes=[parse_scene_name(_URL)], output_dir=tmp_path)
    item = plan.items[0]
    assert item.expected_filename == f"{_GRANULE}.zip"
    assert item.planned_path == str(tmp_path / "02_slc" / f"{_GRANULE}.zip")


def test_url_token_and_query_never_reach_plan(tmp_path: Path) -> None:
    plan = build_asf_download_plan(
        scenes=[parse_scene_name(_URL_WITH_TOKEN)],
        output_dir=tmp_path,
        source_cart="cart.txt",
    )
    item = plan.items[0]
    assert item.expected_filename == f"{_GRANULE}.zip"
    assert "SECRETTOKEN123" not in item.planned_path
    assert "SECRETTOKEN123" not in item.notes
    assert "token=" not in item.expected_filename
    json_path, csv_path = write_asf_download_plan(plan, tmp_path)
    json_text = json_path.read_text(encoding="utf-8")
    csv_text = csv_path.read_text(encoding="utf-8")
    for secret in ("SECRETTOKEN123", "HUNTER2", "token=", "password="):
        assert secret not in json_text
        assert secret not in csv_text


def test_write_plan_csv_round_trip(tmp_path: Path) -> None:
    plan = build_asf_download_plan(scenes=[parse_scene_name(_URL)], output_dir=tmp_path)
    _json_path, csv_path = write_asf_download_plan(plan, tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ASF_PLAN_COLUMNS
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["scene_id"] == _GRANULE
    assert rows[0]["status"] == "PLANNED"
    assert rows[0]["credential_required"] == "yes"
    assert rows[0]["expected_filename"] == f"{_GRANULE}.zip"


def test_write_plan_json_round_trip(tmp_path: Path) -> None:
    plan = build_asf_download_plan(
        scenes=[parse_scene_name(_URL)], output_dir=tmp_path, region_safe_name="demo"
    )
    json_path, _csv_path = write_asf_download_plan(plan, tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["scene_count"] == 1
    assert data["planned_count"] == 1
    assert data["missing_url_count"] == 0
    assert data["credential_required"] is True
    assert data["region_safe_name"] == "demo"
    assert data["items"][0]["scene_id"] == _GRANULE
    assert data["items"][0]["status"] == "PLANNED"


def test_plan_paths_live_under_plan_subdir(tmp_path: Path) -> None:
    json_path, csv_path = asf_download_plan_paths(tmp_path)
    assert json_path == tmp_path / "asf_download_plan" / "asf_download_plan.json"
    assert csv_path == tmp_path / "asf_download_plan" / "asf_download_plan.csv"


def test_planner_does_not_touch_network(tmp_path: Path, monkeypatch) -> None:
    _ban_network(monkeypatch)
    plan = build_asf_download_plan(scenes=[parse_scene_name(_URL)], output_dir=tmp_path)
    # Building and writing the plan must not open any socket.
    write_asf_download_plan(plan, tmp_path)


def test_planner_creates_no_slc_dir_or_large_files(tmp_path: Path) -> None:
    plan = build_asf_download_plan(scenes=[parse_scene_name(_URL)], output_dir=tmp_path)
    write_asf_download_plan(plan, tmp_path)
    assert not (tmp_path / "02_slc").exists()
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.SAFE"))
