"""CLI subcommands for insar-prep (Task 015).

The ``prepare`` command wires the offline pipeline:
ASF cart parser -> scene consistency check -> data preparation report -> save.

Strictly offline: no GUI, no network, no downloads, no ASF/OpenTopography/GACOS
API calls, no credentials, and no real DEM conversion. No ``print()`` is used
(Ruff ``T20``); user-facing text goes through argparse help or the logger.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from insar_prep.core.enums import DemDataset, Polarization, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError, InputValidationError, InsarPrepError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.naming import sarscape_safe_name
from insar_prep.gui import PYSIDE6_MISSING_MESSAGE
from insar_prep.processing.aoi import make_processing_aoi_from_bbox
from insar_prep.processing.aoi_import import load_aoi_from_geojson, load_aoi_from_wkt
from insar_prep.processing.aoi_vector import (
    load_aoi_from_file,
    load_aoi_from_kml,
    load_aoi_from_kmz,
    load_aoi_from_shapefile,
)
from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
from insar_prep.providers.asf.credentials import (
    EARTHDATA_TOKEN_ENV,
    EARTHDATA_TOKEN_URL,
    CredentialSource,
    clear_stored_credentials,
    resolve_credentials,
    store_login,
    store_token,
    stored_credential_status,
)
from insar_prep.providers.asf.download_plan import (
    SLC_SUBDIR,
    build_asf_download_plan,
    write_asf_download_plan,
)
from insar_prep.providers.asf.downloader import (
    DownloadOutcome,
    DownloadResult,
    RealAsfDownloader,
    download_requests_from_scenes,
)
from insar_prep.providers.asf.scene_parser import deduplicate_scenes
from insar_prep.providers.dem import (
    DemDownloadOutcome,
    DemKeySource,
    DemProvider,
    RealDemDownloader,
    create_dem_conversion_plan,
    create_dem_request_plan,
    dem_download_request_from_plan,
    opentopo_demtype,
    resolve_dem_api_key,
    run_dem_download,
    validate_dem_conversion_plan,
    validate_dem_request_plan,
)
from insar_prep.providers.dem.credentials import (
    OPENTOPO_API_KEY_ENV,
    OPENTOPO_API_KEY_URL,
    clear_stored_api_key,
    opentopo_api_key_guidance,
    store_api_key,
    stored_api_key_status,
)
from insar_prep.providers.gacos import (
    check_gacos_products,
    create_gacos_request_plan,
    validate_gacos_request_plan,
)
from insar_prep.providers.orbit import match_orbits_for_scenes, scan_orbit_directory
from insar_prep.quality.scene_checks import check_scene_collection
from insar_prep.reporting.generator import build_data_preparation_report, save_report
from insar_prep.reporting.html import html_report_path_for, save_report_html
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
    # Processing AOI source. These flags are mutually exclusive; argparse rejects
    # any combination with exit code 2. All expect EPSG:4326 lon/lat.
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
    aoi_group.add_argument(
        "--aoi-shp",
        dest="aoi_shp",
        default=None,
        metavar="PATH",
        help=(
            "Processing AOI from an ESRI Shapefile (.shp; EPSG:4326 lon/lat, "
            "Polygon/MultiPolygon). A sidecar .prj, if present, must be WGS84 lon/lat."
        ),
    )
    aoi_group.add_argument(
        "--aoi-kml",
        dest="aoi_kml",
        default=None,
        metavar="PATH",
        help="Processing AOI from a KML file (.kml; WGS84 lon/lat; Polygon geometry).",
    )
    aoi_group.add_argument(
        "--aoi-kmz",
        dest="aoi_kmz",
        default=None,
        metavar="PATH",
        help="Processing AOI from a zipped KML (.kmz; WGS84 lon/lat; Polygon geometry).",
    )
    aoi_group.add_argument(
        "--aoi-file",
        dest="aoi_file",
        default=None,
        metavar="PATH",
        help=(
            "Processing AOI from any supported vector file, auto-detected by "
            "extension (.geojson/.json/.shp/.kml/.kmz; EPSG:4326 lon/lat)."
        ),
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

    The AOI sources (``--bbox`` / ``--aoi-geojson`` / ``--aoi-wkt`` / ``--aoi-shp``
    / ``--aoi-kml`` / ``--aoi-kmz`` / ``--aoi-file``) are mutually exclusive at the
    argparse level, so at most one is set here. Any validation failure is surfaced as an
    :class:`InputValidationError` (``AOI001``). The AOI bbox comes from the bounds
    of the imported geometry; the Download AOI buffer logic downstream is unchanged.
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
    if args.aoi_shp is not None:
        return load_aoi_from_shapefile(args.aoi_shp, name=args.region_name)
    if args.aoi_kml is not None:
        return load_aoi_from_kml(args.aoi_kml, name=args.region_name)
    if args.aoi_kmz is not None:
        return load_aoi_from_kmz(args.aoi_kmz, name=args.region_name)
    if args.aoi_file is not None:
        return load_aoi_from_file(args.aoi_file, name=args.region_name)
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
                "of --bbox WEST SOUTH EAST NORTH, --aoi-geojson PATH, --aoi-wkt WKT, "
                "--aoi-shp PATH, --aoi-kml PATH, --aoi-kmz PATH, or --aoi-file PATH"
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
    # Write a self-contained HTML view alongside the JSON + Markdown report,
    # reusing the same report object (no business logic is re-run).
    html_path = html_report_path_for(output.json_path.parent, region_safe_name)
    save_report_html(report, html_path)

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
        "wrote data preparation report: %s, %s, %s, manifest %s and warnings %s",
        output.json_path,
        output.markdown_path,
        html_path,
        manifest_path,
        warnings_path,
    )
    # User-facing confirmation on stdout (no print(); Ruff T20 stays satisfied).
    sys.stdout.write(
        "Data preparation report written:\n"
        f"JSON: {output.json_path}\n"
        f"Markdown: {output.markdown_path}\n"
        f"HTML: {html_path}\n"
        f"Manifest: {manifest_path}\n"
        f"Warnings: {warnings_path}\n"
    )
    return _EXIT_OK


def add_plan_asf_downloads_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the offline ``plan-asf-downloads`` dry-run subcommand."""
    parser = subparsers.add_parser(
        "plan-asf-downloads",
        help="Plan (dry-run) the ASF SLC downloads implied by a local cart. No network.",
        description=(
            "Offline dry-run: read a local ASF cart, and write an ASF SLC download "
            "*plan* (JSON + CSV) listing the expected filenames and intended local "
            "paths. It never downloads data, contacts ASF/Earthdata, or reads "
            "credentials, and no account is required to run it."
        ),
    )
    parser.add_argument(
        "--cart",
        required=True,
        help="Path to a local ASF cart file (.py/.txt/.csv/.geojson/.json).",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        required=True,
        help="Directory for the plan; outputs go under <output-dir>/asf_download_plan/.",
    )
    parser.add_argument(
        "--region-name",
        dest="region_name",
        default=None,
        help="Optional human-readable region name (recorded as a SARscape-safe name).",
    )
    parser.add_argument(
        "--require-urls",
        dest="require_urls",
        action="store_true",
        help="Exit non-zero if any scene has no download URL (still writes the plan).",
    )
    return parser


