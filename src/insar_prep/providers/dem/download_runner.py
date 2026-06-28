"""Shared orchestration for real OpenTopography DEM download (Task 052).

Wraps the credential-safe primitives -- API-key resolution, request building from
a :class:`~insar_prep.providers.dem.types.DemRequestPlan`, the real downloader,
and a results CSV -- into a single synchronous :func:`run_dem_download` call that
both a background GUI worker and the CLI can reuse, so the DEM download
orchestration lives in exactly one place (mirroring ``asf/download_runner.py``).

It is offline-testable: inject a fake ``downloader`` to exercise the success /
failure / cancel paths without any network or real OpenTopography key. Real
download still needs the optional ``download`` extra (``requests``), which the
:class:`~insar_prep.providers.dem.downloader.RealDemDownloader` imports lazily;
this module never imports ``requests`` itself.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.providers.dem.credentials import DemKeySource
from insar_prep.providers.dem.downloader import (
    DemDownloader,
    DemDownloadOutcome,
    DemDownloadResult,
    RealDemDownloader,
    dem_download_request_from_plan,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from threading import Event

    from insar_prep.providers.dem.types import DemRequestPlan

    ProgressCallback = Callable[[DemDownloadResult], None]

logger = get_logger("providers.dem.download_runner")

# Shared DEM output bucket for raw, ellipsoid, SARscape-ready files and CSV logs.
DEM_DOWNLOAD_SUBDIR = "DEM"

DEM_DOWNLOAD_RESULT_COLUMNS = [
    "region_safe_name",
    "dataset",
    "outcome",
    "bytes_written",
    "error_code",
    "message",
]


def write_dem_download_results_csv(
    output_dir: Path | str, results: Sequence[DemDownloadResult]
) -> Path:
    """Write a credential-masked per-region DEM results CSV; return its path."""
    plan_dir = Path(output_dir) / DEM_DOWNLOAD_SUBDIR
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "dem_download_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEM_DOWNLOAD_RESULT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "region_safe_name": result.region_safe_name,
                    "dataset": result.dataset,
                    "outcome": result.outcome.value,
                    "bytes_written": result.bytes_written,
                    "error_code": result.error_code or "",
                    "message": mask_text(result.message),
                }
            )
    return results_path


@dataclass(frozen=True)
class DemDownloadRunSummary:
    """Aggregate outcome of a :func:`run_dem_download` call."""

    results: list[DemDownloadResult]
    results_path: Path | None
    counts: dict[DemDownloadOutcome, int]
    cancelled: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return self.counts.get(DemDownloadOutcome.SUCCESS, 0)

    @property
    def skipped(self) -> int:
        return self.counts.get(DemDownloadOutcome.SKIPPED, 0)

    @property
    def failed(self) -> int:
        return self.counts.get(DemDownloadOutcome.FAILED, 0)

    @property
    def interrupted(self) -> int:
        return self.counts.get(DemDownloadOutcome.INTERRUPTED, 0)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0 or self.interrupted > 0

    def summary_line(self) -> str:
        """A short, credential-free one-line summary for a status bar/log."""
        return (
            f"{self.succeeded} downloaded, {self.skipped} skipped, "
            f"{self.failed} failed, {self.interrupted} interrupted"
        )


def run_dem_download(
    plans: Iterable[DemRequestPlan],
    output_dir: Path | str,
    *,
    key_source: DemKeySource = DemKeySource.AUTO,
    downloader: DemDownloader | None = None,
    max_retries: int = 3,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> DemDownloadRunSummary:
    """Download the DEM for each plan in ``plans`` to its planned ``raw_dem_path``.

    Resolves the OpenTopography API key (unless an explicit ``downloader`` is
    given), downloads one DEM per plan with a downloadable dataset, writes a
    credential-masked ``dem_download/dem_download_results.csv`` under
    ``output_dir``, and returns a :class:`DemDownloadRunSummary`.

    Per-plan transport/credential problems are captured as ``FAILED`` results
    (never raised). :class:`~insar_prep.core.exceptions.InsarPrepError` is raised
    only when there is nothing to download, and the downloader's key resolver may
    surface a :class:`~insar_prep.core.exceptions.CredentialError` as a ``FAILED``
    result. Pass ``progress`` for each result as it completes and ``cancel_event``
    to stop cleanly between plans.
    """
    output_path = Path(output_dir)
    plan_list = list(plans)
    if not plan_list:
        raise InsarPrepError(
            "no DEM plans to download; run the DEM planning step first",
            code=ErrorCode.DEM001,
        )

    active = downloader
    if active is None:
        active = RealDemDownloader(
            key_source=key_source, max_retries=max_retries, cancel_event=cancel_event
        )

    results: list[DemDownloadResult] = []
    cancelled = False
    for plan in plan_list:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        request = dem_download_request_from_plan(plan)
        if request is None:
            results.append(
                DemDownloadResult(
                    region_safe_name=getattr(plan, "region_safe_name", ""),
                    dataset=getattr(plan, "dataset", ""),
                    outcome=DemDownloadOutcome.SKIPPED,
                    message="dataset is not downloadable from OpenTopography",
                )
            )
            continue
        result = active.download(request)
        results.append(result)
        if progress is not None:
            progress(result)
        logger.info(
            "DEM %s: %s (%d bytes)%s",
            result.region_safe_name,
            result.outcome.value,
            result.bytes_written,
            f" [{result.error_code}]" if result.error_code else "",
        )
        if result.outcome is DemDownloadOutcome.INTERRUPTED:
            cancelled = True
            break

    if not any(r.outcome is not DemDownloadOutcome.SKIPPED for r in results) and not cancelled:
        raise InsarPrepError(
            "no downloadable DEM datasets in the provided plans (e.g. USER_LOCAL)",
            code=ErrorCode.DEM001,
        )

    results_path = write_dem_download_results_csv(output_path, results) if results else None
    counts = {outcome: 0 for outcome in DemDownloadOutcome}
    for result in results:
        counts[result.outcome] += 1
    return DemDownloadRunSummary(
        results=results, results_path=results_path, counts=counts, cancelled=cancelled
    )
