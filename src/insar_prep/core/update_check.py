"""Best-effort update check against GitHub Releases.

Tells the user when a newer ``insar-prep`` release is available, using only the
Python standard library (``urllib``) -- no third-party dependency, so the check
works even in the base packaged ``.exe`` that does not ship the ``download``
extra. The design is deliberately defensive:

- Every network or parse error is swallowed; a failed check returns ``None`` and
  never breaks the command the user actually ran.
- The automatic check (:func:`maybe_check_for_update`) is throttled by a small
  on-disk cache so the GitHub API is queried at most once per interval, and is
  opt-out via the ``INSAR_NO_UPDATE_CHECK`` environment variable.
- No credential, token, or personal data is sent or stored; only the public
  "latest release" endpoint is read and only a timestamp + the public latest tag
  are cached.

The functions accept injected ``fetch`` / ``now`` / ``cache_path`` parameters so
the whole module is unit-testable offline and deterministically.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep import __version__
from insar_prep.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger("core.update_check")

# Public GitHub repository that publishes the releases (matches pyproject URLs).
GITHUB_REPO = "hhanmj/insar_assistant"

# Opt out of the *automatic* check (the explicit ``update-check`` command still
# works). Any of 1/true/yes/on (case-insensitive) disables it.
UPDATE_CHECK_OPT_OUT_ENV = "INSAR_NO_UPDATE_CHECK"

DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_CHECK_INTERVAL_SECONDS = 24 * 60 * 60

_TRUTHY = {"1", "true", "yes", "on"}
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True)
class UpdateInfo:
    """Result of a (successful) update check."""

    current_version: str
    latest_version: str
    html_url: str
    update_available: bool


def release_api_url(repo: str = GITHUB_REPO) -> str:
    """Return the GitHub API URL for the repository's latest release."""
    return f"https://api.github.com/repos/{repo}/releases/latest"


def releases_page_url(repo: str = GITHUB_REPO) -> str:
    """Return the human-facing GitHub releases page (used as a download link)."""
    return f"https://github.com/{repo}/releases/latest"


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """Parse a version like ``v0.12.0`` / ``0.12`` into ``(major, minor, patch)``.

    Returns ``None`` if no ``MAJOR.MINOR`` core can be found. A missing patch is
    treated as ``0``. Any pre-release/build suffix is ignored for comparison.
    """
    if not text:
        return None
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


def is_newer(candidate: str | None, current: str | None) -> bool:
    """Return True if ``candidate`` is a strictly newer version than ``current``."""
    candidate_parsed = parse_version(candidate)
    current_parsed = parse_version(current)
    if candidate_parsed is None or current_parsed is None:
        return False
    return candidate_parsed > current_parsed


def _http_get_json(url: str, timeout: float) -> dict | None:
    """GET ``url`` and parse JSON, returning ``None`` on any failure.

    Sends a descriptive ``User-Agent`` (GitHub rejects requests without one) and
    asks for the versioned REST media type. Never raises.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https GitHub API URL
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"insar-prep/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            if getattr(response, "status", 200) != 200:
                return None
            payload = response.read()
        parsed = json.loads(payload)
    except Exception as exc:  # noqa: BLE001 - update check is best-effort, never fatal
        logger.debug("update check request failed: %s", type(exc).__name__)
        return None
    return parsed if isinstance(parsed, dict) else None


def check_for_update(
    current_version: str = __version__,
    *,
    repo: str = GITHUB_REPO,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    fetch: Callable[[str, float], dict | None] = _http_get_json,
) -> UpdateInfo | None:
    """Query the latest GitHub release and compare it to ``current_version``.

    Returns an :class:`UpdateInfo` on success or ``None`` if the release could
    not be determined (offline, rate-limited, no releases yet, or parse error).
    """
    payload = fetch(release_api_url(repo), timeout)
    if not payload:
        return None
    tag = payload.get("tag_name") or payload.get("name")
    if parse_version(tag) is None:
        return None
    html_url = payload.get("html_url") or releases_page_url(repo)
    return UpdateInfo(
        current_version=current_version,
        latest_version=str(tag),
        html_url=str(html_url),
        update_available=is_newer(tag, current_version),
    )


def format_update_notice(info: UpdateInfo) -> str:
    """Return a one-line, user-facing 'update available' message."""
    return (
        f"Update available: insar-prep {info.latest_version} "
        f"(you have {info.current_version}). Download: {info.html_url}"
    )


def is_opted_out(env: dict[str, str] | None = None) -> bool:
    """Return True if the automatic update check is disabled by environment."""
    environ = os.environ if env is None else env
    return (environ.get(UPDATE_CHECK_OPT_OUT_ENV, "") or "").strip().lower() in _TRUTHY


def cache_dir() -> Path:
    """Return the per-user cache directory for insar-prep (cross-platform)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "insar-prep"


def cache_file() -> Path:
    """Return the path of the throttle/cache file for the automatic check."""
    return cache_dir() / "update_check.json"


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - best-effort cache write
        logger.debug("could not write update-check cache: %s", exc)


def _cached_update(cache: dict, current_version: str, repo: str) -> UpdateInfo | None:
    """Build an UpdateInfo from a cached latest tag, if it is newer."""
    cached_tag = cache.get("latest_version")
    if cached_tag and is_newer(cached_tag, current_version):
        return UpdateInfo(
            current_version=current_version,
            latest_version=str(cached_tag),
            html_url=str(cache.get("html_url") or releases_page_url(repo)),
            update_available=True,
        )
    return None


def maybe_check_for_update(
    current_version: str = __version__,
    *,
    env: dict[str, str] | None = None,
    now: float | None = None,
    interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
    repo: str = GITHUB_REPO,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    fetch: Callable[[str, float], dict | None] = _http_get_json,
    force: bool = False,
    cache_path: Path | None = None,
) -> UpdateInfo | None:
    """Throttled, opt-out automatic check. Returns an UpdateInfo only when newer.

    Honours the ``INSAR_NO_UPDATE_CHECK`` opt-out, queries the network at most
    once per ``interval_seconds`` (tracked in :func:`cache_file`), and falls back
    to the last cached latest tag between checks (or when the network fails) so a
    known-newer version keeps being surfaced without re-hitting the API.
    """
    if is_opted_out(env):
        return None
    moment = time.time() if now is None else now
    path = cache_file() if cache_path is None else cache_path
    cache = _load_cache(path)
    last_check = float(cache.get("last_check_ts", 0) or 0)

    due = force or last_check <= 0 or (moment - last_check) >= interval_seconds
    if not due:
        return _cached_update(cache, current_version, repo)

    info = check_for_update(current_version, repo=repo, timeout=timeout, fetch=fetch)
    new_cache: dict = {"last_check_ts": moment}
    if info is not None:
        new_cache["latest_version"] = info.latest_version
        new_cache["html_url"] = info.html_url
    elif cache.get("latest_version"):
        new_cache["latest_version"] = cache["latest_version"]
        new_cache["html_url"] = cache.get("html_url", "")
    _save_cache(path, new_cache)

    if info is not None:
        return info if info.update_available else None
    return _cached_update(new_cache, current_version, repo)