def run_plan_asf_downloads(args: argparse.Namespace) -> int:
    """Run the offline ASF download dry-run planner. Returns a process exit code."""
    cart_path = Path(args.cart)
    try:
        scenes = parse_asf_cart_file(cart_path)
    except InsarPrepError as exc:
        logger.error("failed to parse ASF cart %s: %s", cart_path, exc)
        return _EXIT_ERROR

    # One plan entry per unique granule (a cart may list a granule more than once).
    unique_scenes, _duplicates = deduplicate_scenes(scenes)

    region_safe_name = ""
    if args.region_name:
        try:
            region_safe_name = sarscape_safe_name(args.region_name)
        except ValueError as exc:
            logger.error("invalid region name %r: %s", args.region_name, exc)
            return _EXIT_ERROR

    plan = build_asf_download_plan(
        scenes=unique_scenes,
        output_dir=args.output_dir,
        source_cart=cart_path,
        region_safe_name=region_safe_name,
    )
    try:
        json_path, csv_path = write_asf_download_plan(plan, args.output_dir)
    except InsarPrepError as exc:
        logger.error("failed to write ASF download plan: %s", exc)
        return _EXIT_ERROR

    logger.info(
        "wrote ASF download plan: %s and %s (%d scenes, %d planned, %d missing url)",
        json_path,
        csv_path,
        plan.scene_count,
        plan.planned_count,
        plan.missing_url_count,
    )
    # User-facing confirmation on stdout (no print(); Ruff T20 stays satisfied).
    sys.stdout.write(f"ASF download plan written:\nJSON: {json_path}\nCSV: {csv_path}\n")
    # Real download is not implemented; this is a plan only.
    if args.require_urls and plan.missing_url_count > 0:
        logger.error(
            "%d scene(s) have no download URL and --require-urls was set",
            plan.missing_url_count,
        )
        return _EXIT_ERROR
    return _EXIT_OK


