"""Shared orchestration for real ASF Sentinel-1 SLC download.

Wraps the credential-safe primitives -- credential resolution, request building,
the real downloader, and a credential-masked results CSV -- into a single
synchronous :func:`run_asf_download` call that both a background GUI worker and
other callers can reuse, so the download orchestration lives in exactly one place.

It is offline-testable: inject a fake ``downloader`` and ``resolver`` to exercise
the success / failure / cancel paths without any network or real Earthdata
account. Real download still needs the optional ``download`` extra (``requests``),
which the :class:`~insar_prep.providers.asf.downloader.RealAsfDownloader` imports
lazily; this module never imports ``requests`` itself.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.providers.asf.credentials import CredentialSource, resolve_credentials
from insar_prep.providers.asf.download_plan import SLC_SUBDIR
from insar_prep.providers.asf.downloader import (
    AsfDownloader,
    DownloadOutcome,
    DownloadResult,
    RealAsfDownloader,
    download_requests_from_scenes,
)
from insar_prep.providers.asf.scene_parser import deduplicate_scenes

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from threading import Event

    from insar_prep.providers.asf.credentials import ResolvedCredential

    ProgressCallback = Callable[[DownloadResult], None]
    CredentialResolver = Callable[[CredentialSource], ResolvedCredential]

logger = get_logger("providers.asf.download_runner")

# Fixed, credential-safe results CSV columns (mirrors the CLI ``download-asf``
# results file so a plan directory looks identical regardless of entry point).
DOWNLOAD_RESULT_COLUMNS = [
    "scene_id",
    "outcome",
    "bytes_written",
    "error_code",
    "message",
]


def write_download_results_csv(output_dir: Path | str, results: Sequence[DownloadResult]) -> Path:
    """Write a credential-masked per-scene results CSV; return its path."""
    plan_dir = Path(output_dir) / "asf_download_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    results_path = plan_dir / "asf_download_results.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DOWNLOAD_RESULT_COLUMNS)
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


@dataclass(frozen=True)
class DownloadRunSummary:
    """Aggregate outcome of a :func:`run_asf_download` call."""

    results: list[DownloadResult]
    results_path: Path | None
    counts: dict[DownloadOutcome, int]
    cancelled: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return self.counts.get(DownloadOutcome.SUCCESS, 0)

    @property
    def skipped(self) -> int:
        return self.counts.get(DownloadOutcome.SKIPPED, 0)

    @property
    def failed(self) -> int:
        return self.counts.get(DownloadOutcome.FAILED, 0)

    @property
    def interrupted(self) -> int:
        return self.counts.get(DownloadOutcome.INTERRUPTED, 0)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0 or self.interrupted > 0

    def summary_line(self) -> str:
        """A short, credential-free one-line summary for a status bar/log."""
        return (
            f"{self.succeeded} downloaded, {self.skipped} skipped, "
            f"{self.failed} failed, {self.interrupted} interrupted"
        )


def run_asf_download(
    scenes: Iterable[object],
    output_dir: Path | str,
    *,
    credential_source: CredentialSource = CredentialSource.AUTO,
    downloader: AsfDownloader | None = None,
    resolver: CredentialResolver = resolve_credentials,
    max_retries: int = 3,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> DownloadRunSummary:
    """Download the SLCs implied by ``scenes`` into ``<output_dir>/02_slc``.

    Resolves Earthdata credentials (unless an explicit ``downloader`` is given),
    downloads each unique scene that carries a URL, writes a credential-masked
    ``asf_download_plan/asf_download_results.csv``, and returns a
    :class:`DownloadRunSummary`.

    Per-scene transport/credential problems are captured as ``FAILED`` results
    (never raised). :class:`~insar_prep.core.exceptions.InsarPrepError` is raised
    only when there is nothing to download, and the resolver may raise
    :class:`~insar_prep.core.exceptions.CredentialError` when no credentials are
    configured. Pass ``progress`` to receive each :class:`DownloadResult` as it
    completes, and ``cancel_event`` to stop cleanly between (and within) scenes.
    """
    output_path = Path(output_dir)
    unique_scenes, _duplicates = deduplicate_scenes(list(scenes))
    requests_to_run = download_requests_from_scenes(unique_scenes, slc_dir=output_path / SLC_SUBDIR)
    if not requests_to_run:
        raise InsarPrepError(
            "no scenes with a download URL; import an ASF cart that includes download URLs",
            code=ErrorCode.ASF003,
        )

    active = downloader
    if active is None:
        resolved = resolver(credential_source)
        active = RealAsfDownloader(
            resolved=resolved, max_retries=max_retries, cancel_event=cancel_event
        )

    results: list[DownloadResult] = []
    cancelled = False
    for request in requests_to_run:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        result = active.download(request)
        results.append(result)
        if progress is not None:
            progress(result)
        logger.info(
            "scene %s: %s (%d bytes)%s",
            result.scene_id,
            result.outcome.value,
            result.bytes_written,
            f" [{result.error_code}]" if result.error_code else "",
        )
        if result.outcome is DownloadOutcome.INTERRUPTED:
            cancelled = True
            break

    results_path = write_download_results_csv(output_path, results) if results else None
    counts = {outcome: 0 for outcome in DownloadOutcome}
    for result in results:
        counts[result.outcome] += 1
    return DownloadRunSummary(
        results=results, results_path=results_path, counts=counts, cancelled=cancelled
    )
