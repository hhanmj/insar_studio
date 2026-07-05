"""Smoke tests for the v0.1.0 project skeleton."""

from __future__ import annotations

import pytest

import insar_prep
from insar_prep.cli.main import main


def test_version_is_nonempty_string() -> None:
    assert isinstance(insar_prep.__version__, str)
    assert insar_prep.__version__


def test_cli_no_args_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "insar-prep" in captured.out


def test_cli_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert insar_prep.__version__ in captured.out
