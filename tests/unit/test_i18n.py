"""Tests for the lightweight GUI i18n layer (Task 055).

No PySide6 required: the catalog and persistence are plain Python.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from insar_prep import i18n


@pytest.fixture(autouse=True)
def _restore_language():
    """Save and restore the process language so tests don't leak state."""
    previous = i18n.get_language()
    yield
    i18n.set_language(previous)


def test_default_language_is_english() -> None:
    i18n.set_language("en")
    assert i18n.get_language() == "en"
    assert i18n.tr("aoi.title") == "Area of interest (AOI)"


def test_switch_to_chinese_changes_translation() -> None:
    i18n.set_language("zh")
    assert i18n.get_language() == "zh"
    assert i18n.tr("aoi.title") == "研究范围（AOI）"
    assert i18n.tr("common.run") == "运行"


def test_unknown_key_returns_key() -> None:
    i18n.set_language("en")
    assert i18n.tr("no.such.key") == "no.such.key"


def test_unsupported_language_is_ignored() -> None:
    i18n.set_language("en")
    i18n.set_language("fr")
    assert i18n.get_language() == "en"


def test_available_languages_include_en_and_zh() -> None:
    codes = {code for code, _name in i18n.available_languages()}
    assert {"en", "zh"} <= codes


def test_format_placeholders() -> None:
    # The catalog has no placeholder entry by default; ensure kwargs never crash.
    assert i18n.tr("app.title", unused="x")


def test_save_and_load_language_roundtrip(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    i18n.save_language("zh", path=settings)
    i18n.set_language("en")
    loaded = i18n.load_saved_language(path=settings)
    assert loaded == "zh"
    assert i18n.get_language() == "zh"


def test_load_missing_settings_defaults_to_english(tmp_path: Path) -> None:
    loaded = i18n.load_saved_language(path=tmp_path / "absent.json")
    assert loaded == "en"


def test_every_key_has_english(tmp_path: Path) -> None:
    # Every catalog entry must at least define English (the fallback language).
    for key, entry in i18n._CATALOG.items():
        assert "en" in entry, f"missing English for {key}"
