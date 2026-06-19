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
from typing import TYPE_CHECKING

from pydantic import ValidationError

from insar_prep.core.enums import DemDataset, Polarization, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError, InsarPrepError
from insar_prep.core.logging import get_logger
from insar_prep.core.naming import sarscape_safe_name
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.processing.aoi_import import load_aoi_from_geojson, load_aoi_from_wkt
from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
from insar_prep.providers.dem import (
    DemProvider,
    create_dem_conversion_plan,
    create_dem_request_plan,
    validate_dem_conversion_plan,
    validate_dem_request_plan,
)
from insar_prep.providers.gacos import (
    check_gacos_products,
    create_gacos_request_plan,
    validate_gacos_request_plan,
)
from insar_prep.providers.orbit import match_orbits_for_scenes, scan_orbit_directory
from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.reporting.generator import build_data_preparation_report, save_report
from insar_prep.reporting.manifest import (
    build_manifest_rows,
    manifest_path_for,
    write_manifest_csv,
)
from insar_prep.reporting.warnings import (
    build_warning_rows,
    warnings_path_for,
    write_warnings_csv,
)

if TYPE_CHECKING:
    from insar_prep.core.models import Aoi

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
    parser.add_argument(
        "--dem-plan",
        dest="dem_plan",
        action="store_true",
        help="Also build an offline DEM request + conversion plan (requires an AOI).",
    )
    # Processing AOI source. The three flags are mutually exclusive; argparse
    # rejects any combination with exit code 2. All expect EPSG:4326 lon/lat.
    aoi_group = parser.add_mutually_exclusive_group()
    aoi_group.add_argument(
        "--bbox",
        dest="bbox",
        nargs=4,
        type=float,
        default=None,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Processing AOI bounds in degrees: WEST SOUTH EAST NORTH (EPSG:4326).",
    )
    aoi_group.add_argument(
        "--aoi-geojson",
        dest="aoi_geojson",
        default=None,
        metavar="PATH",
        help=(
            "Processing AOI from a GeoJSON file (EPSG:4326 lon/lat; Polygon/"
            "MultiPolygon, Feature, or FeatureCollection)."
        ),
    )
    aoi_group.add_argument(
        "--aoi-wkt",
        dest="aoi_wkt",
        default=None,
        metavar="WKT",
        help="Processing AOI from a WKT string (EPSG:4326 lon/lat; POLYGON or MULTIPOLYGON).",
    )
    parser.add_argument(
        "--dem-dataset",
        dest="dem_dataset",
        default=DemDataset.COP30.value,
        choices=[member.value for member in DemDataset],
        help="DEM dataset to plan for (default: COP30).",
    )
    parser.add_argument(
        "--dem-provider",
        dest="dem_provider",
        default=DemProvider.OPENTOPOGRAPHY.value,
        choices=[member.value for member in DemProvider],
        help="Planned DEM provider (default: OPENTOPOGRAPHY).",
    )
    parser.add_argument(
        "--dem-buffer",
        dest="dem_buffer",
        type=float,
        default=0.05,
        help="DEM request bbox buffer in degrees (default: 0.05).",
    )
    parser.add_argument(
        "--source-vertical-datum",
        dest="source_vertical_datum",
        default=VerticalDatum.EGM2008.value,
        choices=[member.value for member in VerticalDatum],
        help="Source DEM vertical datum (default: EGM2008).",
    )
    parser.add_argument(
        "--target-vertical-datum",
        dest="target_vertical_datum",
        default=VerticalDatum.WGS84_ELLIPSOID.value,
        choices=[member.value for member in VerticalDatum],
        help="Target DEM vertical datum (default: WGS84_ELLIPSOID).",
    )
    parser.add_argument(
        "--gacos-plan",
        dest="gacos_plan",
        action="store_true",
        help="Also build an offline GACOS request plan from scene dates (requires an AOI).",
    )
    parser.add_argument(
        "--gacos-buffer",
        dest="gacos_buffer",
        type=float,
        default=0.05,
        help="GACOS request bbox buffer in degrees (default: 0.05).",
    )
    parser.add_argument(
        "--gacos-max-dates-per-batch",
        dest="gacos_max_dates_per_batch",
        type=int,
        default=20,
        help="Maximum acquisition dates per GACOS request batch (default: 20).",
    )
    parser.add_argument(
        "--gacos-import-dir",
        dest="gacos_import_dir",
        default=None,
        help=(
            "Optional local directory of already-downloaded GACOS products "
            "(YYYYMMDD.ztd / YYYYMMDD.ztd.rsc) to check against the expected scene "
            "dates; requires an AOI. Read-only: never downloads, moves, or creates files."
        ),
    )
    return parser


