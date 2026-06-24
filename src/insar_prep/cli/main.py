"""Console entry point for the ``insar-prep`` command.

Exposes ``--help`` and ``--version``, the offline ``prepare`` workflow
(ASF cart -> scene check -> data preparation report), the ``plan-asf-downloads``
dry-run planner, the ``download-asf`` command (offline dry-run by default; a
``--download-mode verify`` network preflight and real SLC download with
``--download-mode real``, both needing the optional ``download`` extra), the
``update-check`` command, and the optional ``gui`` subcommand (PySide6 desktop
GUI, beta skeleton; requires the ``gui`` extra). After a command that already
used the network (``download-asf`` verify/real, ``auth status --test``) a
throttled, opt-out (``INSAR_NO_UPDATE_CHECK=1``) update notice may be printed to
stderr, so the offline commands keep touching no network. ``download-asf``
(verify/real), ``auth status --test``, and ``update-check`` access the network.
"""

from __future__ import annotations

import argparse
import sys

from insar_prep import __version__
from insar_prep.cli.commands import (
    add_auth_subparser,
    add_convert_dem_subparser,
    add_dem_auth_subparser,
    add_download_asf_subparser,
    add_download_dem_subparser,
    add_gacos_import_subparser,
    add_gui_subparser,
    add_plan_asf_downloads_subparser,
    add_prepare_subparser,
    add_update_check_subparser,
    run_auth,
    run_convert_dem,
    run_dem_auth,
    run_download_asf,
    run_download_dem,
    run_gacos_import,
    run_gui,
    run_plan_asf_downloads,
    run_prepare,
    run_update_check,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="insar-prep",
        description="SARscape-oriented InSAR data preparation assistant.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"insar-prep {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    add_prepare_subparser(subparsers)
    add_plan_asf_downloads_subparser(subparsers)
    add_download_asf_subparser(subparsers)
    add_download_dem_subparser(subparsers)
    add_convert_dem_subparser(subparsers)
    add_gacos_import_subparser(subparsers)
    add_auth_subparser(subparsers)
    add_dem_auth_subparser(subparsers)
    add_update_check_subparser(subparsers)
    add_gui_subparser(subparsers)
    return parser


def _command_used_network(args: argparse.Namespace) -> bool:
    """Return True if the command that just ran already performed network I/O.

    The automatic update notice is only attached to such commands so the strictly
    offline commands (``prepare`` / ``plan-asf-downloads`` / ``download-asf``
    dry-run) keep their "touches no network" guarantee. The GUI surfaces its own
    startup notice, and ``update-check`` is always available on demand.
    """
    command = getattr(args, "command", None)
    if command in ("download-asf", "download-dem"):
        return getattr(args, "download_mode", "dry-run") in ("verify", "real")
    if command == "auth":
        return getattr(args, "action", None) == "status" and getattr(args, "test_connection", False)
    return False


def _maybe_notify_update(args: argparse.Namespace) -> None:
    """Print a one-line 'update available' notice (throttled, opt-out, best-effort).

    Only runs after a command that already used the network (see
    :func:`_command_used_network`), queries GitHub at most once per day (cached),
    and is silenced by ``INSAR_NO_UPDATE_CHECK=1``. Any failure is swallowed so
    the update check can never affect the command's behaviour or exit code.
    """
    if not _command_used_network(args):
        return
    try:
        from insar_prep.core.update_check import format_update_notice, maybe_check_for_update

        info = maybe_check_for_update()
        if info is not None:
            sys.stderr.write(format_update_notice(info) + "\n")
    except Exception:  # noqa: BLE001 - the update check must never break a command
        pass


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "prepare":
        return run_prepare(args)
    if args.command == "plan-asf-downloads":
        return run_plan_asf_downloads(args)
    if args.command == "download-asf":
        return run_download_asf(args)
    if args.command == "download-dem":
        return run_download_dem(args)
    if args.command == "convert-dem":
        return run_convert_dem(args)
    if args.command == "gacos-import":
        return run_gacos_import(args)
    if args.command == "auth":
        return run_auth(args)
    if args.command == "dem-auth":
        return run_dem_auth(args)
    if args.command == "update-check":
        return run_update_check(args)
    if args.command == "gui":
        return run_gui(args)
    # No subcommand: show help so the command is informative.
    parser.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    code = _dispatch(args, parser)
    _maybe_notify_update(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