_DOWNLOAD_RESULT_COLUMNS = [
    "scene_id",
    "outcome",
    "bytes_written",
    "error_code",
    "message",
]


def add_download_asf_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``download-asf`` subcommand (dry-run default; real opt-in)."""
    parser = subparsers.add_parser(
        "download-asf",
        help="Plan or download Sentinel-1 SLCs from a cart (dry-run by default).",
        description=(
            "Write an ASF SLC download plan (JSON + CSV) and, with "
            "--download-mode real, fetch the SLCs from ASF using NASA Earthdata "
            "credentials. Use --download-mode verify for a fast network preflight "
            "that checks the whole credential + ASF + redirect chain without "
            "downloading the multi-GB archives. Dry-run is the default and never "
            "touches the network. verify/real require the optional 'download' extra. "
            "Set up credentials once with 'insar-prep auth login' (saved in the OS "
            "keyring) or the GUI 'Earthdata Login' dialog; the default "
            f"--credential-source auto then falls back to ${EARTHDATA_TOKEN_ENV} or "
            "~/.netrc. A password is never accepted on the command line."
        ),
    )
    parser.add_argument(
        "--cart",
        required=True,
        help="Path to a local ASF cart file (.py/.txt/.csv/.geojson/.json).",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        required=True,
        help=(
            "Output root: the plan goes under <output-dir>/asf_download_plan/ and, "
            "in real mode, SLCs under <output-dir>/02_slc/."
        ),
    )
    parser.add_argument(
        "--download-mode",
        dest="download_mode",
        default="dry-run",
        choices=["dry-run", "verify", "real"],
        help=(
            "dry-run (default, offline plan only), verify (network preflight: a "
            "small Range request per scene confirms credentials + ASF reachability "
            "without downloading the multi-GB SLCs), or real (fetch the SLCs). "
            "verify and real need credentials and the optional 'download' extra."
        ),
    )
    parser.add_argument(
        "--credential-source",
        dest="credential_source",
        default=CredentialSource.AUTO.value,
        choices=[member.value for member in CredentialSource],
        help=(
            "Earthdata credential source for real download: auto (keyring -> "
            f"${EARTHDATA_TOKEN_ENV} -> ~/.netrc), keyring, env-token, or netrc. "
            "Default: auto. Configure once with 'insar-prep auth login' or the GUI."
        ),
    )
    parser.add_argument(
        "--max-retries",
        dest="max_retries",
        type=int,
        default=3,
        help="Maximum attempts per scene on transient failures (default: 3).",
    )
    parser.add_argument(
        "--region-name",
        dest="region_name",
        default=None,
        help="Optional human-readable region name (recorded as a SARscape-safe name).",
    )
    parser.add_argument(
        "--require-urls",
        dest="require_urls",
        action="store_true",
        help="Exit non-zero if any scene has no download URL (still writes the plan).",
    )
    return parser


def _write_download_results(output_dir: Path, results: list[DownloadResult]) -> Path:
    """Write a credential-safe per-scene results CSV. Returns its path."""
    plan_dir = output_dir / "asf_download_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "asf_download_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_DOWNLOAD_RESULT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "scene_id": mask_text(result.scene_id),
                    "outcome": result.outcome.value,
                    "bytes_written": result.bytes_written,
                    "error_code": result.error_code or "",
                    "message": mask_text(result.message),
                }
            )
    return results_path


def run_download_asf(args: argparse.Namespace) -> int:
    """Run ``download-asf``. Dry-run writes a plan; real fetches SLCs."""
    cart_path = Path(args.cart)
    try:
        scenes = parse_asf_cart_file(cart_path)
    except InsarPrepError as exc:
        logger.error("failed to parse ASF cart %s: %s", cart_path, exc)
        return _EXIT_ERROR

    unique_scenes, _duplicates = deduplicate_scenes(scenes)

    region_safe_name = ""
    if args.region_name:
        try:
            region_safe_name = sarscape_safe_name(args.region_name)
        except ValueError as exc:
            logger.error("invalid region name %r: %s", args.region_name, exc)
            return _EXIT_ERROR

    output_dir = Path(args.output_dir)
    plan = build_asf_download_plan(
        scenes=unique_scenes,
        output_dir=output_dir,
        source_cart=cart_path,
        region_safe_name=region_safe_name,
    )
    try:
        json_path, csv_path = write_asf_download_plan(plan, output_dir)
    except InsarPrepError as exc:
        logger.error("failed to write ASF download plan: %s", exc)
        return _EXIT_ERROR
    sys.stdout.write(f"ASF download plan written:\nJSON: {json_path}\nCSV: {csv_path}\n")

    if args.require_urls and plan.missing_url_count > 0:
        logger.error(
            "%d scene(s) have no download URL and --require-urls was set",
            plan.missing_url_count,
        )
        return _EXIT_ERROR

    if args.download_mode == "dry-run":
        sys.stdout.write(
            "Dry-run only: no network access, no SLCs downloaded. Re-run with "
            "--download-mode verify (network preflight) or --download-mode real "
            "(fetch the SLCs).\n"
        )
        return _EXIT_OK

    # --- Network paths (verify / real): both need credentials + the extra. ---
    verify_only = args.download_mode == "verify"
    if importlib.util.find_spec("requests") is None:
        action = "network verify" if verify_only else "real download"
        sys.stderr.write(
            f"[{ErrorCode.DL004.value}] {action} needs the optional 'download' extra; "
            "install it with 'uv sync --extra download' (or pip install requests)\n"
        )
        return _EXIT_ERROR

    try:
        resolved = resolve_credentials(CredentialSource(args.credential_source))
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    requests_to_run = download_requests_from_scenes(unique_scenes, slc_dir=output_dir / SLC_SUBDIR)
    if not requests_to_run:
        action = "verify" if verify_only else "download"
        logger.error("no scenes with a download URL; nothing to %s", action)
        return _EXIT_ERROR

    downloader = RealAsfDownloader(resolved=resolved, max_retries=args.max_retries)
    results: list[DownloadResult] = []
    for request in requests_to_run:
        result = downloader.verify(request) if verify_only else downloader.download(request)
        results.append(result)
        logger.info(
            "scene %s: %s (%d bytes)%s",
            result.scene_id,
            result.outcome.value,
            result.bytes_written,
            f" [{result.error_code}]" if result.error_code else "",
        )

    results_path = _write_download_results(output_dir, results)

    counts = {outcome: 0 for outcome in DownloadOutcome}
    for result in results:
        counts[result.outcome] += 1

    if verify_only:
        sys.stdout.write(
            "ASF network verify finished: "
            f"{counts[DownloadOutcome.VERIFIED]} verified, "
            f"{counts[DownloadOutcome.FAILED]} failed.\n"
            f"Results: {results_path}\n"
        )
        return _EXIT_ERROR if counts[DownloadOutcome.FAILED] else _EXIT_OK

    sys.stdout.write(
        "ASF download finished: "
        f"{counts[DownloadOutcome.SUCCESS]} downloaded, "
        f"{counts[DownloadOutcome.SKIPPED]} skipped, "
        f"{counts[DownloadOutcome.FAILED]} failed, "
        f"{counts[DownloadOutcome.INTERRUPTED]} interrupted.\n"
        f"Results: {results_path}\n"
    )

    if counts[DownloadOutcome.FAILED] or counts[DownloadOutcome.INTERRUPTED]:
        return _EXIT_ERROR
    return _EXIT_OK


def _add_processing_aoi_group(parser: argparse.ArgumentParser) -> None:
    """Add the mutually exclusive Processing AOI source flags to ``parser``.

    Mirrors the ``prepare`` AOI flags so ``download-dem`` accepts exactly the same
    inputs and reuses :func:`_resolve_processing_aoi`. All expect EPSG:4326 lon/lat.
    """
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
        help="Processing AOI from a GeoJSON file (EPSG:4326 lon/lat).",
    )
    aoi_group.add_argument(
        "--aoi-wkt",
        dest="aoi_wkt",
        default=None,
        metavar="WKT",
        help="Processing AOI from a WKT string (EPSG:4326 lon/lat).",
    )
    aoi_group.add_argument(
        "--aoi-shp",
        dest="aoi_shp",
        default=None,
        metavar="PATH",
        help="Processing AOI from an ESRI Shapefile (.shp; EPSG:4326 lon/lat).",
    )
    aoi_group.add_argument(
        "--aoi-kml",
        dest="aoi_kml",
        default=None,
        metavar="PATH",
        help="Processing AOI from a KML file (.kml; WGS84 lon/lat).",
    )
    aoi_group.add_argument(
        "--aoi-kmz",
        dest="aoi_kmz",
        default=None,
        metavar="PATH",
        help="Processing AOI from a zipped KML (.kmz; WGS84 lon/lat).",
    )
    aoi_group.add_argument(
        "--aoi-file",
        dest="aoi_file",
        default=None,
        metavar="PATH",
        help="Processing AOI from any supported vector file, auto-detected by extension.",
    )


def add_download_dem_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``download-dem`` subcommand (dry-run default; real opt-in)."""
    parser = subparsers.add_parser(
        "download-dem",
        help="Plan or download a DEM for an AOI from OpenTopography (dry-run by default).",
        description=(
            "Build a DEM request plan for a Processing AOI and, with "
            "--download-mode real, download the DEM raster from the OpenTopography "
            "Global DEM API. Use --download-mode verify for a fast preflight (a tiny "
            "sub-tile) that confirms the API key works without fetching the full DEM. "
            "Dry-run is the default and never touches the network. verify/real require "
            "the optional 'download' extra and a personal OpenTopography API key: each "
            "user supplies their OWN free key (no key is bundled), stored once with "
            "'insar-prep dem-auth login' (OS keyring) or via the "
            f"${OPENTOPO_API_KEY_ENV} environment variable. Get a free key at "
            f"{OPENTOPO_API_KEY_URL}."
        ),
    )
    parser.add_argument(
        "--region-name",
        dest="region_name",
        required=True,
        help="Region name (normalized to a SARscape-safe name; used in output paths).",
    )
    parser.add_argument(
        "--output-root",
        dest="output_root",
        required=True,
        help=(
            "Output root: the DEM lands under "
            "<output-root>/<region>/04_dem/raw/ and results under "
            "<output-root>/dem_download/."
        ),
    )
    _add_processing_aoi_group(parser)
    parser.add_argument(
        "--dem-dataset",
        dest="dem_dataset",
        default=DemDataset.COP30.value,
        choices=[member.value for member in DemDataset],
        help="DEM dataset to fetch (default: COP30). USER_LOCAL is not downloadable.",
    )
    parser.add_argument(
        "--dem-buffer",
        dest="dem_buffer",
        type=float,
        default=0.05,
        help="DEM request bbox buffer in degrees (default: 0.05).",
    )
    parser.add_argument(
        "--download-mode",
        dest="download_mode",
        default="dry-run",
        choices=["dry-run", "verify", "real"],
        help=(
            "dry-run (default, offline plan only), verify (preflight: fetch a tiny "
            "sub-tile to confirm the API key + endpoint), or real (download the DEM). "
            "verify and real need the optional 'download' extra and an API key."
        ),
    )
    parser.add_argument(
        "--api-key-source",
        dest="api_key_source",
        default=DemKeySource.AUTO.value,
        choices=[member.value for member in DemKeySource],
        help=(
            "OpenTopography API-key source for verify/real: auto (keyring -> "
            f"${OPENTOPO_API_KEY_ENV}), keyring, or env. Default: auto. "
            "Configure once with 'insar-prep dem-auth login'."
        ),
    )
    parser.add_argument(
        "--max-retries",
        dest="max_retries",
        type=int,
        default=3,
        help="Maximum attempts on transient failures (default: 3).",
    )
    return parser


