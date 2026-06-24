"""GACOS product import (Task 053).

Takes the GACOS products a user has **already downloaded manually** (GACOS has no
public download API -- see ``THIRD_PARTY_REFERENCES.md`` and the planner module)
and brings them into the region layout: it extracts ``.zip`` / ``.tar.gz``
archives, recognizes the ``YYYYMMDD.ztd`` / ``YYYYMMDD.ztd.rsc`` (and optional
``YYYYMMDD.tif``) products, copies them into the region's GACOS directory under a
canonical name, and verifies integrity -- the ``.ztd`` byte size must equal
``4 * WIDTH * FILE_LENGTH`` from its ``.rsc`` header (little-endian 4-byte float
grid). It still never contacts GACOS, submits its web form, scrapes pages,
drives a browser, or stores credentials -- it only organizes local files the
user already has. This uses only the standard library (zipfile / tarfile).
"""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import AtmosphereProductError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.providers.gacos.types import (
    GacosImportedProduct,
    GacosImportIssue,
    GacosImportResult,
)
from insar_prep.quality.types import CheckSeverity

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger("providers.gacos.importer")

GACOS_NO_PRODUCTS_FOUND = "GACOS_NO_PRODUCTS_FOUND"
GACOS_IMPORTED = "GACOS_IMPORTED"
GACOS_SIZE_MISMATCH = "GACOS_SIZE_MISMATCH"
GACOS_RSC_UNREADABLE = "GACOS_RSC_UNREADABLE"
GACOS_SOURCE_MISSING = "GACOS_SOURCE_MISSING"
GACOS_ZTD_MISSING = "GACOS_ZTD_MISSING"
GACOS_RSC_MISSING = "GACOS_RSC_MISSING"
GACOS_EMPTY_FILE = "GACOS_EMPTY_FILE"
GACOS_EXTRA_DATE = "GACOS_EXTRA_DATE"
GACOS_IMPORT_OK = "GACOS_IMPORT_OK"

_ZTD_RE = re.compile(r"^(\d{8})\.ztd$")
_RSC_RE = re.compile(r"^(\d{8})\.ztd\.rsc$")
_TIF_RE = re.compile(r"^(\d{8})\.(?:ztd\.)?tif$")
_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")
_ZTD_BYTES_PER_SAMPLE = 4  # GACOS .ztd is a little-endian 4-byte float grid.


def _parse_yyyymmdd(token: str) -> date | None:
    try:
        return datetime.strptime(token, "%Y%m%d").date()
    except ValueError:
        return None


def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _safe_members_ok(dest: Path, names: Sequence[str]) -> None:
    """Reject any archive member that would escape ``dest`` (zip/tar slip)."""
    dest_resolved = dest.resolve()
    for name in names:
        target = (dest / name).resolve()
        if target != dest_resolved and dest_resolved not in target.parents:
            raise AtmosphereProductError(f"unsafe path in archive: {name!r}", code=ErrorCode.GAC002)


