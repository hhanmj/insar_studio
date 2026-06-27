"""Dev-only helper: render the GUI off-screen and save PNG screenshots.

Used to produce before/after comparisons while polishing the QSS theme. Runs
head-less via the Qt "offscreen" platform, so it needs no display and touches no
network (window construction is offline, as the frozen-build self-test proves).

Usage (from the insar_assistant repo root, inside the venv):

    .venv\\Scripts\\python.exe scripts\\dev_ui_screenshot.py --theme light --out .ui_preview

It grabs every left-nav page for the chosen theme(s). This file is a throwaway
development aid and is safe to delete.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _load_fonts(app: object) -> None:
    """Force real Windows fonts into the offscreen font DB (avoids tofu boxes)."""
    from PySide6.QtGui import QFont, QFontDatabase

    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    family = None
    for filename, want in (("segoeui.ttf", "Segoe UI"), ("msyh.ttc", "Microsoft YaHei")):
        candidate = fonts_dir / filename
        if candidate.exists():
            QFontDatabase.addApplicationFont(str(candidate))
            family = family or want
    if family:
        app.setFont(QFont(family, 10))


def _capture(theme: str, out_dir: Path, width: int, height: int) -> list[Path]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from insar_prep import i18n
    from insar_prep.gui import theme as theme_module
    from insar_prep.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    _load_fonts(app)
    i18n.set_language("en")
    theme_module.apply_theme(app, theme)

    window = MainWindow()
    window.resize(width, height)
    window.show()
    app.processEvents()

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    rows = window.nav_list.count()
    for row in range(rows):
        window.nav_list.setCurrentRow(row)
        app.processEvents()
        label = window.nav_list.item(row).text().strip().lower().replace(" ", "_")
        path = out_dir / f"{theme}_{row}_{label}.png"
        window.grab().save(str(path))
        saved.append(path)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", default="light", choices=["light", "dark", "both"])
    parser.add_argument("--out", default=".ui_preview")
    parser.add_argument("--width", type=int, default=1360)
    parser.add_argument("--height", type=int, default=860)
    args = parser.parse_args()

    themes = ["light", "dark"] if args.theme == "both" else [args.theme]
    out_dir = Path(args.out).resolve()
    for theme in themes:
        for path in _capture(theme, out_dir, args.width, args.height):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
