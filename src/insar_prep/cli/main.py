"""Console entry point for the ``insar-prep`` command.

Exposes ``--help`` and ``--version`` plus the offline ``prepare`` workflow
(ASF cart -> scene check -> data preparation report). No network, no GUI.
"""

from __future__ import annotations

import argparse

from insar_prep import __version__
from insar_prep.cli.commands import (
    add_plan_asf_downloads_subparser,
    add_prepare_subparser,
    run_plan_asf_downloads,
    run_prepare,
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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "prepare":
        return run_prepare(args)
    if args.command == "plan-asf-downloads":
        return run_plan_asf_downloads(args)
    # No subcommand: show help so the command is informative.
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