def _resolve_processing_aoi(args: argparse.Namespace) -> Aoi | None:
    """Build a Processing AOI from the chosen AOI source, or ``None`` if none given.

    The three sources (``--bbox`` / ``--aoi-geojson`` / ``--aoi-wkt``) are mutually
    exclusive at the argparse level, so at most one is set here. Any validation
    failure is surfaced as an :class:`InputValidationError` (``AOI001``). The AOI
    bbox comes from the bounds of the imported geometry; the Download AOI buffer
    logic downstream is unchanged.
    """
    if args.bbox is not None:
        west, south, east, north = args.bbox
        try:
            return make_processing_aoi_from_bbox(west, east, south, north)
        except (ValidationError, ValueError) as exc:
            raise InputValidationError(
                f"invalid --bbox {args.bbox}: {exc}", code=ErrorCode.AOI001
            ) from exc
    if args.aoi_geojson is not None:
        return load_aoi_from_geojson(args.aoi_geojson, name=args.region_name)
    if args.aoi_wkt is not None:
        return load_aoi_from_wkt(args.aoi_wkt, name=args.region_name)
    return None


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

    # DEM and GACOS features all need a Processing AOI; build it once from
    # whichever AOI source was given (--bbox / --aoi-geojson / --aoi-wkt, which
    # argparse already enforces to be mutually exclusive).
    processing_aoi = None
    if args.dem_plan or args.gacos_plan or args.gacos_import_dir is not None:
        try:
            processing_aoi = _resolve_processing_aoi(args)
        except InsarPrepError as exc:
            logger.error("invalid Processing AOI: %s", exc)
            return _EXIT_ERROR
        if processing_aoi is None:
            logger.error(
                "--dem-plan/--gacos-plan/--gacos-import-dir require a Processing AOI: pass one "
                "of --bbox WEST SOUTH EAST NORTH, --aoi-geojson PATH, or --aoi-wkt WKT"
            )
            return _EXIT_ERROR

    dem_planning_report = None
    dem_conversion_report = None
    if args.dem_plan:
        try:
            dem_plan = create_dem_request_plan(
                region_id=region_id,
                region_safe_name=region_safe_name,
                processing_aoi=processing_aoi,
                output_root=args.output_root,
                dataset=args.dem_dataset,
                provider=args.dem_provider,
                buffer_degrees=args.dem_buffer,
                source_vertical_datum=VerticalDatum(args.source_vertical_datum),
                target_vertical_datum=VerticalDatum(args.target_vertical_datum),
            )
        except InsarPrepError as exc:
            logger.error("failed to build DEM plan: %s", exc)
            return _EXIT_ERROR
        dem_planning_report = validate_dem_request_plan(dem_plan)
        dem_conversion_report = validate_dem_conversion_plan(create_dem_conversion_plan(dem_plan))

    gacos_plan = None
    gacos_planning_report = None
    if args.gacos_plan:
        try:
            gacos_plan = create_gacos_request_plan(
                region_id=region_id,
                region_safe_name=region_safe_name,
                processing_aoi=processing_aoi,
                scenes=scenes,
                output_root=args.output_root,
                buffer_degrees=args.gacos_buffer,
                max_dates_per_batch=args.gacos_max_dates_per_batch,
            )
        except InsarPrepError as exc:
            logger.error("failed to build GACOS plan: %s", exc)
            return _EXIT_ERROR
        gacos_planning_report = validate_gacos_request_plan(gacos_plan)

    # GACOS import check: compare a local product directory against the expected
    # acquisition dates. Expected dates come from an existing --gacos-plan plan when
    # available, otherwise from a plan built from the scene dates (both need --bbox).
    # Uses the existing read-only checker; no products are downloaded, moved, or created.
    gacos_import_report = None
    if args.gacos_import_dir is not None:
        import_plan = gacos_plan
        if import_plan is None:
            try:
                import_plan = create_gacos_request_plan(
                    region_id=region_id,
                    region_safe_name=region_safe_name,
                    processing_aoi=processing_aoi,
                    scenes=scenes,
                    output_root=args.output_root,
                    buffer_degrees=args.gacos_buffer,
                    max_dates_per_batch=args.gacos_max_dates_per_batch,
                )
            except InsarPrepError as exc:
                logger.error("failed to derive GACOS expected dates: %s", exc)
                return _EXIT_ERROR
        try:
            gacos_import_report = check_gacos_products(
                request_plan=import_plan,
                product_directory=args.gacos_import_dir,
            )
        except InsarPrepError as exc:
            logger.error("failed to check GACOS products in %s: %s", args.gacos_import_dir, exc)
            return _EXIT_ERROR

    report = build_data_preparation_report(
        region_id=region_id,
        region_safe_name=region_safe_name,
        scene_check_report=scene_report,
        orbit_match_report=orbit_report,
        dem_planning_report=dem_planning_report,
        dem_conversion_report=dem_conversion_report,
        gacos_planning_report=gacos_planning_report,
        gacos_import_report=gacos_import_report,
    )
    output = save_report(report, args.output_root)

    # Write a flat manifest.csv and a warnings.csv alongside the JSON + Markdown
    # report, reusing the objects already built above (no re-parsing, re-scanning,
    # or downloads). The manifest is the full inventory; warnings.csv summarizes
    # only the problems.
    try:
        manifest_path = manifest_path_for(output.json_path.parent, region_safe_name)
        manifest_rows = build_manifest_rows(
            region_id=region_id,
            region_safe_name=region_safe_name,
            report=report,
            scenes=scenes,
            scene_check_report=scene_report,
            orbit_match_report=orbit_report,
            dem_planning_report=dem_planning_report,
            dem_conversion_report=dem_conversion_report,
            gacos_planning_report=gacos_planning_report,
            gacos_import_report=gacos_import_report,
            json_report_path=output.json_path,
            markdown_report_path=output.markdown_path,
            manifest_csv_path=manifest_path,
        )
        write_manifest_csv(manifest_path, manifest_rows)

        warnings_path = warnings_path_for(output.json_path.parent, region_safe_name)
        warning_rows = build_warning_rows(
            region_safe_name=region_safe_name,
            scene_check_report=scene_report,
            orbit_match_report=orbit_report,
            dem_planning_report=dem_planning_report,
            dem_conversion_report=dem_conversion_report,
            gacos_planning_report=gacos_planning_report,
            gacos_import_report=gacos_import_report,
        )
        write_warnings_csv(warnings_path, warning_rows)
    except InsarPrepError as exc:
        logger.error("failed to write CSV outputs: %s", exc)
        return _EXIT_ERROR

    logger.info(
        "wrote data preparation report: %s, %s, manifest %s and warnings %s",
        output.json_path,
        output.markdown_path,
        manifest_path,
        warnings_path,
    )
    # User-facing confirmation on stdout (no print(); Ruff T20 stays satisfied).
    sys.stdout.write(
        "Data preparation report written:\n"
        f"JSON: {output.json_path}\n"
        f"Markdown: {output.markdown_path}\n"
        f"Manifest: {manifest_path}\n"
        f"Warnings: {warnings_path}\n"
    )
    return _EXIT_OK
