"""Light/dark stylesheet helpers for the optional PySide6 GUI."""

from __future__ import annotations

from typing import Any

DEFAULT_THEME = "light"
THEMES: tuple[str, ...] = ("light", "dark")


def build_stylesheet(name: str | None = None) -> str:
    """Build a compact Qt stylesheet for the selected theme."""
    theme = (name or DEFAULT_THEME).strip().lower()
    if theme not in THEMES:
        theme = DEFAULT_THEME
    dark = theme == "dark"
    window = "#0a0f1a" if dark else "#f5f7fa"
    panel = "#101827" if dark else "#ffffff"
    border = "#253247" if dark else "#dbe2ea"
    text = "#e2e8f0" if dark else "#0f172a"
    muted = "#94a3b8" if dark else "#64748b"
    primary = "#14b8a6" if dark else "#0d9488"
    primary_soft = "#123f3b" if dark else "#d9f6f2"
    return f"""
QWidget {{
    background: {window};
    color: {text};
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 10pt;
}}
QGroupBox {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {muted};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {primary};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {primary};
}}
QPushButton {{
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 12px;
}}
QPushButton:hover {{
    background: {primary_soft};
    border-color: {primary};
}}
QStatusBar {{
    background: {panel};
    border-top: 1px solid {border};
}}
QListWidget#nav_sidebar, QTreeWidget, QTableWidget {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QListWidget#nav_sidebar::item {{
    border-radius: 6px;
    padding: 8px 10px;
}}
QListWidget#nav_sidebar::item:selected {{
    background: {primary_soft};
    color: {text};
}}
QLabel#page_subtitle {{
    color: {muted};
}}
"""


def apply_theme(app: Any, name: str | None = None) -> str:
    """Apply a theme stylesheet to ``app`` and return the normalized name."""
    theme = (name or DEFAULT_THEME).strip().lower()
    if theme not in THEMES:
        theme = DEFAULT_THEME
    app.setStyleSheet(build_stylesheet(theme))
    return theme
