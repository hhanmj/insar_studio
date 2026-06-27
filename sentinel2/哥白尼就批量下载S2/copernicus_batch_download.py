#!/usr/bin/env python3
"""Batch search and download Copernicus/CDSE products with one script.

This script generalizes the reference MSI/OLCI examples into a single tool that
can query and download products from Copernicus Data Space Ecosystem (CDSE)
collections such as SENTINEL-1/2/3/5P/6, CLMS, CCM, LANDSAT, COP-DEM and more.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote

import requests


CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
DEFAULT_SELECT = (
    "Id,Name,ContentType,ContentLength,Online,S3Path,GeoFootprint,ContentDate"
)
DEFAULT_TIMEOUT = 180
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search and batch download Copernicus Data Space Ecosystem products."
        )
    )
    parser.add_argument("--username", default=os.getenv("CDSE_USERNAME"))
    parser.add_argument("--password", default=os.getenv("CDSE_PASSWORD"))
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date in YYYY-MM-DD format (inclusive).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date in YYYY-MM-DD format (inclusive).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory used to store downloaded products and optional manifest.",
    )
    parser.add_argument(
        "--collection",
        action="append",
        help=(
            "Collection name. Repeat this option to query multiple collections, "
            "for example SENTINEL-2 or CLMS."
        ),
    )
    parser.add_argument(
        "--name-contains",
        action="append",
        help="Require product names to contain this text. Repeatable.",
    )
    parser.add_argument(
        "--product-type",
        action="append",
        help=(
            "Filter by official productType attribute, for example S2MSI2A, "
            "OL_1_EFR___ or GRD."
        ),
    )
    parser.add_argument(
        "--cloud-cover-max",
        type=float,
        help="Apply cloudCover <= value. Useful for collections that expose cloudCover.",
    )
    parser.add_argument(
        "--geojson",
        help=(
            "Path to a GeoJSON polygon or multipolygon. The first polygon exterior "
            "ring is used for OData geographic filtering."
        ),
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Use a bounding box instead of GeoJSON.",
    )
    parser.add_argument(
        "--odata-filter",
        action="append",
        help=(
            "Raw OData filter fragment appended with AND. Repeat this option for "
            "advanced collection-specific filters."
        ),
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Search page size, 1-{MAX_PAGE_SIZE}. Default: {DEFAULT_PAGE_SIZE}.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="Stop after collecting this many search results.",
    )
    parser.add_argument(
        "--order-by",
        default="ContentDate/Start asc",
        help="OData order by clause. Default: 'ContentDate/Start asc'.",
    )
    parser.add_argument(
        "--manifest",
        help="Optional path to save search results as .csv or .json.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only search and print results, do not download files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing finished files.",
    )
    parser.add_argument(
        "--use-zip-endpoint",
        action="store_true",
        help=(
            "Download from /$zip instead of /$value. Mainly useful for supported "
            "Sentinel-1 native compressed products."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024 * 1024,
        help="Download chunk size in bytes. Default: 1048576.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT}.",
    )
    parser.add_argument(
        "--show-url",
        action="store_true",
        help="Print the final search URL and filter before execution.",
    )
    args = parser.parse_args()

    if args.page_size < 1 or args.page_size > MAX_PAGE_SIZE:
        parser.error(f"--page-size must be between 1 and {MAX_PAGE_SIZE}")

    if not args.list_only and (not args.username or not args.password):
        parser.error(
            "Provide --username and --password, or set CDSE_USERNAME/CDSE_PASSWORD."
        )

    return args


def quote_odata(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date {value!r}. Use YYYY-MM-DD.") from exc


def date_to_odata(dt: date) -> str:
    return f"{dt.isoformat()}T00:00:00.000Z"


def load_geojson_polygon(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    geometry = payload
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
        if not features:
            raise SystemExit(f"No features found in GeoJSON: {path}")
        geometry = features[0].get("geometry") or {}
    elif payload.get("type") == "Feature":
        geometry = payload.get("geometry") or {}

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        ring = coordinates[0]
    elif geometry_type == "MultiPolygon":
        ring = coordinates[0][0]
    else:
        raise SystemExit(
            f"Unsupported GeoJSON geometry {geometry_type!r}. Use Polygon or MultiPolygon."
        )

    if len(ring) < 4:
        raise SystemExit(f"Invalid polygon ring in {path}")

    normalized = [[float(lon), float(lat)] for lon, lat in ring]
    if normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return ", ".join(f"{lon} {lat}" for lon, lat in normalized)


def bbox_to_polygon(bbox: Iterable[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    ring = [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat),
    ]
    return ", ".join(f"{lon} {lat}" for lon, lat in ring)


def build_filter(args: argparse.Namespace) -> str:
    clauses: List[str] = []

    if args.collection:
        collection_clauses = [
            f"Collection/Name eq {quote_odata(value)}" for value in args.collection
        ]
        if len(collection_clauses) == 1:
            clauses.append(collection_clauses[0])
        else:
            clauses.append("(" + " or ".join(collection_clauses) + ")")

    if args.name_contains:
        for value in args.name_contains:
            clauses.append(f"contains(Name,{quote_odata(value)})")

    if args.product_type:
        for value in args.product_type:
            clauses.append(
                "Attributes/OData.CSC.StringAttribute/any("
                "att:att/Name eq 'productType' and "
                f"att/OData.CSC.StringAttribute/Value eq {quote_odata(value)})"
            )

    if args.cloud_cover_max is not None:
        clauses.append(
            "Attributes/OData.CSC.DoubleAttribute/any("
            "att:att/Name eq 'cloudCover' and "
            f"att/OData.CSC.DoubleAttribute/Value le {args.cloud_cover_max})"
        )

    polygon = None
    if args.geojson:
        polygon = load_geojson_polygon(Path(args.geojson))
    elif args.bbox:
        polygon = bbox_to_polygon(args.bbox)

    if polygon:
        clauses.append(
            "OData.CSC.Intersects("
            f"area=geography'SRID=4326;POLYGON(({polygon}))')"
        )

    start_date = parse_iso_date(args.start_date)
    end_date = parse_iso_date(args.end_date)
    if end_date < start_date:
        raise SystemExit("--end-date must be later than or equal to --start-date")

    end_exclusive = end_date + timedelta(days=1)
    clauses.append(
        f"ContentDate/Start ge {date_to_odata(start_date)} and "
        f"ContentDate/Start lt {date_to_odata(end_exclusive)}"
    )

    if args.odata_filter:
        clauses.extend(args.odata_filter)

    if not clauses:
        raise SystemExit("At least one filter clause is required.")

    return " and ".join(clauses)


def build_search_params(args: argparse.Namespace, filter_str: str, skip: int) -> Dict[str, Any]:
    return {
        "$filter": filter_str,
        "$top": args.page_size,
        "$skip": skip,
        "$count": "true",
        "$select": DEFAULT_SELECT,
        "$orderby": args.order_by,
    }


def format_content_date(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def write_manifest(records: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    fieldnames = [
        "Id",
        "Name",
        "ContentType",
        "ContentLength",
        "Online",
        "S3Path",
        "ContentDate",
        "GeoFootprint",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in records:
            row = {key: item.get(key) for key in fieldnames}
            row["ContentDate"] = format_content_date(row.get("ContentDate"))
            row["GeoFootprint"] = json.dumps(
                row.get("GeoFootprint"), ensure_ascii=False
            )
            writer.writerow(row)


def print_results(records: List[Dict[str, Any]], max_rows: int = 20) -> None:
    if not records:
        print("No products found.")
        return

    print(f"Found {len(records)} products.")
    print("-" * 120)
    for item in records[:max_rows]:
        product_id = item.get("Id", "")
        name = item.get("Name", "")
        content_type = item.get("ContentType", "")
        print(f"{product_id} | {name} | {content_type}")
    if len(records) > max_rows:
        print(f"... {len(records) - max_rows} more rows omitted")


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime


class CDSEClient:
    def __init__(self, username: str, password: str, timeout: int) -> None:
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.token_bundle: Optional[TokenBundle] = None

    def authenticate(self, force_refresh: bool = False) -> str:
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and self.token_bundle
            and now < self.token_bundle.expires_at - timedelta(seconds=60)
        ):
            return self.token_bundle.access_token

        if (
            not force_refresh
            and self.token_bundle
            and self.token_bundle.refresh_token
            and self._refresh_access_token()
        ):
            return self.token_bundle.access_token

        payload = {
            "client_id": "cdse-public",
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
        }
        response = self.session.post(TOKEN_URL, data=payload, timeout=self.timeout)
        self._raise_for_status(response, "Failed to get access token")
        token_payload = response.json()
        self._store_tokens(token_payload)
        return self.token_bundle.access_token

    def _refresh_access_token(self) -> bool:
        assert self.token_bundle is not None
        payload = {
            "client_id": "cdse-public",
            "refresh_token": self.token_bundle.refresh_token,
            "grant_type": "refresh_token",
        }
        response = self.session.post(TOKEN_URL, data=payload, timeout=self.timeout)
        if not response.ok:
            return False
        self._store_tokens(response.json())
        return True

    def _store_tokens(self, payload: Dict[str, Any]) -> None:
        expires_in = int(payload.get("expires_in", 600))
        self.token_bundle = TokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )

    def authed_stream_get(
        self, url: str, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        token = self.authenticate()
        request_headers = dict(headers or {})
        request_headers["Authorization"] = f"Bearer {token}"
        response = self.session.get(
            url,
            headers=request_headers,
            stream=True,
            allow_redirects=True,
            timeout=(30, self.timeout),
        )
        if response.status_code == 401:
            response.close()
            token = self.authenticate(force_refresh=True)
            request_headers["Authorization"] = f"Bearer {token}"
            response = self.session.get(
                url,
                headers=request_headers,
                stream=True,
                allow_redirects=True,
                timeout=(30, self.timeout),
            )
        return response

    @staticmethod
    def _raise_for_status(response: requests.Response, message: str) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise SystemExit(f"{message}: {detail}") from exc


def search_products(args: argparse.Namespace, filter_str: str) -> List[Dict[str, Any]]:
    session = requests.Session()
    all_items: List[Dict[str, Any]] = []
    skip = 0

    while True:
        params = build_search_params(args, filter_str, skip)
        prepared = requests.Request("GET", CATALOGUE_URL, params=params).prepare()
        if args.show_url:
            print("Search filter:")
            print(filter_str)
            print("Search URL:")
            print(prepared.url)
            print("-" * 120)
            args.show_url = False

        response = session.get(prepared.url, timeout=(30, args.timeout))
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise SystemExit(f"Search request failed: {detail}") from exc

        payload = response.json()
        batch = payload.get("value", [])
        all_items.extend(batch)

        if args.max_items and len(all_items) >= args.max_items:
            return all_items[: args.max_items]

        if len(batch) < args.page_size:
            return all_items

        skip += args.page_size


def guess_extension(item: Dict[str, Any], use_zip_endpoint: bool) -> str:
    if use_zip_endpoint:
        return ".zip"

    content_type = (item.get("ContentType") or "").lower()
    name = (item.get("Name") or "").lower()

    if name.endswith(
        (".zip", ".nc", ".tar", ".tgz", ".gz", ".tif", ".tiff", ".jp2", ".csv", ".xml")
    ):
        return ""
    if "netcdf" in content_type or name.startswith("s5p_"):
        return ".nc"
    if "json" in content_type:
        return ".json"
    if "xml" in content_type:
        return ".xml"
    if "csv" in content_type:
        return ".csv"
    return ".zip"


def build_filename(item: Dict[str, Any], use_zip_endpoint: bool) -> str:
    name = item.get("Name", item.get("Id", "product"))
    return f"{name}{guess_extension(item, use_zip_endpoint)}"


def safe_content_length(item: Dict[str, Any]) -> Optional[int]:
    value = item.get("ContentLength")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def download_product(
    client: CDSEClient,
    item: Dict[str, Any],
    output_dir: Path,
    overwrite: bool,
    use_zip_endpoint: bool,
    chunk_size: int,
) -> str:
    filename = build_filename(item, use_zip_endpoint)
    final_path = output_dir / filename
    temp_path = output_dir / f"{filename}.part"
    remote_size = safe_content_length(item)

    if final_path.exists() and not overwrite:
        if remote_size is None or final_path.stat().st_size == remote_size:
            return "skipped"

    if overwrite:
        if final_path.exists():
            final_path.unlink()
        if temp_path.exists():
            temp_path.unlink()

    download_suffix = "$zip" if use_zip_endpoint else "$value"
    product_id = item["Id"]
    download_url = f"{DOWNLOAD_URL}/Products({product_id})/{download_suffix}"

    resume_at = temp_path.stat().st_size if temp_path.exists() else 0
    headers: Dict[str, str] = {}
    if resume_at > 0:
        headers["Range"] = f"bytes={resume_at}-"

    response = client.authed_stream_get(download_url, headers=headers)

    if resume_at > 0 and response.status_code == 200:
        temp_path.unlink(missing_ok=True)
        resume_at = 0

    if response.status_code not in (200, 206):
        body = response.text
        response.close()
        raise RuntimeError(
            f"{item.get('Name')} download failed with HTTP {response.status_code}: {body}"
        )

    mode = "ab" if response.status_code == 206 and resume_at > 0 else "wb"
    with temp_path.open(mode) as handle:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                handle.write(chunk)
    response.close()
    temp_path.replace(final_path)
    return "downloaded"


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filter_str = build_filter(args)
    products = search_products(args, filter_str)

    if args.manifest:
        write_manifest(products, Path(args.manifest))

    print_results(products)
    if args.list_only:
        return 0

    if not products:
        return 0

    client = CDSEClient(args.username, args.password, args.timeout)
    downloaded = 0
    skipped = 0
    failed = 0

    for index, item in enumerate(products, start=1):
        name = item.get("Name", item.get("Id", "<unknown>"))
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{index}/{len(products)}] {name}")
        try:
            status = download_product(
                client=client,
                item=item,
                output_dir=output_dir,
                overwrite=args.overwrite,
                use_zip_endpoint=args.use_zip_endpoint,
                chunk_size=args.chunk_size,
            )
            if status == "downloaded":
                downloaded += 1
                print("  -> downloaded")
            else:
                skipped += 1
                print("  -> skipped (already exists)")
        except Exception as exc:
            failed += 1
            print(f"  -> failed: {exc}")

    print("-" * 120)
    print(
        f"Finished. total={len(products)} downloaded={downloaded} skipped={skipped} failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
