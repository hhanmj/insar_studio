"""Offline ASF download dry-run planner (Task 033).

Builds a *plan* of the Sentinel-1 downloads implied by a local ASF cart,
**without** downloading anything, contacting ASF/Earthdata, verifying remote
files, or reading credentials. It only consumes the already-parsed
:class:`~insar_prep.core.models.Scene` list and writes a small
``asf_download_plan.json`` + ``asf_download_plan.csv`` under
``<output_dir>/asf_download_plan/``.

Credential-safety (see ``docs/asf_download_credential_design.md``): no URL,
query string, or token is ever written to the plan -- only a ``url_status``
(present/missing) flag and an ``expected_filename`` derived from the granule
name. Every cell is additionally passed through ``mask_text`` before reaching
disk. ``credential_required`` is always true, because real ASF Sentinel-1 download
needs NASA Earthdata Login credentials (not handled here).
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import DownloadError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import InsarBaseModel

if TYPE_CHECKING:
    from insar_prep.core.models import Scene

logger = get_logger("providers.asf.download_plan")

# Output layout (design only; no directory other than the plan dir is created).
ASF_PLAN_SUBDIR = "asf_download_plan"
SLC_SUBDIR = "02_slc"
PLAN_JSON_NAME = "asf_download_plan.json"
PLAN_CSV_NAME = "asf_download_plan.csv"

# Sentinel-1 products are distributed as .zip archives.
_SLC_EXTENSION = ".zip"

# Fixed CSV column order. Do not reorder: downstream readers rely on this header.
ASF_PLAN_COLUMNS = [
    "scene_id",
    "platform",
    "acquisition_datetime",
    "product",
    "beam",
    "polarization",
    "url_status",
    "expected_filename",
    "planned_path",
    "status",
    "credential_required",
    "notes",
]


class AsfPlanStatus(StrEnum):
    """Per-scene planning outcome."""

    PLANNED = "PLANNED"
    MISSING_URL = "MISSING_URL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class AsfDownloadPlanItem(InsarBaseModel):
    """One planned Sentinel-1 download (mirrors :data:`ASF_PLAN_COLUMNS`)."""

    scene_id: str
    platform: str = ""
    acquisition_datetime: str = ""
    product: str = ""
    beam: str = ""
    polarization: str = ""
    url_status: str = "missing"
    expected_filename: str = ""
    planned_path: str = ""
    status: AsfPlanStatus = AsfPlanStatus.SKIPPED
    credential_required: bool = True
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        """Return this item as a ``{column: value}`` dict for ``csv.DictWriter``."""
        return {
            "scene_id": self.scene_id,
            "platform": self.platform,
            "acquisition_datetime": self.acquisition_datetime,
            "product": self.product,
            "beam": self.beam,
            "polarization": self.polarization,
            "url_status": self.url_status,
            "expected_filename": self.expected_filename,
            "planned_path": self.planned_path,
            "status": self.status.value,
            "credential_required": "yes" if self.credential_required else "no",
            "notes": self.notes,
        }


class AsfDownloadPlan(InsarBaseModel):
    """A consolidated, offline ASF Sentinel-1 download plan for one cart."""

    generated_at: datetime = Field(default_factory=_utcnow)
    source_cart: str = ""
    output_directory: str = ""
    slc_directory: str = ""
    region_safe_name: str = ""
    scene_count: int = 0
    planned_count: int = 0
    missing_url_count: int = 0
    credential_required: bool = True
    items: list[AsfDownloadPlanItem] = Field(default_factory=list)


def _expected_filename(scene: Scene) -> str:
    """Derive the expected SLC archive name from the granule id (never the URL).

    Using ``scene_id`` (the granule base, already stripped of any URL/query by the
    scene parser) guarantees no token or query string can leak into the plan.
    """
    return f"{scene.scene_id}{_SLC_EXTENSION}"


def _product_subdir(scene: Scene) -> str:
    product = str(getattr(scene.product_type, "value", scene.product_type)).lower()
    if product == "slc":
        return SLC_SUBDIR
    return f"02_{product}"


def _planned_path(output_dir: Path, scene: Scene, expected_filename: str) -> Path:
    """Return the *intended* local product path (the file is never created here)."""
    return output_dir / _product_subdir(scene) / expected_filename


def _acquisition_text(scene: Scene) -> str:
    if scene.acquisition_datetime is None:
        return ""
    return scene.acquisition_datetime.isoformat()


def _plan_item(scene: Scene, output_dir: Path) -> AsfDownloadPlanItem:
    expected = _expected_filename(scene)
    has_url = bool(scene.url)
    if has_url:
        status = AsfPlanStatus.PLANNED
        notes = "ASF Sentinel-1 download requires NASA Earthdata Login credentials"
    else:
        status = AsfPlanStatus.MISSING_URL
        notes = "no download URL in cart; remote fetch cannot be planned for this scene"
    return AsfDownloadPlanItem(
        scene_id=scene.scene_id,
        platform=scene.platform.value,
        acquisition_datetime=_acquisition_text(scene),
        product=scene.product_type.value,
        beam=scene.beam_mode.value,
        polarization=scene.polarization.value,
        url_status="present" if has_url else "missing",
        expected_filename=expected,
        planned_path=str(_planned_path(output_dir, scene, expected)),
        status=status,
        credential_required=True,
        notes=notes,
    )


def build_asf_download_plan(
    *,
    scenes: list[Scene],
    output_dir: Path | str,
    source_cart: Path | str = "",
    region_safe_name: str = "",
) -> AsfDownloadPlan:
    """Build an offline ASF download plan from parsed scenes (no network)."""
    out_dir = Path(output_dir)
    items = [_plan_item(scene, out_dir) for scene in scenes]
    planned = sum(1 for item in items if item.status is AsfPlanStatus.PLANNED)
    missing = sum(1 for item in items if item.status is AsfPlanStatus.MISSING_URL)
    plan = AsfDownloadPlan(
        source_cart=str(source_cart),
        output_directory=str(out_dir),
        slc_directory=str(out_dir / SLC_SUBDIR),
        region_safe_name=region_safe_name,
        scene_count=len(items),
        planned_count=planned,
        missing_url_count=missing,
        credential_required=True,
        items=items,
    )
    logger.debug("built ASF download plan with %d scenes (%d planned)", len(items), planned)
    return plan


def asf_download_plan_paths(output_dir: Path | str) -> tuple[Path, Path]:
    """Return the ``(json_path, csv_path)`` for the plan under ``output_dir``."""
    plan_dir = Path(output_dir) / ASF_PLAN_SUBDIR
    return plan_dir / PLAN_JSON_NAME, plan_dir / PLAN_CSV_NAME


def write_asf_download_plan(plan: AsfDownloadPlan, output_dir: Path | str) -> tuple[Path, Path]:
    """Write the plan as UTF-8 JSON + CSV (credential-masked). Returns both paths."""
    json_path, csv_path = asf_download_plan_paths(output_dir)
    try:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(mask_text(plan.to_json(indent=2)), encoding="utf-8")
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ASF_PLAN_COLUMNS)
            writer.writeheader()
            for item in plan.items:
                writer.writerow({key: mask_text(value) for key, value in item.to_row().items()})
    except OSError as exc:
        raise DownloadError(
            f"failed to write ASF download plan to {json_path.parent}: {exc}",
            code=ErrorCode.ASF001,
        ) from exc
    logger.debug("wrote ASF download plan (%d items) to %s", len(plan.items), json_path.parent)
    return json_path, csv_path
