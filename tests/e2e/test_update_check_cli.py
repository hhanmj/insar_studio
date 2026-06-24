"""End-to-end tests for the ``update-check`` CLI and the auto-notify hook.

No network is used: the update-check entry points are monkeypatched so the
command's output formatting and the post-command notice are verified offline.
"""

from __future__ import annotations

import argparse
import socket

import pytest

from insar_prep.cli.main import _command_used_network, _maybe_notify_update, main
from insar_prep.core import update_check as uc


def _ban_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_update_check_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["update-check", "--help"])
    assert exc.value.code == 0


def test_update_check_reports_available(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.setattr(
        uc,
        "check_for_update",
        lambda *a, **k: uc.UpdateInfo("0.12.0", "v0.13.0", "https://example/r", True),
    )
    code = main(["update-check"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Update available" in out
    assert "v0.13.0" in out


def test_update_check_reports_up_to_date(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.setattr(
        uc,
        "check_for_update",
        lambda *a, **k: uc.UpdateInfo("0.12.0", "v0.12.0", "https://example/r", False),
    )
    code = main(["update-check"])
    assert code == 0
    assert "up to date" in capsys.readouterr().out


def test_update_check_handles_failure(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ban_network(monkeypatch)
    monkeypatch.setattr(uc, "check_for_update", lambda *a, **k: None)
    code = main(["update-check"])
    # Best-effort: a failed check is not a hard error.
    assert code == 0
    assert "Could not check for updates" in capsys.readouterr().err


def test_auto_notify_prints_after_network_command(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        uc,
        "maybe_check_for_update",
        lambda *a, **k: uc.UpdateInfo("0.12.0", "v0.13.0", "https://example/r", True),
    )
    args = argparse.Namespace(command="download-asf", download_mode="real")
    _maybe_notify_update(args)
    assert "Update available" in capsys.readouterr().err


def test_auto_notify_skips_offline_commands(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a: object, **k: object) -> object:
        raise AssertionError("auto-notify must not run for offline commands")

    monkeypatch.setattr(uc, "maybe_check_for_update", _boom)
    offline_invocations = [
        argparse.Namespace(command=None),
        argparse.Namespace(command="update-check"),
        argparse.Namespace(command="gui"),
        argparse.Namespace(command="prepare"),
        argparse.Namespace(command="plan-asf-downloads"),
        argparse.Namespace(command="download-asf", download_mode="dry-run"),
    ]
    for args in offline_invocations:
        _maybe_notify_update(args)
    assert capsys.readouterr().err == ""


def test_auto_notify_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: object, **k: object) -> object:
        raise RuntimeError("network exploded")

    monkeypatch.setattr(uc, "maybe_check_for_update", _boom)
    # Must swallow any error so it cannot affect the command's exit code.
    _maybe_notify_update(argparse.Namespace(command="download-asf", download_mode="verify"))


@pytest.mark.parametrize(
    ("args", "used_network"),
    [
        (argparse.Namespace(command="download-asf", download_mode="real"), True),
        (argparse.Namespace(command="download-asf", download_mode="verify"), True),
        (argparse.Namespace(command="download-asf", download_mode="dry-run"), False),
        (argparse.Namespace(command="auth", action="status", test_connection=True), True),
        (argparse.Namespace(command="auth", action="status", test_connection=False), False),
        (argparse.Namespace(command="auth", action="login"), False),
        (argparse.Namespace(command="prepare"), False),
        (argparse.Namespace(command=None), False),
    ],
)
def test_command_used_network(args: argparse.Namespace, used_network: bool) -> None:
    assert _command_used_network(args) is used_network
