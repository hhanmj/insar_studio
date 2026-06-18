"""Tests for the PyInstaller entry script (Task 022).

The entry file is loaded by path (not imported as ``packaging.insar_prep_entry``)
to avoid clashing with the third-party ``packaging`` distribution, and to confirm
it simply re-exports the real CLI ``main`` without invoking it on import.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from insar_prep.cli.main import main as cli_main

ENTRY_PATH = Path(__file__).resolve().parents[2] / "packaging" / "insar_prep_entry.py"


def _load_entry_module():
    spec = importlib.util.spec_from_file_location("insar_prep_entry", ENTRY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entry_file_exists() -> None:
    assert ENTRY_PATH.is_file()


def test_entry_reexports_cli_main() -> None:
    module = _load_entry_module()
    # Importing the entry must not run the CLI; it only exposes the real main.
    assert module.main is cli_main
