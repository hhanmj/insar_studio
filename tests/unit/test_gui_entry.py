"""Tests for the GUI entry point and skeleton (Task 037).

Headless by default: the GUI runtime smoke test is skipped unless PySide6 (the
optional ``gui`` extra) is installed. None of these tests open a socket,
download anything, or require a real display.
"""

from __future__ import annotations

import importlib.util

import pytest

from insar_prep.cli.main import build_parser, main
from insar_prep.core.error_codes import ErrorCode
from insar_prep.gui import PYSIDE6_MISSING_MESSAGE, WINDOW_TITLE, WORKFLOW_STEPS

_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _patch_pyside6_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``find_spec('PySide6')`` report it as not installed.

    Other modules resolve normally, so this isolates the missing-GUI-extra path
    regardless of whether PySide6 is actually installed in the test env.
    """
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object):
        if name == "PySide6":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


def test_gui_constants_importable_without_pyside6() -> None:
    # The shared constants live in insar_prep.gui and must import without PySide6.
    assert WINDOW_TITLE == "INSAR Prep Assistant"
    assert WORKFLOW_STEPS[0] == "Workspace"
    assert "Reports" in WORKFLOW_STEPS
    assert "uv sync --extra gui" in PYSIDE6_MISSING_MESSAGE


def test_gui_subcommand_is_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["prepare", "--help"],
        ["plan-asf-downloads", "--help"],
        ["gui", "--help"],
    ],
)
def test_help_does_not_require_pyside6(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Even with PySide6 unavailable, --help for every command must succeed.
    _patch_pyside6_missing(monkeypatch)
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 0
    assert capsys.readouterr().out  # help text was printed


def test_gui_without_pyside6_reports_clear_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_pyside6_missing(monkeypatch)
    exit_code = main(["gui"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert PYSIDE6_MISSING_MESSAGE in captured.err
    # The user-visible error carries the GUI001 error code (manual section 30).
    assert f"[{ErrorCode.GUI001.value}]" in captured.err
    # A missing optional dependency must not surface as a traceback.
    assert "Traceback" not in captured.err


@pytest.mark.skipif(not _PYSIDE6_AVAILABLE, reason="PySide6 (gui extra) not installed")
def test_main_window_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    # Render with the offscreen Qt platform plugin so no real display is needed.
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from insar_prep.gui.app import create_application
    from insar_prep.gui.main_window import MainWindow

    create_application([])
    window = MainWindow()

    assert window.windowTitle() == WINDOW_TITLE
    assert window.project_tree.topLevelItemCount() == 1
    assert window.project_tree.topLevelItem(0).text(0) == "Workspace"
    assert window.workflow_steps.step_list.count() == len(WORKFLOW_STEPS)
    assert window.queue_log_panel.queue_view.count() >= 1
    assert window.status_bar_widget.status_text() == "Ready"
