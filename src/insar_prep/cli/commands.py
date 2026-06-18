"""CLI subcommands for insar-prep (Task 015).

The ``prepare`` command wires the offline pipeline:
ASF cart parser -> scene consistency check -> data preparation report -> save.

Strictly offline: no GUI, no network, no downloads, no ASF/OpenTopography/GACOS
API calls, no credentials, and no real DEM conversion. No ``print()`` is used
(Ruff ``T20``); user-facing text goes through argparse help or the logger.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from insar_prep.core.enums import Polarization
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import get_logger
from insar_prep.core.naming import sarscape_safe_name
from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
from insar_prep.providers.orbit import match_orbits_for_scenes, scan_orbit_directory
from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.reporting.generator import build_data_preparation_report, save_report

logger = get_logger("cli.prepare")

_EXIT_OK = 0
_EXIT_ERROR = 2


def add_prepare_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``prepare`` subcommand and its arguments."""
    parser = subparsers.add_parser(
        "prepare",
        help="Parse a local ASF cart, check scenes, and write a data preparation report.",
        description=(
            "Offline workflow: parse a local ASF cart file, run scene consistency "
            "checks, and write a JSON + Markdown data preparation report. No network."
        ),
    )
    parser.add_argument(
        "--cart",
        required=True,
        help="Path to a local ASF cart file (.py/.txt/.csv/.geojson/.json).",
    )
    parser.add_argument(
        "--region-name",
        dest="region_name",
        required=True,
        help="Human-readable region name; converted to a SARscape-safe name.",
    )
    parser.add_argument(
        "--output-root",
        dest="output_root",
        required=True,
        help="Workspace root; the report is written under <root>/<region>/07_reports/.",
    )
    parser.add_argument(
        "--region-id",
        dest="region_id",
        default=None,
        help="Optional explicit region id (defaults to region_<safe_name>).",
    )
    parser.add_argument(
        "--require-urls",
        dest="require_urls",
        action="store_true",
        help="Treat scenes without a download URL as errors instead of warnings.",
    )
    parser.add_argument(
        "--expected-polarization",
        dest="expected_polarization",
        default=None,
        choices=[member.value for member in Polarization],
        help="Require every scene to use this Sentinel-1 polarization code.",
    )
    parser.add_argument(
        "--orbit-dir",
        dest="orbit_dir",
        default=None,
        help="Optional local directory of Sentinel-1 orbit (.EOF) files to match.",
    )
    return parser


def run_prepare(args: argparse.Namespace) -> int:
    """Run the offline ``prepare`` workflow. Returns a process exit code."""
    cart_path = Path(args.cart)
    try:
        scenes = parse_asf_cart_file(cart_path)
    except InsarPrepError as exc:
        logger.error("failed to parse ASF cart %s: %s", cart_path, exc)
        return _EXIT_ERROR

    try:
        region_safe_name = sarscape_safe_name(args.region_name)
    except ValueError as exc:
        logger.error("invalid region name %r: %s", args.region_name, exc)
        return _EXIT_ERROR

    region_id = args.region_id or f"region_{region_safe_name}"
    expected_polarization = (
        Polarization(args.expected_polarization) if args.expected_polarization else None
    )

    scene_report = check_scene_collection(
        scenes,
        require_urls=args.require_urls,
        expected_polarization=expected_polarization,
    )

    orbit_report = None
    if args.orbit_dir is not None:
        try:
            orbit_files = scan_orbit_directory(args.orbit_dir)
        except InsarPrepError as exc:
            logger.error("failed to scan orbit directory %s: %s", args.orbit_dir, exc)
            return _EXIT_ERROR
        orbit_report = match_orbits_for_scenes(scenes, orbit_files)

    report = build_data_preparation_report(
        region_id=region_id,
        region_safe_name=region_safe_name,
        scene_check_report=scene_report,
        orbit_match_report=orbit_report,
    )
    output = save_report(report, args.output_root)
    logger.info(
        "wrote data preparation report: %s and %s",
        output.json_path,
        output.markdown_path,
    )
    # User-facing confirmation on stdout (no print(); Ruff T20 stays satisfied).
    sys.stdout.write(
        "Data preparation report written:\n"
        f"JSON: {output.json_path}\n"
        f"Markdown: {output.markdown_path}\n"
    )
    return _EXIT_OK
