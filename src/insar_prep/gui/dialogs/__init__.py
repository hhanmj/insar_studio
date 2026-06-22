"""Input dialogs for the insar-prep GUI (Task 038).

Small PySide6 ``QDialog`` subclasses that collect text input for creating a
Workspace, Project, or Region. They require PySide6 (the ``gui`` extra) and hold
no business logic: the collected values are handed to
:class:`insar_prep.gui.state.GuiState`, which assembles the core models.
"""

from __future__ import annotations
