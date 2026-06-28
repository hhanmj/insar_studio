"""Shared orchestration for real DEM vertical-datum conversion (Task 053).

Wraps :class:`~insar_prep.providers.dem.converter.RealDemConverter` into a single
synchronous :func:`run_dem_conversion` that the CLI (and a future GUI worker) can
reuse, writing a credential-free ``dem_convert/dem_convert_results.csv`` next to
the download results CSV. It mirrors ``dem/download_runner.py``.

It is offline-testable: inject a fake ``converter`` to exercise the
success / copied / failed paths without rasterio, a geoid, or a real GeoTIFF.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.providers.dem.converter import (
    DemConversionOutcome,
    DemConversionResult,
    DemConverter,
    RealDemConverter,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from insar_prep.providers.dem.types import DemConversionPlan

    ProgressCallback = Callable[[DemConversionResult], None]

logger = get_logger("providers.dem.convert_runner")

DEM_CONVERT_SUBDIR = "DEM"

DEM_CONVERT_RESULT_COLUMNS = [
    "region_safe_name",
    "dataset",
    "outcome",
    "source_vertical_datum",
    "target_vertical_datum",
    "geoid_model",
    "output_path",
    "message",
]


def write_dem_convert_results_csv(
    output_dir: Path | str, results: Sequence[DemConversionResult]
) -> Path:
    """Write a per-region DEM conversion results CSV; return its path."""
    plan_dir = Path(output_dir) / DEM_CONVERT_SUBDIR
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "dem_convert_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEM_CONVERT_RESULT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "region_safe_name": result.region_safe_name,
                    "dataset": result.dataset,
                    "outcome": result.outcome.value,
                    "source_vertical_datum": result.source_vertical_datum.value,
                    "target_vertical_datum": result.target_vertical_datum.value,
                    "geoid_model": result.geoid_model or "",
                    "output_path": str(result.path) if result.path else "",
                    "message": mask_text(result.message),
                }
            )
    return results_path


@dataclass(frozen=True)
class DemConvertRunSummary:
    """Aggregate outcome of a :func:`run_dem_conversion` call."""

    results: list[DemConversionResult]
    results_path: Path | None
    counts: dict[DemConversionOutcome, int]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return self.counts.get(DemConversionOutcome.SUCCESS, 0)

    @property
    def copied(self) -> int:
        return self.counts.get(DemConversionOutcome.COPIED, 0)

    @property
    def skipped(self) -> int:
        return self.counts.get(DemConversionOutcome.SKIPPED, 0)

    @property
    def failed(self) -> int:
        return self.counts.get(DemConversionOutcome.FAILED, 0)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0

    def summary_line(self) -> str:
        return (
            f"{self.succeeded} converted, {self.copied} copied, "
            f"{self.skipped} skipped, {self.failed} failed"
        )


def run_dem_conversion(
    plans: Iterable[DemConversionPlan],
    output_dir: Path | str,
    *,
    converter: DemConverter | None = None,
    geoid_grid_path: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> DemConvertRunSummary:
    """Convert each plan's raw DEM to a SARscape-ready ellipsoidal DEM.

    Writes a ``dem_convert/dem_convert_results.csv`` under ``output_dir`` and
    returns a :class:`DemConvertRunSummary`. Per-plan failures are captured as
    ``FAILED`` results (never raised); :class:`InsarPrepError` is raised only when
    there is nothing to convert.
    """
    plan_list = list(plans)
    if not plan_list:
        raise InsarPrepError(
            "no DEM conversion plans; run the DEM planning step first",
            code=ErrorCode.DEM003,
        )

    active = converter
    if active is None:
        active = RealDemConverter(geoid_grid_path=geoid_grid_path)

    results: list[DemConversionResult] = []
    for plan in plan_list:
        result = active.convert(plan)
        results.append(result)
        if progress is not None:
            progress(result)
        logger.info(
            "DEM convert %s: %s%s",
            result.region_safe_name,
            result.outcome.value,
            f" [{result.error_code}]" if result.error_code else "",
        )

    results_path = write_dem_convert_results_csv(output_dir, results) if results else None
    counts = {outcome: 0 for outcome in DemConversionOutcome}
    for result in results:
        counts[result.outcome] += 1
    return DemConvertRunSummary(results=results, results_path=results_path, counts=counts)
