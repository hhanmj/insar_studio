"""PySide6 application launcher for the insar-prep GUI (Task 037).

Imported lazily by the ``insar-prep gui`` command, and only when PySide6 is
available. It creates the ``QApplication`` and shows the skeleton main window.
No business logic, no network, no downloads.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from insar_prep.gui.main_window import MainWindow


def create_application(argv: list[str] | None = None) -> QApplication:
    """Return the running ``QApplication``, creating one if needed.

    ``QApplication`` is a per-process singleton, so this reuses an existing
    instance (handy for tests) instead of constructing a second one.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else [])
    return app


def launch_gui(argv: list[str] | None = None) -> int:
    """Create the application, show the main window, and run the event loop.

    Returns the Qt event-loop exit code.
    """
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()