def run_download_dem(args: argparse.Namespace) -> int:
    """Run ``download-dem``. Dry-run plans only; real fetches the DEM."""
    try:
        region_safe_name = sarscape_safe_name(args.region_name)
    except ValueError as exc:
        logger.error("invalid region name %r: %s", args.region_name, exc)
        return _EXIT_ERROR

    try:
        processing_aoi = _resolve_processing_aoi(args)
    except (InputValidationError, InsarPrepError) as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR
    if processing_aoi is None:
        sys.stderr.write(
            f"[{ErrorCode.AOI001.value}] a Processing AOI is required; pass one of "
            "--bbox WEST SOUTH EAST NORTH, --aoi-geojson PATH, --aoi-wkt WKT, "
            "--aoi-shp PATH, --aoi-kml PATH, --aoi-kmz PATH, or --aoi-file PATH\n"
        )
        return _EXIT_ERROR

    output_root = Path(args.output_root)
    try:
        plan = create_dem_request_plan(
            region_id="",
            region_safe_name=region_safe_name,
            processing_aoi=processing_aoi,
            output_root=output_root,
            dataset=args.dem_dataset,
            buffer_degrees=args.dem_buffer,
        )
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    report = validate_dem_request_plan(plan)
    if report.has_errors:
        for issue in report.issues:
            logger.error("DEM plan issue %s: %s", issue.code, issue.message)
        sys.stderr.write("DEM request plan is invalid; see the logged issues.\n")
        return _EXIT_ERROR

    bbox = plan.request_bbox
    demtype = opentopo_demtype(args.dem_dataset)
    sys.stdout.write(
        "DEM request plan:\n"
        f"  dataset: {plan.dataset} (OpenTopography demtype: {demtype or 'N/A'})\n"
        f"  bbox (W,S,E,N): {bbox.west}, {bbox.south}, {bbox.east}, {bbox.north}\n"
        f"  destination: {plan.raw_dem_path}\n"
    )

    if args.download_mode == "dry-run":
        sys.stdout.write(
            "Dry-run only: no network access, no DEM downloaded. Re-run with "
            "--download-mode verify (preflight) or --download-mode real (download).\n"
        )
        return _EXIT_OK

    if demtype is None:
        sys.stderr.write(
            f"[{ErrorCode.DEM001.value}] dataset {plan.dataset!r} cannot be downloaded "
            "from OpenTopography; choose a global dataset (e.g. COP30) or supply the DEM "
            "locally (USER_LOCAL).\n"
        )
        return _EXIT_ERROR

    verify_only = args.download_mode == "verify"
    if importlib.util.find_spec("requests") is None:
        action = "preflight" if verify_only else "real download"
        sys.stderr.write(
            f"[{ErrorCode.DEM005.value}] DEM {action} needs the optional 'download' extra; "
            "install it with 'uv sync --extra download' (or pip install requests)\n"
        )
        return _EXIT_ERROR

    try:
        resolved = resolve_dem_api_key(DemKeySource(args.api_key_source))
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n\n{opentopo_api_key_guidance()}\n")
        return _EXIT_ERROR

    if verify_only:
        downloader = RealDemDownloader(resolved=resolved, max_retries=args.max_retries)
        request = dem_download_request_from_plan(plan)
        result = downloader.verify(request)
        sys.stdout.write(f"DEM preflight: {result.outcome.value} ({mask_text(result.message)})\n")
        return _EXIT_OK if result.outcome is DemDownloadOutcome.VERIFIED else _EXIT_ERROR

    downloader = RealDemDownloader(resolved=resolved, max_retries=args.max_retries)
    summary = run_dem_download([plan], output_root, downloader=downloader)
    sys.stdout.write(
        f"DEM download finished: {summary.summary_line()}.\nResults: {summary.results_path}\n"
    )
    return _EXIT_ERROR if summary.has_failures else _EXIT_OK


