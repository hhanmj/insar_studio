"""Modern desktop UI for insar-prep.

A web frontend (React/Vite, built into ``ui/dist`` and bundled here as ``web/``)
hosted in a native OS WebView2 window via :mod:`webview` (pywebview). The Python
side exposes :class:`insar_prep.desktop.api.Api` to the page as
``window.pywebview.api.*`` and reuses the existing core in-process -- no Rust, no
sidecar, no second runtime.

Optional component: requires the ``desktop`` extra (``uv sync --extra desktop``).
The offline CLI never imports this package.
"""

from __future__ import annotations
