"""Offline tests for the GitHub update check.

No network is ever used: a fake ``fetch`` is injected (or the cache is seeded),
so version parsing/comparison, the throttle/opt-out logic, and the cached
fallbacks are all exercised deterministically.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from insar_prep.core import update_check as uc


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden in update-check tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.12.0", (0, 12, 0)),
        ("v0.12.0", (0, 12, 0)),
        ("v1.2", (1, 2, 0)),
        ("release-2.3.4", (2, 3, 4)),
        ("1.0.0-rc1", (1, 0, 0)),
        ("not-a-version", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_version(text: str | None, expected: tuple[int, int, int] | None) -> None:
    assert uc.parse_version(text) == expected


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("0.13.0", "0.12.0", True),
        ("v1.0.0", "0.12.0", True),
        ("0.12.1", "0.12.0", True),
        ("0.12.0", "0.12.0", False),
        ("0.11.9", "0.12.0", False),
        ("bad", "0.12.0", False),
        ("0.13.0", None, False),
    ],
)
def test_is_newer(candidate: str, current: str | None, newer: bool) -> None:
    assert uc.is_newer(candidate, current) is newer


def test_check_for_update_detects_newer() -> None:
    payload = {
        "tag_name": "v0.13.0",
        "name": "InSAR Studio 0.13.0",
        "html_url": "https://example/releases/v0.13.0",
        "body": "- Startup update dialog\n- Download package",
        "published_at": "2026-07-08T00:00:00Z",
    }
    info = uc.check_for_update("0.12.0", fetch=lambda url, timeout: payload)
    assert info is not None
    assert info.update_available is True
    assert info.latest_version == "v0.13.0"
    assert info.html_url == "https://example/releases/v0.13.0"
    assert info.release_name == "InSAR Studio 0.13.0"
    assert "Startup update dialog" in info.changelog
    assert info.published_at == "2026-07-08T00:00:00Z"


def test_check_for_update_extracts_release_asset_mirrors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        uc.UPDATE_MIRROR_BASE_ENV,
        "https://download.example.com/insar/{tag}/{asset}",
    )
    payload = {
        "tag_name": "v0.13.0",
        "body": (
            "<!-- insar-update-mirror: https://mirror.example.com/InSAR-Studio-0.13.0.exe -->"
        ),
        "assets": [
            {
                "name": "InSAR-Studio-0.13.0.exe",
                "browser_download_url": "https://github.com/example/InSAR-Studio-0.13.0.exe",
                "size": 123,
            }
        ],
    }
    info = uc.check_for_update("0.12.0", fetch=lambda url, timeout: payload)
    assert info is not None
    assert info.assets
    assert info.assets[0].mirrors == (
        "https://download.example.com/insar/v0.13.0/InSAR-Studio-0.13.0.exe",
        "https://mirror.example.com/InSAR-Studio-0.13.0.exe",
    )


def test_check_for_update_up_to_date() -> None:
    info = uc.check_for_update("0.12.0", fetch=lambda url, timeout: {"tag_name": "v0.12.0"})
    assert info is not None
    assert info.update_available is False
    # Falls back to the canonical releases page when the payload omits html_url.
    assert info.html_url == uc.releases_page_url()


def test_check_for_update_returns_none_on_empty_or_bad_payload() -> None:
    assert uc.check_for_update("0.12.0", fetch=lambda url, timeout: None) is None
    assert uc.check_for_update("0.12.0", fetch=lambda url, timeout: {"tag_name": "nope"}) is None


def test_format_update_notice() -> None:
    info = uc.UpdateInfo("0.12.0", "v0.13.0", "https://example/r", True)
    notice = uc.format_update_notice(info)
    assert "v0.13.0" in notice
    assert "0.12.0" in notice
    assert "https://example/r" in notice


@pytest.mark.parametrize(
    ("value", "opted_out"),
    [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("", False)],
)
def test_is_opted_out(value: str, opted_out: bool) -> None:
    assert uc.is_opted_out({uc.UPDATE_CHECK_OPT_OUT_ENV: value}) is opted_out


def test_maybe_check_opt_out_skips_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ban_network(monkeypatch)
    result = uc.maybe_check_for_update(
        "0.12.0",
        env={uc.UPDATE_CHECK_OPT_OUT_ENV: "1"},
        fetch=lambda url, timeout: pytest.fail("must not fetch when opted out"),
        cache_path=tmp_path / "cache.json",
    )
    assert result is None


def test_maybe_check_fetches_and_caches(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    calls: list[str] = []

    def _fetch(url: str, timeout: float) -> dict:
        calls.append(url)
        return {"tag_name": "v0.13.0", "html_url": "https://example/r"}

    info = uc.maybe_check_for_update("0.12.0", env={}, now=1000.0, fetch=_fetch, cache_path=cache)
    assert info is not None and info.update_available
    assert len(calls) == 1
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["latest_version"] == "v0.13.0"
    assert saved["last_check_ts"] == 1000.0


def test_maybe_check_caches_changelog_for_startup_prompt(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"

    def _fetch(url: str, timeout: float) -> dict:
        return {
            "tag_name": "v0.13.0",
            "name": "InSAR Studio 0.13.0",
            "html_url": "https://example/r",
            "body": "更新日志正文",
            "published_at": "2026-07-08T00:00:00Z",
        }

    first = uc.maybe_check_for_update("0.12.0", env={}, now=1000.0, fetch=_fetch, cache_path=cache)
    assert first is not None
    assert first.changelog == "更新日志正文"

    def _no_fetch(url: str, timeout: float) -> dict:
        pytest.fail("must reuse cached update metadata inside the throttle interval")

    cached = uc.maybe_check_for_update(
        "0.12.0", env={}, now=1100.0, fetch=_no_fetch, cache_path=cache
    )
    assert cached is not None
    assert cached.release_name == "InSAR Studio 0.13.0"
    assert cached.changelog == "更新日志正文"
    assert cached.published_at == "2026-07-08T00:00:00Z"


def test_maybe_check_throttles_within_interval(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {"last_check_ts": 1000.0, "latest_version": "v0.13.0", "html_url": "https://example/r"}
        ),
        encoding="utf-8",
    )

    def _fetch(url: str, timeout: float) -> dict:
        pytest.fail("must not fetch within the throttle interval")

    # 100s later, well within the 24h interval: no network, but the cached newer
    # version is still surfaced.
    info = uc.maybe_check_for_update("0.12.0", env={}, now=1100.0, fetch=_fetch, cache_path=cache)
    assert info is not None
    assert info.latest_version == "v0.13.0"


def test_maybe_check_force_bypasses_throttle(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"last_check_ts": 1000.0}), encoding="utf-8")
    calls: list[str] = []

    def _fetch(url: str, timeout: float) -> dict:
        calls.append(url)
        return {"tag_name": "v0.13.0"}

    info = uc.maybe_check_for_update(
        "0.12.0", env={}, now=1100.0, fetch=_fetch, cache_path=cache, force=True
    )
    assert info is not None
    assert len(calls) == 1


def test_maybe_check_network_failure_uses_cached_latest(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "last_check_ts": 0.0,
                "latest_version": "v0.13.0",
                "html_url": "https://example/r",
                "assets": [
                    {
                        "name": "insar-prep-desktop.exe",
                        "download_url": "https://example/a.exe",
                        "mirrors": ["https://mirror.example/a.exe"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Interval elapsed -> it tries the network, which fails (None), and falls back
    # to the cached known-newer release instead of going silent.
    info = uc.maybe_check_for_update(
        "0.12.0",
        env={},
        now=10_000_000.0,
        fetch=lambda url, timeout: None,
        cache_path=cache,
    )
    assert info is not None
    assert info.latest_version == "v0.13.0"
    assert info.assets and info.assets[0].download_url == "https://example/a.exe"
    assert info.assets[0].mirrors == ("https://mirror.example/a.exe",)


def test_cache_dir_is_under_insar_prep() -> None:
    assert uc.cache_dir().name == "insar-prep"