def add_dem_auth_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``dem-auth`` subcommand (manage the OpenTopography API key)."""
    parser = subparsers.add_parser(
        "dem-auth",
        help="Manage your stored OpenTopography API key (OS keyring).",
        description=(
            "Store, check, or remove your personal OpenTopography API key in the OS "
            "keyring so 'download-dem --download-mode real' can use it. Each user "
            "supplies their OWN free key (none is bundled, to avoid sharing a rate "
            "limit). The key is never accepted as a flag; 'dem-auth login' prompts "
            f"without echo. Get a free key at {OPENTOPO_API_KEY_URL}. Needs the "
            "optional 'download' extra (keyring)."
        ),
    )
    parser.add_argument(
        "action",
        choices=["login", "status", "logout"],
        help="login: store the API key; status: show whether one is stored; logout: clear it.",
    )
    parser.add_argument(
        "--key-stdin",
        dest="key_stdin",
        action="store_true",
        help="Read the API key from stdin instead of prompting (for 'login').",
    )
    return parser


def run_dem_auth(args: argparse.Namespace) -> int:
    """Run the ``dem-auth`` subcommand. Returns a process exit code."""
    try:
        if args.action == "login":
            if args.key_stdin:
                api_key = sys.stdin.readline().strip()
            else:
                sys.stdout.write(opentopo_api_key_guidance() + "\n\n")
                api_key = getpass.getpass("Paste OpenTopography API key: ").strip()
            if not api_key:
                sys.stderr.write("No API key entered; nothing stored.\n")
                return _EXIT_ERROR
            store_api_key(api_key)
            sys.stdout.write("Stored OpenTopography API key in the OS keyring.\n")
            return _EXIT_OK
        if args.action == "status":
            status = stored_api_key_status()
            sys.stdout.write(f"Stored OpenTopography API key: {status}\n")
            if status == "none":
                sys.stdout.write("\n" + opentopo_api_key_guidance() + "\n")
            return _EXIT_OK
        removed = clear_stored_api_key()
        sys.stdout.write(
            "Cleared the stored OpenTopography API key.\n"
            if removed
            else "No stored OpenTopography API key to clear.\n"
        )
        return _EXIT_OK
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR


def add_auth_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``auth`` subcommand (manage stored Earthdata credentials)."""
    parser = subparsers.add_parser(
        "auth",
        help="Manage stored NASA Earthdata credentials (OS keyring).",
        description=(
            "Store, check, or remove NASA Earthdata Login credentials in the OS "
            "keyring (Windows Credential Manager / macOS Keychain / Linux Secret "
            "Service) so 'download-asf --download-mode real' can use them. A password "
            "is never accepted as a flag; 'auth login' prompts without echo. Needs the "
            "optional 'download' extra (keyring)."
        ),
    )
    parser.add_argument(
        "action",
        choices=["login", "status", "logout"],
        help="login: store a token or username/password; status: show it; logout: clear it.",
    )
    parser.add_argument(
        "--token-stdin",
        dest="token_stdin",
        action="store_true",
        help="Read the Earthdata token from stdin instead of prompting (for 'login').",
    )
    parser.add_argument(
        "--username",
        dest="username",
        default=None,
        help="Earthdata username for 'login' (the password is then prompted without echo).",
    )
    parser.add_argument(
        "--test",
        dest="test_connection",
        action="store_true",
        help="For 'status': perform a live authenticated check against Earthdata (network).",
    )
    return parser


