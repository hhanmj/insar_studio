"""GACOS request planning and import checking (local, offline).

Task 012 plans GACOS zenith-delay requests the user submits manually; Task 013
checks the products the user later downloads. Neither contacts GACOS, submits
its web form, scrapes pages, bypasses limits, downloads products, drives a
browser, or stores credentials. Import checking is read-only: it never moves,
deletes, or creates user files.
"""

from __future__ import annotations

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
    "GACOS_EMPTY_FILE",
    "GACOS_EXPECTED_FILE_PATTERNS",
    "GACOS_EXTRA_DATE",
    "GACOS_FILENAME_INVALID",
    "GACOS_IMPORT_OK",
    "GACOS_IMPORT_READY",
    "GACOS_MANUAL_SUBMISSION_REQUIRED",
    "GACOS_NO_PRODUCTS_FOUND",
    "GACOS_NO_SCENES",
    "GACOS_NO_VALID_DATES",
    "GACOS_PLAN_READY",
    "GACOS_RSC_MISSING",
    "GACOS_SCENE_DATE_MISSING",
    "GACOS_SIZE_MISMATCH",
    "GACOS_ZTD_MISSING",
    "GacosImportCheckReport",
    "GacosImportIssue",
    "GacosImportResult",
    "GacosImportedProduct",
    "GacosPlanningIssue",
    "GacosPlanningReport",
    "GacosProductFile",
    "GacosRequestBatch",
    "GacosRequestPlan",
    "check_gacos_products",
    "create_gacos_request_plan",
    "extract_gacos_dates_from_scenes",
    "import_gacos_products",
    "scan_gacos_product_directory",
    "validate_gacos_request_plan",
]
