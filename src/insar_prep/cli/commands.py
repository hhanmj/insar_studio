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
    dataset_source_vertical_datum,
    dem_download_request_from_plan,
    opentopo_demtype,
    resolve_dem_api_key,
    run_dem_conversion,
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
    GACOS_PORTAL_URL,
    GacosEmailSource,
    GacosOutputFormat,
    check_gacos_products,
    clear_stored_gacos_email,
    create_gacos_request_plan,
    extract_gacos_dates_from_scenes,
    import_gacos_products,
    is_valid_email,
    raise_for_missing_download_extra,
    store_gacos_email,
    stored_gacos_email_status,
    validate_gacos_request_plan,
)
from insar_prep.providers.gacos import run_gacos_download as _run_gacos_download
from insar_prep.providers.gacos import run_gacos_request as _run_gacos_request
from insar_prep.providers.gacos.planner import GACOS_REQUESTS_SUBDIR
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


_CONVERT_DATUM_CHOICES = [
    "auto",
    VerticalDatum.WGS84_ELLIPSOID.value,
    VerticalDatum.EGM96.value,
    VerticalDatum.EGM2008.value,
    VerticalDatum.ORTHOMETRIC.value,
]


def add_convert_dem_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``convert-dem`` subcommand (real vertical-datum conversion)."""
    parser = subparsers.add_parser(
        "convert-dem",
        help="Convert a downloaded DEM to a WGS84-ellipsoidal, SARscape-ready DEM.",
        description=(
            "Convert an already-downloaded raw DEM's vertical datum from "
            "orthometric (EGM96/EGM2008) to the WGS84 ellipsoid SARscape expects, "
            "by adding the geoid undulation from the bundled EGM96 grid, and write "
            "it under the SARscape-ready '<region>_dem' ENVI name. Datasets that are "
            "already ellipsoidal (SRTMGL1_E/AW3D30_E) are copied through unchanged. "
            "Use --plan-only to print the planned steps without converting. Real "
            "conversion needs the optional 'convert' extra (rasterio); install it "
            "with 'uv sync --extra convert'. This is local-only: no network, no "
            "credentials."
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
            "Output root: reads <output-root>/<region>/04_dem/raw/, writes the "
            "SARscape-ready DEM under <output-root>/<region>/04_dem/ and results "
            "under <output-root>/dem_convert/."
        ),
    )
    _add_processing_aoi_group(parser)
    parser.add_argument(
        "--dem-dataset",
        dest="dem_dataset",
        default=DemDataset.COP30.value,
        choices=[member.value for member in DemDataset],
        help="DEM dataset that was downloaded (default: COP30); sets the source datum.",
    )
    parser.add_argument(
        "--dem-buffer",
        dest="dem_buffer",
        type=float,
        default=0.05,
        help="DEM request bbox buffer in degrees (default: 0.05); must match download-dem.",
    )
    parser.add_argument(
        "--source-vertical-datum",
        dest="source_vertical_datum",
        default="auto",
        choices=_CONVERT_DATUM_CHOICES,
        help="Source vertical datum (default: auto, inferred from the dataset).",
    )
    parser.add_argument(
        "--target-vertical-datum",
        dest="target_vertical_datum",
        default=VerticalDatum.WGS84_ELLIPSOID.value,
        choices=_CONVERT_DATUM_CHOICES[1:],
        help="Target vertical datum (default: WGS84_ELLIPSOID, SARscape-ready).",
    )
    parser.add_argument(
        "--geoid-grid",
        dest="geoid_grid",
        default=None,
        help=(
            "Optional path to a custom geoid .npz (e.g. an EGM2008 grid built with "
            "scripts/build_geoid_npz.py); defaults to the bundled EGM96 grid."
        ),
    )
    parser.add_argument(
        "--plan-only",
        dest="plan_only",
        action="store_true",
        help="Print the planned conversion steps and exit (no rasterio, no output).",
    )
    return parser


def run_convert_dem(args: argparse.Namespace) -> int:
    """Run ``convert-dem``. --plan-only prints steps; otherwise converts the DEM."""
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

    if args.source_vertical_datum == "auto":
        source_datum = dataset_source_vertical_datum(args.dem_dataset)
        if source_datum is VerticalDatum.UNKNOWN:
            sys.stderr.write(
                f"[{ErrorCode.DEM002.value}] cannot infer the source vertical datum for dataset "
                f"{args.dem_dataset!r}; pass --source-vertical-datum explicitly.\n"
            )
            return _EXIT_ERROR
    else:
        source_datum = VerticalDatum(args.source_vertical_datum)
    target_datum = VerticalDatum(args.target_vertical_datum)

    output_root = Path(args.output_root)
    try:
        request_plan = create_dem_request_plan(
            region_id="",
            region_safe_name=region_safe_name,
            processing_aoi=processing_aoi,
            output_root=output_root,
            dataset=args.dem_dataset,
            buffer_degrees=args.dem_buffer,
            source_vertical_datum=source_datum,
            target_vertical_datum=target_datum,
        )
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    conversion_plan = create_dem_conversion_plan(request_plan)
    report = validate_dem_conversion_plan(conversion_plan)

    sys.stdout.write(
        "DEM conversion plan:\n"
        f"  dataset: {conversion_plan.dataset}\n"
        f"  vertical datum: {source_datum.value} -> {target_datum.value}\n"
        f"  requires geoid: {conversion_plan.requires_geoid}\n"
        f"  raw DEM: {conversion_plan.raw_dem_path}\n"
        f"  SARscape-ready DEM: {conversion_plan.sarscape_ready_dem_path}\n"
    )
    for issue in report.issues:
        sys.stdout.write(f"  [{issue.severity.value}] {issue.code}: {issue.message}\n")
    if report.has_errors:
        sys.stderr.write("DEM conversion plan is invalid; see the issues above.\n")
        return _EXIT_ERROR

    if args.plan_only:
        sys.stdout.write("Plan only: no conversion performed.\n")
        return _EXIT_OK

    if importlib.util.find_spec("rasterio") is None:
        sys.stderr.write(
            f"[{ErrorCode.DEM003.value}] real DEM conversion needs the optional 'convert' extra; "
            "install it with 'uv sync --extra convert' (or pip install rasterio)\n"
        )
        return _EXIT_ERROR

    try:
        summary = run_dem_conversion(
            [conversion_plan], output_root, geoid_grid_path=args.geoid_grid
        )
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    sys.stdout.write(
        f"DEM conversion finished: {summary.summary_line()}.\nResults: {summary.results_path}\n"
    )
    for result in summary.results:
        sys.stdout.write(f"  {result.region_safe_name}: {mask_text(result.message)}\n")
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


def add_gacos_import_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``gacos-import`` subcommand (organize downloaded GACOS products)."""
    parser = subparsers.add_parser(
        "gacos-import",
        help="Extract, organize, and integrity-check manually downloaded GACOS products.",
        description=(
            "GACOS has no public download API, so users request and download "
            "products manually from the GACOS web service. This command takes the "
            "archives/folders you downloaded, extracts .zip/.tar.gz, copies the "
            "YYYYMMDD.ztd / .ztd.rsc / .tif products into the region's GACOS "
            "directory under canonical names, and integrity-checks each date (the "
            ".ztd byte size must equal 4 x WIDTH x FILE_LENGTH from its .rsc). It "
            "never contacts GACOS or stores credentials. Pass --cart to compare the "
            "imported dates against the acquisition dates of a local ASF cart."
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
            "Output root: products land under <output-root>/<region>/05_atmosphere/gacos/requests/."
        ),
    )
    parser.add_argument(
        "--source",
        dest="sources",
        action="append",
        required=True,
        metavar="PATH",
        help="A GACOS archive (.zip/.tar.gz), a folder, or a product file. Repeatable.",
    )
    parser.add_argument(
        "--cart",
        dest="cart",
        default=None,
        help="Optional ASF cart file; its acquisition dates drive the coverage check.",
    )
    parser.add_argument(
        "--move",
        dest="move",
        action="store_true",
        help="Move (instead of copy) loose source product files into the region directory.",
    )
    return parser