def _auth_login(args: argparse.Namespace) -> int:
    """Store a token or username/password in the OS keyring."""
    if args.username:
        password = getpass.getpass(f"Earthdata password for {args.username}: ")
        store_login(args.username, password)
        sys.stdout.write("Stored Earthdata username/password in the OS keyring.\n")
        return _EXIT_OK

    if args.token_stdin:
        token = sys.stdin.readline().strip()
    else:
        token = getpass.getpass(
            "Paste Earthdata token (leave blank to enter username/password): "
        ).strip()

    if token:
        store_token(token)
        sys.stdout.write("Stored Earthdata token in the OS keyring.\n")
        return _EXIT_OK

    username = input("Earthdata username: ").strip()
    password = getpass.getpass("Earthdata password: ")
    store_login(username, password)
    sys.stdout.write("Stored Earthdata username/password in the OS keyring.\n")
    return _EXIT_OK


def _auth_status(args: argparse.Namespace) -> int:
    """Print what (if anything) is stored, optionally testing it against Earthdata."""
    status = stored_credential_status()
    sys.stdout.write(f"Stored Earthdata credential: {status} (token page: {EARTHDATA_TOKEN_URL})\n")
    if not args.test_connection:
        return _EXIT_OK

    try:
        resolved = resolve_credentials(CredentialSource.AUTO)
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR
    if importlib.util.find_spec("requests") is None:
        sys.stderr.write(
            f"[{ErrorCode.DL004.value}] connection test needs the optional 'download' extra "
            "(requests); install it with 'uv sync --extra download'\n"
        )
        return _EXIT_ERROR
    from insar_prep.providers.asf.downloader import probe_earthdata_auth

    ok, message = probe_earthdata_auth(resolved)
    sys.stdout.write(f"Earthdata connection test: {'OK' if ok else 'FAILED'} ({message})\n")
    return _EXIT_OK if ok else _EXIT_ERROR


