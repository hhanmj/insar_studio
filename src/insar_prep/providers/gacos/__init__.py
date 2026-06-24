"""GACOS request planning, import checking, and real request/download.

Task 012 plans GACOS zenith-delay requests; Task 013 checks the products the
user later downloads; Task 053 imports manually downloaded products. The
planning, import-checking, and import modules never contact GACOS. Task 054 adds
an **opt-in real client** (:mod:`insar_prep.providers.gacos.downloader` /
:mod:`~insar_prep.providers.gacos.download_runner`, behind the ``download``
extra) that submits the GACOS web form and fetches the emailed result archive --
the only automation the service (which has no API) permits. Import checking is
read-only: it never moves, deletes, or creates user files.
"""

from __future__ import annotations

from insar_prep.providers.gacos.credentials import (
    GACOS_EMAIL_ENV,
    GACOS_PORTAL_URL,
    GACOS_README_URL,
    GacosEmailSource,
    ResolvedGacosEmail,
    clear_stored_gacos_email,
    is_valid_email,
    mask_email,
    resolve_gacos_email,
    store_gacos_email,
    stored_gacos_email_status,
)
from insar_prep.providers.gacos.download_runner import (
    GacosDownloadRunSummary,
    GacosRequestRunSummary,
    raise_for_missing_download_extra,
    run_gacos_download,
    run_gacos_request,
)
from insar_prep.providers.gacos.downloader import (
    GACOS_MAX_DATES_PER_REQUEST,
    GACOS_MAX_SPAN_DEGREES,
    GACOS_SUBMIT_ENDPOINT,
    FakeGacosClient,
    GacosClient,
    GacosFetchOutcome,
    GacosFetchResult,
    GacosOutputFormat,
    GacosRequest,
    GacosSubmitOutcome,
    GacosSubmitResult,
    RealGacosClient,
)
from insar_prep.providers.gacos.import_checker import (
    GACOS_EMPTY_FILE,
    GACOS_EXTRA_DATE,
    GACOS_FILENAME_INVALID,
    GACOS_IMPORT_READY,
    GACOS_RSC_MISSING,
    GACOS_ZTD_MISSING,
    check_gacos_products,
    scan_gacos_product_directory,
)
from insar_prep.providers.gacos.importer import (
    GACOS_IMPORT_OK,
    GACOS_NO_PRODUCTS_FOUND,
    GACOS_SIZE_MISMATCH,
    import_gacos_products,
)
from insar_prep.providers.gacos.planner import (
    GACOS_BATCH_SIZE_INVALID,
    GACOS_BUFFER_INVALID,
    GACOS_EXPECTED_FILE_PATTERNS,
    GACOS_MANUAL_SUBMISSION_REQUIRED,
    GACOS_NO_SCENES,
    GACOS_NO_VALID_DATES,
    GACOS_PLAN_READY,
    GACOS_SCENE_DATE_MISSING,
    create_gacos_request_plan,
    extract_gacos_dates_from_scenes,
    validate_gacos_request_plan,
)
from insar_prep.providers.gacos.types import (
    GacosImportCheckReport,
    GacosImportedProduct,
    GacosImportIssue,
    GacosImportResult,
    GacosPlanningIssue,
    GacosPlanningReport,
    GacosProductFile,
    GacosRequestBatch,
    GacosRequestPlan,
)

__all__ = [
    "GACOS_BATCH_SIZE_INVALID",
    "GACOS_BUFFER_INVALID",
    "GACOS_EMAIL_ENV",
    "GACOS_EMPTY_FILE",
    "GACOS_EXPECTED_FILE_PATTERNS",
    "GACOS_EXTRA_DATE",
    "GACOS_FILENAME_INVALID",
    "GACOS_IMPORT_OK",
    "GACOS_IMPORT_READY",
    "GACOS_MANUAL_SUBMISSION_REQUIRED",
    "GACOS_MAX_DATES_PER_REQUEST",
    "GACOS_MAX_SPAN_DEGREES",
    "GACOS_NO_PRODUCTS_FOUND",
    "GACOS_NO_SCENES",
    "GACOS_NO_VALID_DATES",
    "GACOS_PLAN_READY",
    "GACOS_PORTAL_URL",
    "GACOS_README_URL",
    "GACOS_RSC_MISSING",
    "GACOS_SCENE_DATE_MISSING",
    "GACOS_SIZE_MISMATCH",
    "GACOS_SUBMIT_ENDPOINT",
    "GACOS_ZTD_MISSING",
    "FakeGacosClient",
    "GacosClient",
    "GacosDownloadRunSummary",
    "GacosEmailSource",
    "GacosFetchOutcome",
    "GacosFetchResult",
    "GacosImportCheckReport",
    "GacosImportIssue",
    "GacosImportResult",
    "GacosImportedProduct",
    "GacosOutputFormat",
    "GacosPlanningIssue",
    "GacosPlanningReport",
    "GacosProductFile",
    "GacosRequest",
    "GacosRequestBatch",
    "GacosRequestPlan",
    "GacosRequestRunSummary",
    "GacosSubmitOutcome",
    "GacosSubmitResult",
    "RealGacosClient",
    "ResolvedGacosEmail",
    "check_gacos_products",
    "clear_stored_gacos_email",
    "create_gacos_request_plan",
    "extract_gacos_dates_from_scenes",
    "import_gacos_products",
    "is_valid_email",
    "mask_email",
    "raise_for_missing_download_extra",
    "resolve_gacos_email",
    "run_gacos_download",
    "run_gacos_request",
    "scan_gacos_product_directory",
    "store_gacos_email",
    "stored_gacos_email_status",
    "validate_gacos_request_plan",
]
