"""PySide6 GUI for insar-prep (Task 037, beta skeleton).

This subpackage holds the optional desktop GUI. It is a **read-only skeleton**:
it builds the main-window shell (project tree, workflow steps, queue/log panel,
and a warnings/errors status bar) and is intended to call into the existing
``insar_prep`` core interfaces only. It must never re-implement business logic,
download data, or access the network.

PySide6 is an **optional** dependency (the ``gui`` extra). Importing this
package by itself does not import PySide6; only the :mod:`insar_prep.gui.app`
and widget modules require it. The ``insar-prep gui`` command imports those
lazily and prints a clear message when PySide6 is not installed.

The plain constants below (window title and workflow step labels) live here so
they can be imported and asserted in headless environments without PySide6.
"""

from __future__ import annotations

WINDOW_TITLE = "INSAR Prep Assistant"

# Placeholder workflow steps shown in the centre panel. These are UI labels for
# the skeleton; the real per-step wiring to core interfaces lands in later tasks.
WORKFLOW_STEPS: tuple[str, ...] = (
    "Workspace",
    "Project",
    "Region / AOI",
    "ASF Cart",
    "Scene Check",
    "Orbit / DEM / GACOS Plan",
    "Reports",
    "Download",
)

# Message shown when the GUI extra (PySide6) is not installed.
PYSIDE6_MISSING_MESSAGE = "PySide6 is required for the GUI. Install with: uv sync --extra gui"

__all__ = ["PYSIDE6_MISSING_MESSAGE", "WINDOW_TITLE", "WORKFLOW_STEPS"]
