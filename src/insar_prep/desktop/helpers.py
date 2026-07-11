"""Shared desktop helpers for formatting errors and detecting proxies."""

from __future__ import annotations

from insar_prep.core.exceptions import InsarPrepError


def _error_msg(message: str, code: str | None = None) -> dict:
    """Build a plain error envelope (no core exception involved)."""
    return {"ok": False, "error": message, "code": code}


def _error(exc: InsarPrepError) -> dict:
    """Render a coded core error as a JSON-friendly envelope for the UI."""
    code = getattr(exc, "code", None)
    return {"ok": False, "error": str(exc), "code": getattr(code, "name", None)}


def _normalise_proxy_url(value: object) -> str:
    """Ensure a proxy URL string starts with a scheme."""
    proxy_url = str(value or "").strip()
    if proxy_url and "://" not in proxy_url:
        proxy_url = f"http://{proxy_url}"
    return proxy_url


def _detect_system_proxy() -> str:
    """Return the OS/browser proxy, if one is configured."""
    try:
        import urllib.request  # noqa: PLC0415 - small stdlib import

        proxies = urllib.request.getproxies()
    except Exception:  # noqa: BLE001
        return ""
    for key in ("https", "http", "all"):
        proxy_url = _normalise_proxy_url(proxies.get(key))
        if proxy_url:
            return proxy_url
    return ""
