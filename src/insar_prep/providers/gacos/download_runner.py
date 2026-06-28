"""Shared orchestration for real GACOS request submission and download (Task 054).

Wraps the GACOS client into two synchronous calls that the CLI and a background
GUI worker reuse, mirroring ``asf``/``dem`` download runners:

* :func:`run_gacos_request` splits a date list into <=20-date batches and submits
  each to the GACOS web form, writing a credential-safe results CSV.
* :func:`run_gacos_download` fetches the emailed result archive(s) and hands them
  to :func:`insar_prep.providers.gacos.importer.import_gacos_products` so the
  products are organized and integrity-checked in one step.

Both are offline-testable by injecting a
:class:`~insar_prep.providers.gacos.downloader.FakeGacosClient`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.events import EventType
from insar_prep.core.exceptions import InputValidationError, InsarPrepError
from insar_prep.core.logging import get_logger, log_event, mask_text
from insar_prep.core.models import BBox
from insar_prep.providers.gacos.credentials import GacosEmailSource
from insar_prep.providers.gacos.downloader import (
    GACOS_MAX_DATES_PER_REQUEST,
    GACOS_MAX_SPAN_DEGREES,
    GacosClient,
    GacosFetchOutcome,
    GacosFetchResult,
    GacosOutputFormat,
    GacosRequest,
    GacosSubmitOutcome,
    GacosSubmitResult,
    RealGacosClient,
)
from insar_prep.providers.gacos.importer import import_gacos_products

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from threading import Event

    from insar_prep.providers.gacos.types import GacosImportResult

    SubmitProgress = Callable[[GacosSubmitResult], None]
    FetchProgress = Callable[[GacosFetchResult], None]

logger = get_logger("providers.gacos.download_runner")

GACOS_REQUEST_SUBDIR = "GACOS"
GACOS_DOWNLOADS_SUBDIR = "downloads"

GACOS_REQUEST_RESULT_COLUMNS = [
    "region_safe_name",
    "batch_index",
    "batch_count",
    "date_count",
    "outcome",
    "error_code",
    "message",
]

GACOS_FETCH_RESULT_COLUMNS = [
    "index",
    "outcome",
    "bytes_written",
    "error_code",
    "message",
]


def _chunk(items: list[date], size: int) -> list[list[date]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _bbox_span_ok(bbox: BBox) -> bool:
    return (bbox.north - bbox.south) <= GACOS_MAX_SPAN_DEGREES and (
        bbox.east - bbox.west
    ) <= GACOS_MAX_SPAN_DEGREES


def write_gacos_request_results_csv(
    output_dir: Path | str, results: Sequence[GacosSubmitResult]
) -> Path:
    """Write a credential-safe per-batch GACOS request results CSV; return its path."""
    plan_dir = Path(output_dir) / GACOS_REQUEST_SUBDIR
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "gacos_request_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GACOS_REQUEST_RESULT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "region_safe_name": result.region_safe_name,
                    "batch_index": result.batch_index,
                    "batch_count": result.batch_count,
                    "date_count": result.date_count,
                    "outcome": result.outcome.value,
                    "error_code": result.error_code or "",
                    "message": mask_text(result.message),
                }
            )
    return results_path


def write_gacos_fetch_results_csv(
    output_dir: Path | str, results: Sequence[GacosFetchResult]
) -> Path:
    """Write a credential-safe per-URL GACOS fetch results CSV; return its path."""
    plan_dir = Path(output_dir)
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "gacos_download_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GACOS_FETCH_RESULT_COLUMNS)
        writer.writeheader()
        for index, result in enumerate(results, start=1):
            writer.writerow(
                {
                    "index": index,
                    "outcome": result.outcome.value,
                    "bytes_written": result.bytes_written,
                    "error_code": result.error_code or "",
                    "message": mask_text(result.message),
                }
            )
    return results_path


@dataclass(frozen=True)
class GacosRequestRunSummary:
    """Aggregate outcome of a :func:`run_gacos_request` call."""

    results: list[GacosSubmitResult]
    results_path: Path | None
    counts: dict[GacosSubmitOutcome, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def submitted(self) -> int:
        return self.counts.get(GacosSubmitOutcome.SUBMITTED, 0)

    @property
    def failed(self) -> int:
        return self.counts.get(GacosSubmitOutcome.FAILED, 0)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0

    def summary_line(self) -> str:
        return f"{self.submitted} batch(es) submitted, {self.failed} failed"


@dataclass(frozen=True)
class GacosDownloadRunSummary:
    """Aggregate outcome of a :func:`run_gacos_download` call."""

    fetch_results: list[GacosFetchResult]
    import_result: GacosImportResult | None
    results_path: Path | None
    counts: dict[GacosFetchOutcome, int] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def fetched(self) -> int:
        return self.counts.get(GacosFetchOutcome.SUCCESS, 0)

    @property
    def skipped(self) -> int:
        return self.counts.get(GacosFetchOutcome.SKIPPED, 0)

    @property
    def failed(self) -> int:
        return self.counts.get(GacosFetchOutcome.FAILED, 0)

    @property
    def interrupted(self) -> int:
        return self.counts.get(GacosFetchOutcome.INTERRUPTED, 0)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0 or self.interrupted > 0

    def summary_line(self) -> str:
        imported = (
            self.import_result.summary.get("product_date_count", 0)
            if self.import_result is not None
            else 0
        )
        return (
            f"{self.fetched} archive(s) fetched, {self.skipped} skipped, "
            f"{self.failed} failed; {imported} product date(s) imported"
        )


def run_gacos_request(
    *,
    region_safe_name: str,
    bbox: BBox,
    dates: Sequence[date],
    email: str = "",
    output_root: Path | str,
    hour: int = 0,
    minute: int = 0,
    output_format: GacosOutputFormat = GacosOutputFormat.GEOTIFF,
    client: GacosClient | None = None,
    email_source: GacosEmailSource = GacosEmailSource.AUTO,
    max_retries: int = 3,
    max_dates_per_batch: int = GACOS_MAX_DATES_PER_REQUEST,
    progress: SubmitProgress | None = None,
) -> GacosRequestRunSummary:
    """Submit a GACOS request for ``dates`` over ``bbox`` in <=20-date batches.

    Splits the dates into batches, submits each to the GACOS web form (unless an
    explicit ``client`` is injected), writes a credential-safe
    ``GACOS/gacos_request_results.csv`` under ``output_root``, and returns
    a :class:`GacosRequestRunSummary`. Per-batch problems are captured as
    ``FAILED`` results (never raised); :class:`InputValidationError` is raised for
    invalid inputs (no dates, bad time-of-day, too many dates per batch).
    """
    unique_dates = sorted({d for d in dates})
    if not unique_dates:
        raise InputValidationError("no acquisition dates to submit", code=ErrorCode.GAC001)
    if not (0 <= hour <= 23):
        raise InputValidationError("hour must be 0-23 (UTC)", code=ErrorCode.GAC003)
    if not (0 <= minute <= 59):
        raise InputValidationError("minute must be 0-59 (UTC)", code=ErrorCode.GAC003)
    if max_dates_per_batch < 1 or max_dates_per_batch > GACOS_MAX_DATES_PER_REQUEST:
        raise InputValidationError(
            f"max_dates_per_batch must be 1-{GACOS_MAX_DATES_PER_REQUEST}", code=ErrorCode.GAC003
        )
    if not _bbox_span_ok(bbox):
        logger.warning(
            "GACOS bbox span exceeds %.0f deg; GACOS may reject the job",
            GACOS_MAX_SPAN_DEGREES,
        )

    active = (
        client
        if client is not None
        else RealGacosClient(email_source=email_source, max_retries=max_retries)
    )

    batches = _chunk(unique_dates, max_dates_per_batch)
    batch_count = len(batches)
    results: list[GacosSubmitResult] = []
    for index, batch in enumerate(batches, start=1):
        request = GacosRequest(
            region_safe_name=region_safe_name,
            bbox=bbox,
            dates=batch,
            hour=hour,
            minute=minute,
            output_format=output_format,
            email=email,
        )
        result = active.submit(request)
        result.batch_index = index
        result.batch_count = batch_count
        results.append(result)
        if progress is not None:
            progress(result)
        logger.info(
            "GACOS request batch %d/%d: %s (%d date(s))%s",
            index,
            batch_count,
            result.outcome.value,
            result.date_count,
            f" [{result.error_code}]" if result.error_code else "",
        )

    results_path = write_gacos_request_results_csv(output_root, results) if results else None
    counts = {outcome: 0 for outcome in GacosSubmitOutcome}
    for result in results:
        counts[result.outcome] += 1
    log_event(
        logger,
        EventType.GACOS_REQUEST_SUBMITTED,
        f"submitted {counts[GacosSubmitOutcome.SUBMITTED]}/{batch_count} GACOS batch(es)",
        module="providers.gacos.download_runner",
        payload={"date_count": len(unique_dates), "batch_count": batch_count},
    )
    return GacosRequestRunSummary(results=results, results_path=results_path, counts=counts)


def run_gacos_download(
    urls: Sequence[str],
    output_directory: Path | str,
    *,
    expected_dates: Sequence[date] | None = None,
    client: GacosClient | None = None,
    email_source: GacosEmailSource = GacosEmailSource.AUTO,
    max_retries: int = 3,
    move: bool = True,
    progress: FetchProgress | None = None,
    cancel_event: Event | None = None,
) -> GacosDownloadRunSummary:
    """Fetch GACOS result archive(s) from ``urls`` and import them.

    Each URL is downloaded to a staging ``downloads/`` folder beside
    ``output_directory`` (the region GACOS ``requests`` dir), then all fetched
    archives are extracted, organized, and integrity-checked by
    :func:`import_gacos_products`. Returns a :class:`GacosDownloadRunSummary`.
    """
    if not urls:
        raise InputValidationError("no GACOS result URLs to download", code=ErrorCode.GAC004)

    output_dir = Path(output_directory)
    staging_dir = output_dir.parent / GACOS_DOWNLOADS_SUBDIR
    staging_dir.mkdir(parents=True, exist_ok=True)

    active = (
        client
        if client is not None
        else RealGacosClient(
            email_source=email_source, max_retries=max_retries, cancel_event=cancel_event
        )
    )

    fetch_results: list[GacosFetchResult] = []
    fetched_archives: list[Path] = []
    cancelled = False
    for index, url in enumerate(urls, start=1):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        destination = staging_dir / _archive_name_for(url, index)
        result = active.fetch(url, destination)
        fetch_results.append(result)
        if progress is not None:
            progress(result)
        if result.outcome in (GacosFetchOutcome.SUCCESS, GacosFetchOutcome.SKIPPED) and result.path:
            fetched_archives.append(result.path)
        logger.info(
            "GACOS fetch %d/%d: %s (%d bytes)%s",
            index,
            len(urls),
            result.outcome.value,
            result.bytes_written,
            f" [{result.error_code}]" if result.error_code else "",
        )
        if result.outcome is GacosFetchOutcome.INTERRUPTED:
            cancelled = True
            break

    import_result: GacosImportResult | None = None
    if fetched_archives:
        import_result = import_gacos_products(
            fetched_archives,
            output_dir,
            expected_dates=expected_dates,
            move=move,
        )

    results_path = (
        write_gacos_fetch_results_csv(output_dir, fetch_results) if fetch_results else None
    )
    counts = {outcome: 0 for outcome in GacosFetchOutcome}
    for result in fetch_results:
        counts[result.outcome] += 1
    log_event(
        logger,
        EventType.GACOS_DOWNLOAD_FINISHED,
        f"fetched {counts[GacosFetchOutcome.SUCCESS]}/{len(urls)} GACOS archive(s)",
        module="providers.gacos.download_runner",
        payload={"url_count": len(urls)},
    )
    return GacosDownloadRunSummary(
        fetch_results=fetch_results,
        import_result=import_result,
        results_path=results_path,
        counts=counts,
        cancelled=cancelled,
    )


def _archive_name_for(url: str, index: int) -> str:
    """Derive a safe local archive filename from a result URL (fallback by index)."""
    from urllib.parse import unquote, urlsplit  # noqa: PLC0415 - local helper

    path = urlsplit(url).path
    name = Path(unquote(path)).name
    archive_suffixes = (".zip", ".tar.gz", ".tgz", ".tar")
    if name and any(name.lower().endswith(suffix) for suffix in archive_suffixes):
        return name
    if name:
        return f"{name}.zip" if "." not in name else name
    return f"gacos_result_{index}.zip"


def raise_for_missing_download_extra() -> None:
    """Raise a clear :class:`InsarPrepError` (GAC004) if ``requests`` is unavailable."""
    import importlib.util  # noqa: PLC0415 - local guard

    if importlib.util.find_spec("requests") is None:
        raise InsarPrepError(
            "real GACOS request/download needs the optional 'download' extra; install "
            "it with 'uv sync --extra download' (or pip install requests)",
            code=ErrorCode.GAC004,
        )
