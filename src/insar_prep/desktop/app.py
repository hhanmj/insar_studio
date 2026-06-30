"""Launch the native desktop window that hosts the web UI.

Resolution order for the page to load:

1. ``INSAR_DESKTOP_URL`` env var (e.g. ``http://localhost:5173`` for live vite dev)
2. the bundled production build ``insar_prep/desktop/web/index.html``
3. the repo dev build ``ui/dist/index.html``
4. the vite dev server fallback ``http://localhost:5173``
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from insar_prep.desktop.api import Api


def _schedule_force_exit(delay: float = 0.8) -> None:
    """Force the desktop process down after normal shutdown has had a moment.

    WebView2 / pythonnet can occasionally keep helper threads alive after the
    native window is gone.  The desktop app has no useful background mode, so
    after the API saves state and stops jobs we terminate the current process as
    a final guard against invisible leftovers.
    """
    if os.environ.get("INSAR_DESKTOP_NO_FORCE_EXIT"):
        return

    def exit_now() -> None:
        os._exit(0)  # noqa: SLF001 - deliberate last-resort desktop cleanup

    timer = threading.Timer(delay, exit_now)
    timer.daemon = True
    timer.start()


def resolve_url() -> str:
    """Return the URL / file path the WebView should load."""
    override = os.environ.get("INSAR_DESKTOP_URL")
    if override:
        return override

    # Frozen (PyInstaller) build: the web assets are bundled under
    # ``<_MEIPASS>/insar_prep/desktop/web`` via the build's --add-data.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen = Path(meipass) / "insar_prep" / "desktop" / "web" / "index.html"
        if frozen.exists():
            return str(frozen)

    here = Path(__file__).resolve()
    bundled = here.parent / "web" / "index.html"
    if bundled.exists():
        return str(bundled)

    repo_dist = here.parents[3] / "ui" / "dist" / "index.html"
    if repo_dist.exists():
        return str(repo_dist)

    return "http://localhost:5173"


def run() -> int:
    """Create the WebView2 window, wire the Python API, and run the GUI loop."""
    import webview  # noqa: PLC0415 - optional dependency, imported lazily

    api = Api()
    window = webview.create_window(
        "InSAR Studio",
        url=resolve_url(),
        js_api=api,
        width=1320,
        height=880,
        min_size=(920, 620),
        resizable=True,
        frameless=True,
        easy_drag=False,
    )

    def shutdown_api(*_args: object, **_kwargs: object) -> None:
        api.shutdown()

    for event_name in ("closing", "closed"):
        try:
            event = getattr(window.events, event_name)
            event += shutdown_api
        except Exception:
            pass
    try:
        webview.start()
    finally:
        api.shutdown()
        _schedule_force_exit()
    return 0
