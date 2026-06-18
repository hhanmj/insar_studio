"""Console entry point for the ``insar-prep`` command.

This is a skeleton CLI: it only exposes ``--help`` and ``--version``.
No business functionality is implemented here yet.
"""

from __future__ import annotations

import argparse

from insar_prep import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="insar-prep",
        description="SARscape-oriented InSAR data preparation assistant (skeleton).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"insar-prep {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    # No subcommands yet: show help so the command is informative.
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
