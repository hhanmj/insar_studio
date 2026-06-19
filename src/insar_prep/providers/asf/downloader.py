"""ASF SLC downloader interface and an offline fake (Task 035).

Defines the interface a *future* real ASF downloader will implement, plus a
:class:`FakeAsfDownloader` for offline testing of retry/error/cancellation
paths. **Nothing here performs real network I/O, reads credentials, or downloads
real SAR data.** :class:`RealAsfDownloader` is a deliberate ``NotImplemented``
stub: real, credentialed ASF/Earthdata download is a separate, later,
user-authorized task (see ``docs/asf_download_credential_design.md``).

No new dependency: standard library + pydantic only (no requests/aiohttp/httpx).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.logging import get_logger
from insar_prep.core.models import InsarBaseModel

logger = get_logger("providers.asf.downloader")


class DownloadOutcome(StrEnum):
    """Outcome of a (fake) download attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


class DownloadRequest(InsarBaseModel):
    """A single planned SLC download request (credential-free).

    The ``url`` is optional and, if provided, is never logged verbatim; the fake
    needs only the destination and identifiers.
    """

    scene_id: str
    expected_filename: str
    destination: Path
    url: str | None = None
    expected_size: int | None = None


class DownloadResult(InsarBaseModel):
    """The outcome of a (fake) download attempt."""

    scene_id: str
    outcome: DownloadOutcome
    path: Path | None = None
    bytes_written: int = 0
    message: str = ""
    error_code: str | None = None


@runtime_checkable
class AsfDownloader(Protocol):
    """The interface a real or fake ASF downloader must implement."""

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Download (or simulate downloading) one SLC and return the result."""
        ...


class FakeAsfDownloader:
    """An offline, deterministic fake downloader for tests.

    It never opens a socket, reads credentials, or writes a real SLC archive. By
    default it writes nothing; with ``write_placeholder=True`` it writes a tiny
    text marker (with a ``.fake`` / ``.part`` extension -- never ``.zip`` or
    ``.SAFE``). The ``outcome`` controls whether it simulates success, failure,
    or an interrupted (partial) transfer so downstream error handling can be
    exercised offline.
    """

    def __init__(
        self,
        *,
        outcome: DownloadOutcome = DownloadOutcome.SUCCESS,
        write_placeholder: bool = False,
    ) -> None:
        self.outcome = outcome
        self.write_placeholder = write_placeholder
        self.calls: list[str] = []

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Simulate one download. Never touches the network or credentials."""
        self.calls.append(request.scene_id)
        logger.debug("fake download for %s (outcome=%s)", request.scene_id, self.outcome.value)

        if self.outcome is DownloadOutcome.FAILED:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message="simulated download failure",
                error_code=ErrorCode.DL001.value,
            )

        if self.outcome is DownloadOutcome.INTERRUPTED:
            bytes_written = 0
            if self.write_placeholder:
                part_path = request.destination.with_suffix(".part")
                part_path.parent.mkdir(parents=True, exist_ok=True)
                part_path.write_text("partial-fake-transfer\n", encoding="utf-8")
                bytes_written = part_path.stat().st_size
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.INTERRUPTED,
                bytes_written=bytes_written,
                message="simulated interrupted transfer (.part not finalized)",
                error_code=ErrorCode.DL001.value,
            )

        path: Path | None = None
        bytes_written = 0
        if self.outcome is DownloadOutcome.SUCCESS and self.write_placeholder:
            marker = request.destination.with_suffix(".fake")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("fake-slc-placeholder\n", encoding="utf-8")
            path = marker
            bytes_written = marker.stat().st_size
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=self.outcome,
            path=path,
            bytes_written=bytes_written,
            message="fake download ok" if self.outcome is DownloadOutcome.SUCCESS else "skipped",
        )


class RealAsfDownloader:
    """Placeholder for the future real ASF downloader (NOT implemented).

    Real, credentialed ASF/Earthdata download is a separate, later, explicitly
    user-authorized task. Both construction and :meth:`download` raise
    ``NotImplementedError`` so this class can never accidentally perform network
    I/O or read credentials. See ``docs/asf_download_credential_design.md``.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "Real ASF download is not implemented; use FakeAsfDownloader for tests. "
            "See docs/asf_download_credential_design.md."
        )

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Always raises; real download is a separate, future task."""
        raise NotImplementedError("Real ASF download is not implemented.")
