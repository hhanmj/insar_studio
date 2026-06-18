"""End-to-end regression for the offline ``insar-prep prepare`` workflow (Task 020).

Drives the full offline pipeline through the public CLI with *every* optional
module enabled at once (orbit matching, DEM planning + conversion, GACOS request
planning, GACOS import check) against the ASF cart fixture plus dynamically
created orbit/GACOS inputs, and asserts the JSON + Markdown report is produced
without any network access, without real DEM ``.tif`` files, and without moving,
deleting, or modifying the user's GACOS products.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from insar_prep.cli.main import main
from insar_prep.core.naming import sarscape_safe_name

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
URLS_CART = FIXTURES / "asf" / "urls.txt"

# EOF validity windows cover the two urls.txt scenes (S1A 2024-01-01,
# S1B 2024-01-13); the orbit matcher reads filenames only, never contents.
_MATCHING_ORBIT_NAMES = (
    "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T000000.EOF",
    "S1B_OPER_AUX_POEORB_OPOD_20240114T120000_V20240113T000000_20240114T000000.EOF",
)
# GACOS acquisition dates expected from the two scenes.
_GACOS_DATES = ("20240101", "20240113")

_EXPECTED_SECTIONS = (
    "Scene consistency",
    "Orbit matching",
    "DEM planning",
    "DEM conversion",
    "GACOS request planning",
    "GACOS import check",
)


def _make_orbit_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in _MATCHING_ORBIT_NAMES:
        (root / name).write_text("placeholder; contents are never parsed\n", encoding="utf-8")
    return root


def _make_gacos_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for stamp in _GACOS_DATES:
        (root / f"{stamp}.ztd").write_text("ztd\n", encoding="utf-8")
        (root / f"{stamp}.ztd.rsc").write_text("WIDTH 10\n", encoding="utf-8")
    return root


def _snapshot(directory: Path) -> dict[str, int]:
    return {entry.name: entry.stat().st_size for entry in sorted(directory.iterdir())}


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any socket creation fail so the workflow is proven offline."""

    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in the offline workflow")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_full_offline_prepare_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = "shiliushubao_demo"
    workspace = tmp_path / "workspace"
    orbit_dir = _make_orbit_dir(tmp_path / "orbits")
    gacos_dir = _make_gacos_dir(tmp_path / "gacos_products")
    gacos_before = _snapshot(gacos_dir)

    _ban_network(monkeypatch)
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            region,
            "--output-root",
            str(workspace),
            "--orbit-dir",
            str(orbit_dir),
            "--dem-plan",
            "--bbox",
            "110.1",
            "30.8",
            "110.6",
            "31.2",
            "--gacos-plan",
            "--gacos-import-dir",
            str(gacos_dir),
        ]
    )
    assert code == 0

    safe = sarscape_safe_name(region)
    reports = workspace / safe / "07_reports"
    json_path = reports / f"{safe}_data_preparation_report.json"
    md_path = reports / f"{safe}_data_preparation_report.md"
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.parent.name == "07_reports"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    sections = {section["title"]: section for section in data["sections"]}
    for expected in _EXPECTED_SECTIONS:
        assert expected in sections

    markdown = md_path.read_text(encoding="utf-8")
    for expected in _EXPECTED_SECTIONS:
        assert f"## {expected}" in markdown

    # Orbit matching and GACOS import both reach a "ready" state with these inputs.
    assert sections["Orbit matching"]["summary"]["matched"] == 2
    gacos_import = sections["GACOS import check"]
    assert gacos_import["summary"]["missing_date_count"] == 0
    assert "GACOS_IMPORT_READY" in " ".join(issue["code"] for issue in gacos_import["issues"])

    # Planning only: no real DEM raster is ever produced.
    assert not list(tmp_path.rglob("*.tif"))
    # GACOS products are never moved, deleted, or modified (read-only import check).
    assert _snapshot(gacos_dir) == gacos_before
    assert all((gacos_dir / name).exists() for name in gacos_before)
    # Neither the SARscape-ready DEM tree nor the GACOS requests tree is created.
    assert not (workspace / safe / "05_atmosphere").exists()
    assert not (workspace / safe / "06_sarscape_ready").exists()

    # The CLI prints both report paths on success.
    out = capsys.readouterr().out
    assert str(json_path) in out
    assert str(md_path) in out


def test_prepare_workflow_handles_output_root_with_spaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Windows-style output root containing spaces must work end to end."""
    region = "shiliushubao_demo"
    workspace = tmp_path / "My Work" / "work space"

    _ban_network(monkeypatch)
    code = main(
        [
            "prepare",
            "--cart",
            str(URLS_CART),
            "--region-name",
            region,
            "--output-root",
            str(workspace),
        ]
    )
    assert code == 0

    safe = sarscape_safe_name(region)
    reports = workspace / safe / "07_reports"
    assert (reports / f"{safe}_data_preparation_report.json").exists()
    assert (reports / f"{safe}_data_preparation_report.md").exists()
    # The space stays in the user-chosen output root, never in the safe names.
    assert " " in str(workspace)
    assert " " not in safe
