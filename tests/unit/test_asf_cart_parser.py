"""Tests for ASF cart / URL file parsing (Task 006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from insar_prep.core.exceptions import InputValidationError
from insar_prep.providers.asf.cart_parser import (
    extract_urls_from_text,
    parse_asf_cart_file,
    parse_asf_csv,
    parse_asf_geojson,
    parse_asf_python_script,
    parse_url_text,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "asf"
S1A_NAME = "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
S1A_URL = f"https://datapool.asf.alaska.edu/SLC/SA/{S1A_NAME}.zip"
S1B_NAME = "S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064DEF_5678"
S1B_URL = f"https://datapool.asf.alaska.edu/SLC/SB/{S1B_NAME}.zip"


def test_extract_urls_ignores_non_asf() -> None:
    text = f"see {S1A_URL} and https://example.com/help and {S1B_URL}"
    assert extract_urls_from_text(text) == [S1A_URL, S1B_URL]


def test_python_script_is_not_executed(tmp_path: Path) -> None:
    script = tmp_path / "download-all.py"
    script.write_text(
        "raise RuntimeError('this script must not be executed')\n"
        f"urls = ['{S1A_URL}', 'https://example.com/x']\n",
        encoding="utf-8",
    )
    # If the parser executed the script, the RuntimeError would propagate.
    assert parse_asf_python_script(script) == [S1A_URL]


def test_parse_url_text_ignores_blanks_and_comments() -> None:
    assert parse_url_text(FIXTURES / "urls.txt") == [S1A_URL, S1B_URL]


def test_parse_csv_with_url_and_name_only_rows() -> None:
    scenes = parse_asf_csv(FIXTURES / "scenes.csv")
    by_id = {scene.scene_id: scene for scene in scenes}
    assert set(by_id) == {S1A_NAME, S1B_NAME}
    assert by_id[S1A_NAME].url == S1A_URL
    assert by_id[S1B_NAME].url is None


def test_parse_geojson_extracts_scenes() -> None:
    scenes = parse_asf_geojson(FIXTURES / "scenes.geojson")
    assert {scene.scene_id for scene in scenes} == {S1A_NAME, S1B_NAME}


def test_geojson_without_features_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.geojson"
    empty.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    with pytest.raises(InputValidationError):
        parse_asf_geojson(empty)


def test_cart_file_dispatch_on_txt() -> None:
    scenes = parse_asf_cart_file(FIXTURES / "urls.txt")
    assert {scene.scene_id for scene in scenes} == {S1A_NAME, S1B_NAME}


def test_cart_file_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "cart.xml"
    bad.write_text("<xml/>", encoding="utf-8")
    with pytest.raises(InputValidationError):
        parse_asf_cart_file(bad)


def test_cart_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        parse_asf_cart_file(tmp_path / "nope.txt")


def test_cart_file_without_scenes_raises(tmp_path: Path) -> None:
    only_bad = tmp_path / "bad.txt"
    only_bad.write_text("https://example.com/not-a-granule\n", encoding="utf-8")
    with pytest.raises(InputValidationError):
        parse_asf_cart_file(only_bad)
