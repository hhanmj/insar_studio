"""PyInstaller entry point for the insar-prep desktop GUI (Task 053).

A thin, package-external launcher used only for freezing the **windowed** GUI
executable. Freezing a module that lives *inside* the ``insar_prep`` package as a
top-level script can cause double-import / relative-path edge cases; this external
entry imports the installed package and delegates to it instead.

With no arguments it opens the main window. With ``--selftest`` it constructs the
application + main window **off-screen** and exits 0 without starting the event
loop, so a frozen build can be smoke-tested headlessly (no window, no network).
"""

from __future__ import annotations

import os
import sys


def _selftest() -> int:
    """Construct the app + main window off-screen and exit 0 (frozen-build check)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application
    from insar_prep.gui.main_window import MainWindow

    create_application([])
    MainWindow()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return _selftest()
    from insar_prep.gui.app import launch_gui

    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())