def run_gacos_import(args: argparse.Namespace) -> int:
    """Run ``gacos-import``: extract, organize, and integrity-check GACOS products."""
    try:
        region_safe_name = sarscape_safe_name(args.region_name)
    except ValueError as exc:
        logger.error("invalid region name %r: %s", args.region_name, exc)
        return _EXIT_ERROR

    output_directory = Path(args.output_root) / region_safe_name / Path(*GACOS_REQUESTS_SUBDIR)

    expected_dates = None
    if args.cart:
        try:
            scenes = parse_asf_cart_file(args.cart)
        except InsarPrepError as exc:
            sys.stderr.write(f"{exc}\n")
            return _EXIT_ERROR
        expected_dates = extract_gacos_dates_from_scenes(scenes)

    try:
        result = import_gacos_products(
            args.sources,
            output_directory,
            expected_dates=expected_dates,
            move=args.move,
        )
    except (InputValidationError, InsarPrepError) as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    sys.stdout.write(
        "GACOS import:\n"
        f"  output directory: {result.output_directory}\n"
        f"  imported files: {result.summary['imported_file_count']}\n"
        f"  product dates: {result.summary['product_date_count']} "
        f"({result.summary['valid_product_count']} valid)\n"
    )
    if expected_dates is not None:
        sys.stdout.write(
            f"  expected dates: {len(expected_dates)}, "
            f"missing: {result.summary['missing_date_count']}, "
            f"extra: {result.summary['extra_date_count']}\n"
        )
    for issue in result.issues:
        sys.stdout.write(f"  [{issue.severity.value}] {issue.code}: {issue.message}\n")
    return _EXIT_ERROR if result.has_errors else _EXIT_OK