def _extract_archive(archive: Path, dest: Path) -> None:
    """Safely extract a ``.zip`` / ``.tar*`` archive into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            _safe_members_ok(dest, zf.namelist())
            zf.extractall(dest)
    else:
        with tarfile.open(archive) as tf:
            _safe_members_ok(dest, tf.getnames())
            tf.extractall(dest)  # noqa: S202 - members validated above


def _gather_files(
    sources: Sequence[Path], extract_root: Path, issues: list[GacosImportIssue]
) -> list[Path]:
    """Return all candidate files from dirs / archives / individual files."""
    files: list[Path] = []
    for source in sources:
        if not source.exists():
            issues.append(
                GacosImportIssue(
                    code=GACOS_SOURCE_MISSING,
                    severity=CheckSeverity.WARNING,
                    message=f"source not found: {source}",
                    file_path=source,
                )
            )
            continue
        if source.is_file() and _is_archive(source):
            target = extract_root / source.stem
            _extract_archive(source, target)
            files.extend(p for p in target.rglob("*") if p.is_file())
        elif source.is_dir():
            files.extend(p for p in source.rglob("*") if p.is_file())
        elif source.is_file():
            files.append(source)
    return files


def _canonical_name(name: str) -> tuple[date, str] | None:
    """Return (date, canonical_filename) for a recognized GACOS product."""
    for pattern in (_RSC_RE, _ZTD_RE, _TIF_RE):
        match = pattern.match(name)
        if match:
            parsed = _parse_yyyymmdd(match.group(1))
            if parsed is not None:
                return parsed, name
    return None


def _expected_ztd_size(rsc_path: Path) -> int | None:
    """Compute the expected ``.ztd`` byte size from its ``.rsc`` header."""
    try:
        text = rsc_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    values: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            values[parts[0].upper()] = parts[1]
    try:
        width = int(values["WIDTH"])
        length = int(values["FILE_LENGTH"])
    except (KeyError, ValueError):
        return None
    if width <= 0 or length <= 0:
        return None
    return _ZTD_BYTES_PER_SAMPLE * width * length


def import_gacos_products(
    sources: Sequence[Path | str],
    output_directory: Path | str,
    *,
    expected_dates: Sequence[date] | None = None,
    move: bool = False,
) -> GacosImportResult:
    """Import GACOS products from ``sources`` into ``output_directory``.

    ``sources`` may be directories, ``.zip`` / ``.tar.gz`` archives, or individual
    product files. Recognized products (``YYYYMMDD.ztd`` / ``.ztd.rsc`` /
    ``.tif``) are copied (or moved when ``move=True``) under a canonical name, and
    each date is integrity-checked. ``expected_dates`` (e.g. a request plan's
    ``unique_dates``) drives the missing/extra-date coverage report.
    """
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = [Path(s) for s in sources]
    issues: list[GacosImportIssue] = []
    imported_files: list[Path] = []
    extracted_archives = [p for p in source_paths if p.is_file() and _is_archive(p)]

    with tempfile.TemporaryDirectory(prefix="gacos_import_") as tmp:
        extract_root = Path(tmp)
        candidates = _gather_files(source_paths, extract_root, issues)
        for candidate in candidates:
            recognized = _canonical_name(candidate.name)
            if recognized is None:
                continue
            _parsed_date, canonical = recognized
            destination = output_dir / canonical
            if destination.resolve() == candidate.resolve():
                imported_files.append(destination)
                continue
            shutil.copyfile(candidate, destination)
            from_archive = extract_root in candidate.parents
            if move and not from_archive:
                candidate.unlink(missing_ok=True)
            imported_files.append(destination)

    products = _scan_imported(output_dir)
    found_dates = sorted({product.date for product in products})

    if not products:
        issues.append(
            GacosImportIssue(
                code=GACOS_NO_PRODUCTS_FOUND,
                severity=CheckSeverity.ERROR,
                message="no GACOS products (YYYYMMDD.ztd[.rsc]/.tif) were found in the sources",
            )
        )

    _validate_products(products, issues)

    expected = sorted(set(expected_dates)) if expected_dates else []
    missing_dates = sorted(set(expected) - set(found_dates)) if expected else []
    extra_dates = sorted(set(found_dates) - set(expected)) if expected else []
    for missing in missing_dates:
        issues.append(
            GacosImportIssue(
                code=GACOS_ZTD_MISSING,
                severity=CheckSeverity.ERROR,
                message=f"expected GACOS date not imported: {missing:%Y%m%d}",
                date=missing,
            )
        )
    for extra in extra_dates:
        issues.append(
            GacosImportIssue(
                code=GACOS_EXTRA_DATE,
                severity=CheckSeverity.WARNING,
                message=f"imported GACOS date not in the request plan: {extra:%Y%m%d}",
                date=extra,
            )
        )

    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in issues)
    if not has_errors and products:
        issues.append(
            GacosImportIssue(
                code=GACOS_IMPORT_OK,
                severity=CheckSeverity.INFO,
                message=f"imported {len(products)} GACOS product date(s) successfully",
            )
        )

    summary = {
        "output_directory": str(output_dir),
        "imported_file_count": len(imported_files),
        "product_date_count": len(products),
        "valid_product_count": sum(1 for p in products if p.valid),
        "expected_date_count": len(expected),
        "missing_date_count": len(missing_dates),
        "extra_date_count": len(extra_dates),
    }
    log_event(
        logger,
        EventType.GACOS_PRODUCTS_IMPORTED,
        f"imported {len(products)} GACOS product date(s) into {output_dir.name}",
        module="providers.gacos.importer",
        payload=summary,
    )
    return GacosImportResult(
        output_directory=output_dir,
        imported_files=sorted(imported_files),
        extracted_archives=extracted_archives,
        products=products,
        expected_dates=expected,
        found_dates=found_dates,
        missing_dates=missing_dates,
        extra_dates=extra_dates,
        issues=issues,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )


def _scan_imported(output_dir: Path) -> list[GacosImportedProduct]:
    """Group the canonical product files now present in ``output_dir`` by date."""
    products: dict[date, GacosImportedProduct] = {}
    for entry in sorted(output_dir.iterdir()):
        if not entry.is_file():
            continue
        rsc_match = _RSC_RE.match(entry.name)
        ztd_match = None if rsc_match else _ZTD_RE.match(entry.name)
        tif_match = None if (rsc_match or ztd_match) else _TIF_RE.match(entry.name)
        token = rsc_match or ztd_match or tif_match
        if token is None:
            continue
        parsed = _parse_yyyymmdd(token.group(1))
        if parsed is None:
            continue
        product = products.setdefault(parsed, GacosImportedProduct(date=parsed))
        if rsc_match:
            product.rsc_path = entry
        elif ztd_match:
            product.ztd_path = entry
            product.ztd_size_bytes = entry.stat().st_size
        elif tif_match:
            product.tif_path = entry
    return [products[key] for key in sorted(products)]


def _validate_products(
    products: list[GacosImportedProduct], issues: list[GacosImportIssue]
) -> None:
    """Validate each imported product's pairing and byte-size integrity."""
    for product in products:
        has_tif = product.tif_path is not None
        # A GeoTIFF-only product is self-contained; .ztd needs a paired .rsc.
        if product.ztd_path is None and not has_tif:
            issues.append(
                GacosImportIssue(
                    code=GACOS_ZTD_MISSING,
                    severity=CheckSeverity.ERROR,
                    message=f"missing .ztd for {product.date:%Y%m%d}",
                    date=product.date,
                )
            )
        if product.ztd_path is not None and product.rsc_path is None:
            issues.append(
                GacosImportIssue(
                    code=GACOS_RSC_MISSING,
                    severity=CheckSeverity.ERROR,
                    message=f"missing .ztd.rsc for {product.date:%Y%m%d}",
                    date=product.date,
                )
            )

        empty = False
        for path in (product.ztd_path, product.rsc_path, product.tif_path):
            if path is not None and path.stat().st_size == 0:
                empty = True
                issues.append(
                    GacosImportIssue(
                        code=GACOS_EMPTY_FILE,
                        severity=CheckSeverity.ERROR,
                        message=f"empty GACOS file: {path.name}",
                        date=product.date,
                        file_path=path,
                    )
                )

        size_ok = True
        if product.ztd_path is not None and product.rsc_path is not None:
            expected = _expected_ztd_size(product.rsc_path)
            product.expected_ztd_size_bytes = expected
            if expected is None:
                size_ok = False
                issues.append(
                    GacosImportIssue(
                        code=GACOS_RSC_UNREADABLE,
                        severity=CheckSeverity.WARNING,
                        message=f"could not read WIDTH/FILE_LENGTH from {product.rsc_path.name}",
                        date=product.date,
                        file_path=product.rsc_path,
                    )
                )
            elif product.ztd_size_bytes != expected:
                size_ok = False
                issues.append(
                    GacosImportIssue(
                        code=GACOS_SIZE_MISMATCH,
                        severity=CheckSeverity.ERROR,
                        message=(
                            f".ztd for {product.date:%Y%m%d} is {product.ztd_size_bytes} bytes "
                            f"but its .rsc implies {expected} (4 x WIDTH x FILE_LENGTH)"
                        ),
                        date=product.date,
                        file_path=product.ztd_path,
                    )
                )

        if has_tif and product.tif_path is not None and product.tif_path.stat().st_size > 0:
            with product.tif_path.open("rb") as handle:
                head = handle.read(4)
            if not head.startswith(_TIFF_MAGIC):
                size_ok = False
                issues.append(
                    GacosImportIssue(
                        code=GACOS_SIZE_MISMATCH,
                        severity=CheckSeverity.ERROR,
                        message=f"{product.tif_path.name} is not a valid GeoTIFF",
                        date=product.date,
                        file_path=product.tif_path,
                    )
                )

        ztd_paired_ok = product.ztd_path is not None and product.rsc_path is not None
        product.valid = (not empty) and size_ok and (ztd_paired_ok or has_tif)
