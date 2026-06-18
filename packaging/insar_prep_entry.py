"""PyInstaller entry point for the ``insar-prep`` CLI (Task 022).

A thin, package-external launcher used only for freezing a standalone executable.
Freezing a module that lives *inside* the ``insar_prep`` package as a top-level
script can cause double-import / relative-path edge cases; this external entry
imports the installed package and delegates to its ``main`` instead.
"""

from __future__ import annotations

from insar_prep.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