def _parse_utc_time(value: str) -> tuple[int, int]:
    """Parse a ``HH:MM`` (or ``HH``) UTC time-of-day into ``(hour, minute)``."""
    text = value.strip()
    if ":" in text:
        hour_str, _, minute_str = text.partition(":")
    else:
        hour_str, minute_str = text, "0"
    try:
        hour = int(hour_str)
        minute = int(minute_str or "0")
    except ValueError as exc:
        raise InputValidationError(
            f"invalid --time {value!r}; expected HH:MM in UTC", code=ErrorCode.GAC003
        ) from exc
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise InputValidationError(
            f"invalid --time {value!r}; hour 0-23, minute 0-59 (UTC)", code=ErrorCode.GAC003
        )
    return hour, minute


def add_gacos_auth_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``gacos-auth`` subcommand (manage the stored GACOS email)."""
    parser = subparsers.add_parser(
        "gacos-auth",
        help="Manage your stored GACOS delivery email (OS keyring).",
        description=(
            "Store, check, or remove the email address GACOS sends result links to, "
            "in the OS keyring, so 'gacos-request --submit' can use it. The email is "
            "not a password (you may also pass --email directly), but storing it once "
            "keeps it out of shell history. Needs the optional 'download' extra "
            f"(keyring). Register / submit at {GACOS_PORTAL_URL}."
        ),
    )
    parser.add_argument(
        "action",
        choices=["login", "status", "logout"],
        help="login: store the email; status: show whether one is stored; logout: clear it.",
    )
    parser.add_argument(
        "--email",
        dest="email",
        default=None,
        help="Email to store (for 'login'); if omitted you are prompted.",
    )
    return parser


def run_gacos_auth(args: argparse.Namespace) -> int:
    """Run the ``gacos-auth`` subcommand. Returns a process exit code."""
    try:
        if args.action == "login":
            email = args.email if args.email is not None else input("GACOS email: ").strip()
            if not email:
                sys.stderr.write("No email entered; nothing stored.\n")
                return _EXIT_ERROR
            store_gacos_email(email)
            sys.stdout.write("Stored GACOS email in the OS keyring.\n")
            return _EXIT_OK
        if args.action == "status":
            status = stored_gacos_email_status()
            sys.stdout.write(f"Stored GACOS email: {status}\n")
            return _EXIT_OK
        removed = clear_stored_gacos_email()
        sys.stdout.write(
            "Cleared the stored GACOS email.\n" if removed else "No stored GACOS email to clear.\n"
        )
        return _EXIT_OK
    except CredentialError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR


def add_gacos_request_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``gacos-request`` subcommand (submit a real GACOS web request)."""
    parser = subparsers.add_parser(
        "gacos-request",
        help="Submit a real GACOS atmospheric-correction request (dry-run by default).",
        description=(
            "GACOS has no download API: a request is a web-form submission whose "
            "result link is emailed to you. This command builds the request "
            "(bounding box + acquisition dates + UTC time + output format) from a "
            "local ASF cart (or --dates) and, with --submit, POSTs it to the GACOS "
            "web form in <=20-date batches. Dry-run is the default and never touches "
            "the network. --submit needs the optional 'download' extra and your "
            "GACOS email (stored via 'gacos-auth login', $GACOS_EMAIL, or --email). "
            "After submitting, watch your inbox for the download link and fetch it "
            "with 'gacos-download --url'."
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
        help="Output root: a results CSV is written under <output-root>/gacos_request/.",
    )
    _add_processing_aoi_group(parser)
    parser.add_argument(
        "--cart",
        dest="cart",
        default=None,
        help="ASF cart file; its acquisition dates become the GACOS date list.",
    )
    parser.add_argument(
        "--dates",
        dest="dates",
        default=None,
        help="Comma/space-separated YYYYMMDD dates (overrides --cart for the date list).",
    )
    parser.add_argument(
        "--time",
        dest="time",
        default="00:00",
        help="Acquisition time of day in UTC as HH:MM (default: 00:00).",
    )
    parser.add_argument(
        "--output-format",
        dest="output_format",
        default=GacosOutputFormat.GEOTIFF.value,
        choices=[fmt.value for fmt in GacosOutputFormat],
        help="GACOS product format (default: geotiff).",
    )
    parser.add_argument(
        "--email",
        dest="email",
        default=None,
        help="GACOS delivery email (else resolved from keyring / $GACOS_EMAIL).",
    )
    parser.add_argument(
        "--gacos-buffer",
        dest="gacos_buffer",
        type=float,
        default=0.05,
        help="GACOS request bbox buffer in degrees (default: 0.05).",
    )
    parser.add_argument(
        "--max-dates-per-batch",
        dest="max_dates_per_batch",
        type=int,
        default=20,
        help="Maximum dates per submitted batch (1-20; default: 20).",
    )
    parser.add_argument(
        "--submit",
        dest="submit",
        action="store_true",
        help="Actually POST the request to GACOS (default: dry-run preview only).",
    )
    return parser


def _gacos_request_dates(args: argparse.Namespace) -> list | None:
    """Resolve the GACOS date list from --dates or --cart (None on error)."""
    if args.dates:
        from datetime import datetime  # noqa: PLC0415 - local, only needed here

        tokens = [tok for tok in args.dates.replace(",", " ").split() if tok]
        parsed: list = []
        for token in tokens:
            try:
                parsed.append(datetime.strptime(token, "%Y%m%d").date())
            except ValueError:
                sys.stderr.write(
                    f"[{ErrorCode.GAC001.value}] invalid date {token!r}; use YYYYMMDD\n"
                )
                return None
        return sorted(set(parsed))
    if args.cart:
        try:
            scenes = parse_asf_cart_file(args.cart)
        except InsarPrepError as exc:
            sys.stderr.write(f"{exc}\n")
            return None
        return extract_gacos_dates_from_scenes(scenes)
    sys.stderr.write(
        f"[{ErrorCode.GAC001.value}] provide acquisition dates via --cart or --dates\n"
    )
    return None


def run_gacos_request(args: argparse.Namespace) -> int:
    """Run ``gacos-request``. Dry-run previews the batches; --submit POSTs them."""
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

    dates = _gacos_request_dates(args)
    if dates is None:
        return _EXIT_ERROR
    if not dates:
        sys.stderr.write(f"[{ErrorCode.GAC001.value}] no acquisition dates found\n")
        return _EXIT_ERROR

    try:
        hour, minute = _parse_utc_time(args.time)
    except InputValidationError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    request_bbox = processing_aoi.bbox.buffer(args.gacos_buffer)
    output_format = GacosOutputFormat(args.output_format)

    sys.stdout.write(
        "GACOS request:\n"
        f"  region: {region_safe_name}\n"
        f"  bbox (W,S,E,N): {request_bbox.west}, {request_bbox.south}, "
        f"{request_bbox.east}, {request_bbox.north}\n"
        f"  dates: {len(dates)} (UTC {hour:02d}:{minute:02d})\n"
        f"  output format: {output_format.value}\n"
    )

    if not args.submit:
        batches = (len(dates) + args.max_dates_per_batch - 1) // args.max_dates_per_batch
        sys.stdout.write(
            f"Dry-run only: would submit {batches} batch(es) to GACOS. No network access. "
            "Re-run with --submit to POST the request.\n"
        )
        return _EXIT_OK

    try:
        raise_for_missing_download_extra()
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    email = (args.email or "").strip()
    if email and not is_valid_email(email):
        sys.stderr.write(f"[{ErrorCode.GAC003.value}] {email!r} is not a valid email\n")
        return _EXIT_ERROR

    try:
        summary = _run_gacos_request(
            region_safe_name=region_safe_name,
            bbox=request_bbox,
            dates=dates,
            email=email,
            output_root=Path(args.output_root),
            hour=hour,
            minute=minute,
            output_format=output_format,
            email_source=GacosEmailSource.AUTO,
            max_dates_per_batch=args.max_dates_per_batch,
        )
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    sys.stdout.write(f"GACOS request finished: {summary.summary_line()}.\n")
    if summary.results_path is not None:
        sys.stdout.write(f"Results: {summary.results_path}\n")
    for result in summary.results:
        sys.stdout.write(
            f"  batch {result.batch_index}/{result.batch_count}: "
            f"{result.outcome.value} - {mask_text(result.message)}\n"
        )
    if summary.submitted:
        sys.stdout.write(
            "Watch your email for the GACOS download link(s), then run "
            "'insar-prep gacos-download --url <link>'.\n"
        )
    return _EXIT_ERROR if summary.has_failures else _EXIT_OK


def add_gacos_download_subparser(subparsers) -> argparse.ArgumentParser:
    """Register the ``gacos-download`` subcommand (fetch the emailed GACOS archive)."""
    parser = subparsers.add_parser(
        "gacos-download",
        help="Download GACOS result archive(s) from the emailed link and import them.",
        description=(
            "Fetch the GACOS result archive(s) from the download link(s) GACOS "
            "emailed you (after 'gacos-request --submit'), then extract, organize, "
            "and integrity-check the products into the region's GACOS directory "
            "(reusing the same importer as 'gacos-import'). Pass each link with "
            "--url (repeatable) or a file of links with --url-file. Needs the "
            "optional 'download' extra. Pass --cart to check coverage against the "
            "scene dates."
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
            "Output root: products land under <output-root>/<region>/05_atmosphere/gacos/requests/."
        ),
    )
    parser.add_argument(
        "--url",
        dest="urls",
        action="append",
        default=None,
        metavar="URL",
        help="A GACOS result download link (http/https/ftp). Repeatable.",
    )
    parser.add_argument(
        "--url-file",
        dest="url_file",
        default=None,
        help="A text file with one GACOS result link per line.",
    )
    parser.add_argument(
        "--cart",
        dest="cart",
        default=None,
        help="Optional ASF cart file; its acquisition dates drive the coverage check.",
    )
    parser.add_argument(
        "--max-retries",
        dest="max_retries",
        type=int,
        default=3,
        help="Maximum attempts per link on transient failures (default: 3).",
    )
    return parser


def run_gacos_download(args: argparse.Namespace) -> int:
    """Run ``gacos-download``: fetch the emailed archive(s) and import the products."""
    try:
        region_safe_name = sarscape_safe_name(args.region_name)
    except ValueError as exc:
        logger.error("invalid region name %r: %s", args.region_name, exc)
        return _EXIT_ERROR

    urls: list[str] = list(args.urls or [])
    if args.url_file:
        try:
            text = Path(args.url_file).read_text(encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"[{ErrorCode.GAC004.value}] could not read --url-file: {exc}\n")
            return _EXIT_ERROR
        urls.extend(line.strip() for line in text.splitlines() if line.strip())
    if not urls:
        sys.stderr.write(f"[{ErrorCode.GAC004.value}] provide at least one --url or a --url-file\n")
        return _EXIT_ERROR

    try:
        raise_for_missing_download_extra()
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    expected_dates = None
    if args.cart:
        try:
            scenes = parse_asf_cart_file(args.cart)
        except InsarPrepError as exc:
            sys.stderr.write(f"{exc}\n")
            return _EXIT_ERROR
        expected_dates = extract_gacos_dates_from_scenes(scenes)

    output_directory = Path(args.output_root) / region_safe_name / Path(*GACOS_REQUESTS_SUBDIR)
    try:
        summary = _run_gacos_download(
            urls,
            output_directory,
            expected_dates=expected_dates,
            email_source=GacosEmailSource.AUTO,
            max_retries=args.max_retries,
        )
    except InsarPrepError as exc:
        sys.stderr.write(f"{exc}\n")
        return _EXIT_ERROR

    sys.stdout.write(f"GACOS download finished: {summary.summary_line()}.\n")
    if summary.results_path is not None:
        sys.stdout.write(f"Results: {summary.results_path}\n")
    if summary.import_result is not None:
        sys.stdout.write(
            f"  imported into: {summary.import_result.output_directory}\n"
            f"  product dates: {summary.import_result.summary['product_date_count']} "
            f"({summary.import_result.summary['valid_product_count']} valid)\n"
        )
        for issue in summary.import_result.issues:
            sys.stdout.write(f"  [{issue.severity.value}] {issue.code}: {issue.message}\n")
    has_import_errors = summary.import_result.has_errors if summary.import_result else False
    return _EXIT_ERROR if (summary.has_failures or has_import_errors) else _EXIT_OK


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