def run_auth(args: argparse.Namespace) -> int:
    """Run the ``auth`` subcommand. Returns a process exit code."""
    try:
        if args.action == "login":
            return _auth_login(args)
        if args.action == "status":
            return _auth_status(args)
        # logout
        removed = clear_stored_credentials()
        sys.stdout.write(
            "Cleared stored Earthdata credentials.\n"
            if removed
            else "No stored Earthdata credentials to clear.\n"
        )
        return _EXIT_OK
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR


def add_update_check_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``update-check`` subcommand (check GitHub for a newer release)."""
    parser = subparsers.add_parser(
        "update-check",
        help="Check GitHub for a newer insar-prep release (network, best-effort).",
        description=(
            "Query the project's public GitHub releases and report whether a newer "
            "version is available. Uses only the standard library (no credentials, "
            "no extra dependency). The automatic check that runs after other "
            "commands can be disabled by setting INSAR_NO_UPDATE_CHECK=1."
        ),
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=5.0,
        help="Network timeout in seconds for the GitHub request (default: 5).",
    )
    return parser


def run_update_check(args: argparse.Namespace) -> int:
    """Run the ``update-check`` subcommand. Returns a process exit code."""
    from insar_prep.core.update_check import (
        GITHUB_REPO,
        check_for_update,
        format_update_notice,
        releases_page_url,
    )

    info = check_for_update(timeout=args.timeout)
    if info is None:
        sys.stderr.write(
            "Could not check for updates (offline, rate-limited, or no release "
            f"published yet). See {releases_page_url(GITHUB_REPO)}\n"
        )
        return _EXIT_OK
    if info.update_available:
        sys.stdout.write(format_update_notice(info) + "\n")
    else:
        sys.stdout.write(f"insar-prep is up to date ({info.current_version}).\n")
    return _EXIT_OK


def add_gui_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``gui`` subcommand (PySide6 desktop GUI, beta skeleton)."""
    parser = subparsers.add_parser(
        "gui",
        help="Launch the desktop GUI (beta skeleton; requires the optional 'gui' extra).",
        description=(
            "Launch the insar-prep desktop GUI (beta skeleton). It requires the "
            "optional PySide6 dependency; install it with 'uv sync --extra gui'. The "
            "GUI is offline and read-only: it performs no downloads and runs no "
            "network access."
        ),
    )
    return parser


def run_gui(args: argparse.Namespace) -> int:
    """Launch the PySide6 GUI. Returns a process exit code.

    PySide6 is an optional dependency (the ``gui`` extra). Its availability is
    checked without importing it, so a missing GUI extra yields a clear,
    single-line message and a non-zero exit code instead of a traceback.
    """
    if importlib.util.find_spec("PySide6") is None:
        # User-visible error carries a stable error code (manual section 30).
        sys.stderr.write(f"[{ErrorCode.GUI001.value}] {PYSIDE6_MISSING_MESSAGE}\n")
        return _EXIT_ERROR
    # Imported lazily: this pulls in PySide6, so it must only run once the
    # availability check above has passed.
    from insar_prep.gui.app import launch_gui

    return launch_gui()
