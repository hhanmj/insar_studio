"""GACOS product import checking (Task 013).

Checks a *local* directory of GACOS products the user has already downloaded
against a :class:`GacosRequestPlan`: are the expected ``YYYYMMDD.ztd`` and
``YYYYMMDD.ztd.rsc`` files present, are there unexpected dates, are filenames
well-formed, and are any files empty. It never contacts GACOS, downloads
products, submits the web form, scrapes pages, drives a browser, reads
accounts, or stores credentials. It also never parses ``.ztd`` raster content
or ``.rsc`` extents, never performs atmospheric correction, and never moves,
deletes, or creates user files (it is read-only).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import AtmosphereProductError
from insar_prep.core.logging import get_logger, log_event
from insar_prep.providers.gacos.types import (
    GacosImportCheckReport,
    GacosImportIssue,
    GacosProductFile,
    GacosRequestPlan,
)
from insar_prep.quality.types import CheckSeverity

logger = get_logger("providers.gacos.import_checker")

GACOS_ZTD_MISSING = "GACOS_ZTD_MISSING"
GACOS_RSC_MISSING = "GACOS_RSC_MISSING"
GACOS_EXTRA_DATE = "GACOS_EXTRA_DATE"
GACOS_FILENAME_INVALID = "GACOS_FILENAME_INVALID"
GACOS_EMPTY_FILE = "GACOS_EMPTY_FILE"
GACOS_IMPORT_READY = "GACOS_IMPORT_READY"

_ZTD_RE = re.compile(r"^(\d{8})\.ztd$")
_RSC_RE = re.compile(r"^(\d{8})\.ztd\.rsc$")


def _parse_yyyymmdd(token: str) -> date | None:
    try:
        return datetime.strptime(token, "%Y%m%d").date()
    except ValueError:
        return None


def scan_gacos_product_directory(path: Path | str) -> list[GacosProductFile]:
    """Scan ``path`` for well-formed GACOS products grouped by date.

    Only files named ``YYYYMMDD.ztd`` / ``YYYYMMDD.ztd.rsc`` with a valid date
    are grouped. Reading is non-destructive (``stat`` only); contents are never
    opened. Raises :class:`AtmosphereProductError` (``GAC002``) if the directory
    does not exist.
    """
    directory = Path(path)
    if not directory.is_dir():
        raise AtmosphereProductError(
            f"GACOS product directory not found: {directory}", code=ErrorCode.GAC002
        )
    products: dict[date, GacosProductFile] = {}
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        rsc_match = _RSC_RE.match(entry.name)
        ztd_match = None if rsc_match else _ZTD_RE.match(entry.name)
        if rsc_match:
            parsed = _parse_yyyymmdd(rsc_match.group(1))
            if parsed is None:
                continue
            product = products.setdefault(parsed, GacosProductFile(date=parsed))
            product.rsc_path = entry
            product.has_rsc = True
            product.rsc_size_bytes = entry.stat().st_size
        elif ztd_match:
            parsed = _parse_yyyymmdd(ztd_match.group(1))
            if parsed is None:
                continue
            product = products.setdefault(parsed, GacosProductFile(date=parsed))
            product.ztd_path = entry
            product.has_ztd = True
            product.ztd_size_bytes = entry.stat().st_size
    return [products[key] for key in sorted(products)]


def _filename_issues(directory: Path) -> list[GacosImportIssue]:
    """Flag files that look like GACOS products but are misnamed (WARNING)."""
    issues: list[GacosImportIssue] = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        name = entry.name
        if name.endswith(".ztd.rsc"):
            invalid = _RSC_RE.match(name) is None or _parse_yyyymmdd(name[:8]) is None
        elif name.endswith(".ztd"):
            invalid = _ZTD_RE.match(name) is None or _parse_yyyymmdd(name[:8]) is None
        else:
            continue
        if invalid:
            issues.append(
                GacosImportIssue(
                    code=GACOS_FILENAME_INVALID,
                    severity=CheckSeverity.WARNING,
                    message=f"GACOS filename does not match YYYYMMDD.ztd[.rsc]: {name!r}",
                    file_path=entry,
                )
            )
    return issues


def check_gacos_products(
    *,
    request_plan: GacosRequestPlan,
    product_directory: Path | str,
) -> GacosImportCheckReport:
    """Check a local GACOS product directory against a request plan."""
    directory = Path(product_directory)
    if not directory.is_dir():
        raise AtmosphereProductError(
            f"GACOS product directory not found: {directory}", code=ErrorCode.GAC002
        )
    logger.debug("checking GACOS products in %s", directory)

    products = scan_gacos_product_directory(directory)
    products_by_date = {product.date: product for product in products}
    expected_dates = list(request_plan.unique_dates)
    found_dates = sorted(products_by_date)
    missing_dates = sorted(set(expected_dates) - set(found_dates))
    extra_dates = sorted(set(found_dates) - set(expected_dates))

    issues: list[GacosImportIssue] = _filename_issues(directory)

    for expected in expected_dates:
        product = products_by_date.get(expected)
        if product is None or not product.has_ztd:
            issues.append(
                GacosImportIssue(
                    code=GACOS_ZTD_MISSING,
                    severity=CheckSeverity.ERROR,
                    message=f"missing .ztd for {expected:%Y%m%d}",
                    date=expected,
                )
            )
        if product is None or not product.has_rsc:
            issues.append(
                GacosImportIssue(
                    code=GACOS_RSC_MISSING,
                    severity=CheckSeverity.ERROR,
                    message=f"missing .ztd.rsc for {expected:%Y%m%d}",
                    date=expected,
                )
            )

    for product in products:
        if product.has_ztd and product.ztd_size_bytes == 0:
            ztd_name = product.ztd_path.name if product.ztd_path else ""
            issues.append(
                GacosImportIssue(
                    code=GACOS_EMPTY_FILE,
                    severity=CheckSeverity.ERROR,
                    message=f"empty GACOS file: {ztd_name}",
                    date=product.date,
                    file_path=product.ztd_path,
                )
            )
        if product.has_rsc and product.rsc_size_bytes == 0:
            rsc_name = product.rsc_path.name if product.rsc_path else ""
            issues.append(
                GacosImportIssue(
                    code=GACOS_EMPTY_FILE,
                    severity=CheckSeverity.ERROR,
                    message=f"empty GACOS file: {rsc_name}",
                    date=product.date,
                    file_path=product.rsc_path,
                )
            )

    for extra in extra_dates:
        issues.append(
            GacosImportIssue(
                code=GACOS_EXTRA_DATE,
                severity=CheckSeverity.WARNING,
                message=f"unexpected GACOS date not in request plan: {extra:%Y%m%d}",
                date=extra,
            )
        )

    has_errors = any(issue.severity is CheckSeverity.ERROR for issue in issues)
    has_warnings = any(issue.severity is CheckSeverity.WARNING for issue in issues)
    if not has_errors:
        issues.append(
            GacosImportIssue(
                code=GACOS_IMPORT_READY,
                severity=CheckSeverity.INFO,
                message="all expected GACOS products are present",
            )
        )
    summary = {
        "expected_date_count": len(expected_dates),
        "found_date_count": len(found_dates),
        "missing_date_count": len(missing_dates),
        "extra_date_count": len(extra_dates),
        "product_directory": str(directory),
    }
    log_event(
        logger,
        EventType.GACOS_PRODUCTS_IMPORTED,
        f"checked GACOS products in {directory.name}",
        module="providers.gacos.import_checker",
        payload=summary,
    )
    logger.debug("finished GACOS import check for %s", directory)
    return GacosImportCheckReport(
        expected_dates=expected_dates,
        found_dates=found_dates,
        missing_dates=missing_dates,
        extra_dates=extra_dates,
        products=products,
        issues=issues,
        has_errors=has_errors,
        has_warnings=has_warnings,
        summary=summary,
    )
