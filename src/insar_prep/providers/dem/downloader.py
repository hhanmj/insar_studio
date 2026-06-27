"""OpenTopography DEM downloader interface, an offline fake, and the real one.

Defines the :class:`DemDownloader` interface, a :class:`FakeDemDownloader` for
offline testing of retry/error/cancellation paths, and :class:`RealDemDownloader`
-- a key-authenticated client for the OpenTopography Global DEM API
(``GET /API/globaldem``; see ``THIRD_PARTY_REFERENCES.md`` #3). The interface
concept (datatype enum + bbox params + GeoTIFF output) is borrowed from the
OpenTopography API docs and the local ``DEMdownloader`` reference (#8, concept
only -- no source code is copied).

The real downloader needs the optional ``download`` extra (``requests``), which
is imported lazily so the offline core (``prepare`` / ``plan-asf-downloads`` /
``gui``) never depends on it. It follows the same credential-safety contract as
the ASF downloader: the API key lives only in memory and is passed as the
``API_Key`` query parameter (never logged -- the request URL is never logged
verbatim, and ``mask_text`` redacts ``API_Key=`` anyway), downloads stream to a
``.part`` file and are atomically renamed only after a verified, non-empty
GeoTIFF, and every error string is masked before it is logged or returned.
"""

from __future__ import annotations

import os
import time
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from insar_prep.core.enums import DemDataset
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import BBox, InsarBaseModel
from insar_prep.providers.dem.credentials import (
    DemKeySource,
    ResolvedDemKey,
    resolve_dem_api_key,
)

if TYPE_CHECKING:
    from threading import Event

logger = get_logger("providers.dem.downloader")

# OpenTopography Global DEM API endpoint (raster GeoTIFF by bbox).
OPENTOPO_GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"
OPENTOPO_OUTPUT_FORMAT = "GTiff"

_DEFAULT_CHUNK_SIZE = 1024 * 1024
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF = 2.0

# A tiny bbox (~0.01 deg) used by the network preflight (``verify``): proves the
# key + endpoint work and return a valid GeoTIFF without pulling the full AOI.
_VERIFY_BBOX_SPAN = 0.01

# GeoTIFF magic numbers: little-endian ("II", 0x2A) and big-endian ("MM", 0x2A).
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")

# Maps our DemDataset enum to the OpenTopography ``demtype`` parameter. Datasets
# without a global-DEM equivalent (USER_LOCAL) map to None and cannot be fetched.
_DATASET_TO_DEMTYPE: dict[str, str] = {
    DemDataset.COP30.value: "COP30",
    DemDataset.COP90.value: "COP90",
    DemDataset.SRTM_GL3.value: "SRTMGL3",
    DemDataset.SRTM_GL1.value: "SRTMGL1",
    DemDataset.SRTM_GL1_ELLIPSOIDAL.value: "SRTMGL1_E",
    DemDataset.NASADEM.value: "NASADEM",
    DemDataset.AW3D30.value: "AW3D30",
    DemDataset.AW3D30_ELLIPSOIDAL.value: "AW3D30_E",
}


def opentopo_demtype(dataset: DemDataset | str) -> str | None:
    """Return the OpenTopography ``demtype`` for ``dataset`` (None if unsupported)."""
    value = dataset.value if isinstance(dataset, DemDataset) else str(dataset)
    return _DATASET_TO_DEMTYPE.get(value)


class DemDownloadOutcome(StrEnum):
    """Outcome of a DEM download (or preflight) attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"
    VERIFIED = "verified"


class DemDownloadRequest(InsarBaseModel):
    """A single planned DEM download request (credential-free).

    The API key is never part of this request; it is resolved separately at the
    auth boundary so the request can be logged/serialized safely.
    """

    region_safe_name: str
    dataset: str
    demtype: str
    bbox: BBox
    destination: Path


class DemDownloadResult(InsarBaseModel):
    """The outcome of a DEM download attempt."""

    region_safe_name: str
    dataset: str
    outcome: DemDownloadOutcome
    path: Path | None = None
    bytes_written: int = 0
    message: str = ""
    error_code: str | None = None


@runtime_checkable
class DemDownloader(Protocol):
    """The interface a real or fake DEM downloader must implement."""

    def download(self, request: DemDownloadRequest) -> DemDownloadResult:
        """Download (or simulate downloading) one DEM and return the result."""
        ...


class FakeDemDownloader:
    """An offline, deterministic fake DEM downloader for tests.

    It never opens a socket, reads an API key, or writes a real GeoTIFF. By
    default it writes nothing; with ``write_placeholder=True`` it writes a tiny
    marker file (``.fake`` / ``.part`` extension -- never ``.tif``). The
    ``outcome`` controls whether it simulates success, failure, or an interrupted
    transfer so downstream error handling can be exercised offline.
    """

    def __init__(
        self,
        *,
        outcome: DemDownloadOutcome = DemDownloadOutcome.SUCCESS,
        write_placeholder: bool = False,
    ) -> None:
        self.outcome = outcome
        self.write_placeholder = write_placeholder
        self.calls: list[str] = []

    def download(self, request: DemDownloadRequest) -> DemDownloadResult:
        """Simulate one download. Never touches the network or the API key."""
        self.calls.append(request.demtype)
        logger.debug(
            "fake DEM download for %s/%s (outcome=%s)",
            request.region_safe_name,
            request.demtype,
            self.outcome.value,
        )

        if self.outcome is DemDownloadOutcome.FAILED:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message="simulated DEM download failure",
                error_code=ErrorCode.DEM001.value,
            )

        if self.outcome is DemDownloadOutcome.INTERRUPTED:
            bytes_written = 0
            if self.write_placeholder:
                part_path = request.destination.with_suffix(".part")
                part_path.parent.mkdir(parents=True, exist_ok=True)
                part_path.write_text("partial-fake-dem\n", encoding="utf-8")
                bytes_written = part_path.stat().st_size
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.INTERRUPTED,
                bytes_written=bytes_written,
                message="simulated interrupted transfer (.part not finalized)",
                error_code=ErrorCode.DEM001.value,
            )

        path: Path | None = None
        bytes_written = 0
        if self.outcome is DemDownloadOutcome.SUCCESS and self.write_placeholder:
            marker = request.destination.with_suffix(".fake")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("fake-dem-placeholder\n", encoding="utf-8")
            path = marker
            bytes_written = marker.stat().st_size
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=self.outcome,
            path=path,
            bytes_written=bytes_written,
            message=("fake DEM ok" if self.outcome is DemDownloadOutcome.SUCCESS else "skipped"),
        )


class _KeyRejected(Exception):
    """OpenTopography rejected the API key (HTTP 401/403). Not retryable."""


class _FatalRequest(Exception):
    """A non-retryable request failure (e.g. HTTP 400 bad params)."""


class _TransientError(Exception):
    """A retryable failure (timeout, connection reset, 429, 5xx)."""


class _IntegrityMismatch(Exception):
    """The response was not a valid / non-empty GeoTIFF. Retryable."""


class _Cancelled(Exception):
    """The caller requested cancellation mid-transfer."""


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Content-Length") or headers.get("content-length")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _content_type(response: object) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("Content-Type") or headers.get("content-type") or "").lower()


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best-effort cleanup
        logger.debug("could not remove partial file %s", path)


def build_opentopo_session() -> object:
    """Build a plain ``requests`` session (lazy import; needs the ``download`` extra).

    The OpenTopography API authenticates via the ``API_Key`` query parameter, so
    no auth header or redirect handling is required -- a vanilla session suffices.
    """
    try:
        import requests  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - exercised via CLI guard
        raise CredentialError(
            "the 'download' extra is required for real DEM download; install it with "
            "'uv sync --extra download' (or pip install requests)",
            code=ErrorCode.DEM005,
        ) from exc
    return requests.Session()


class RealDemDownloader:
    """Key-authenticated OpenTopography Global DEM downloader.

    Construction performs no network I/O and reads no secret: the API key is
    resolved and the session built lazily on the first :meth:`download`. The key
    is taken from :func:`resolve_dem_api_key` (keyring or ``OPENTOPOGRAPHY_API_KEY``
    env) and never persisted. For tests, an alternative ``session`` may be
    injected so the transfer logic runs without ``requests`` or the network.
    """

    def __init__(
        self,
        *,
        key_source: DemKeySource = DemKeySource.AUTO,
        resolved: ResolvedDemKey | None = None,
        session: object | None = None,
        endpoint: str = OPENTOPO_GLOBALDEM_URL,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_seconds: float = _DEFAULT_BACKOFF,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        timeout: float = _DEFAULT_TIMEOUT,
        cancel_event: Event | None = None,
    ) -> None:
        self.key_source = key_source
        self.endpoint = endpoint
        self.max_retries = max(1, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.chunk_size = max(1, chunk_size)
        self.timeout = timeout
        self.cancel_event = cancel_event
        self._resolved = resolved
        self._session = session

    def _ensure_session(self) -> tuple[object, ResolvedDemKey]:
        if self._resolved is None:
            self._resolved = resolve_dem_api_key(self.key_source)
        if self._session is None:
            self._session = build_opentopo_session()
        return self._session, self._resolved

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def _params(self, demtype: str, bbox: BBox, api_key: str) -> dict[str, str]:
        return {
            "demtype": demtype,
            "south": f"{bbox.south}",
            "north": f"{bbox.north}",
            "west": f"{bbox.west}",
            "east": f"{bbox.east}",
            "outputFormat": OPENTOPO_OUTPUT_FORMAT,
            "API_Key": api_key,
        }

    def download(self, request: DemDownloadRequest) -> DemDownloadResult:
        """Download one DEM, returning a :class:`DemDownloadResult` (never raises)."""
        dest = request.destination
        part = dest.with_name(dest.name + ".part")

        if dest.exists() and dest.stat().st_size > 0:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.SKIPPED,
                path=dest,
                bytes_written=dest.stat().st_size,
                message="already present; skipped",
            )

        if not request.demtype:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message=f"dataset {request.dataset!r} has no OpenTopography demtype",
                error_code=ErrorCode.DEM001.value,
            )

        try:
            session, resolved = self._ensure_session()
        except CredentialError as exc:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message=mask_text(str(exc)),
                error_code=ErrorCode.DEM005.value,
            )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            if self._cancelled():
                return self._interrupted(request)
            try:
                return self._attempt(session, resolved, request, dest, part)
            except _KeyRejected:
                _safe_unlink(part)
                return DemDownloadResult(
                    region_safe_name=request.region_safe_name,
                    dataset=request.dataset,
                    outcome=DemDownloadOutcome.FAILED,
                    message="OpenTopography API key was rejected (HTTP 401/403)",
                    error_code=ErrorCode.DEM005.value,
                )
            except _Cancelled:
                return self._interrupted(request)
            except _FatalRequest as exc:
                _safe_unlink(part)
                return DemDownloadResult(
                    region_safe_name=request.region_safe_name,
                    dataset=request.dataset,
                    outcome=DemDownloadOutcome.FAILED,
                    message=mask_text(str(exc)),
                    error_code=ErrorCode.DEM001.value,
                )
            except (_TransientError, _IntegrityMismatch) as exc:
                last_error = exc
                _safe_unlink(part)
            except Exception as exc:  # noqa: BLE001 - transport errors are masked + retried
                last_error = exc
                _safe_unlink(part)
            if attempt < self.max_retries and not self._cancelled():
                time.sleep(self.backoff_seconds * attempt)

        detail = mask_text(f"{type(last_error).__name__}: {last_error}") if last_error else ""
        logger.warning(
            "DEM download failed for %s/%s after %d attempts",
            request.region_safe_name,
            request.demtype,
            self.max_retries,
        )
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=DemDownloadOutcome.FAILED,
            message=f"DEM download failed after {self.max_retries} attempts: {detail}".strip(),
            error_code=ErrorCode.DEM001.value,
        )

    def _attempt(
        self,
        session: object,
        resolved: ResolvedDemKey,
        request: DemDownloadRequest,
        dest: Path,
        part: Path,
    ) -> DemDownloadResult:
        part.parent.mkdir(parents=True, exist_ok=True)
        params = self._params(request.demtype, request.bbox, resolved.api_key)
        written = 0
        first_chunk_checked = False
        with session.get(  # type: ignore[attr-defined]
            self.endpoint, params=params, stream=True, timeout=self.timeout
        ) as response:
            status = int(getattr(response, "status_code", 200))
            if status in (401, 403):
                raise _KeyRejected()
            if status == 429 or status >= 500:
                raise _TransientError(f"HTTP {status} from OpenTopography")
            if status >= 400:
                raise _FatalRequest(f"HTTP {status} from OpenTopography (check bbox/dataset/key)")
            ctype = _content_type(response)
            if "html" in ctype or "json" in ctype or ctype.startswith("text/"):
                raise _FatalRequest(f"OpenTopography returned a non-raster response ({ctype})")
            with part.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._cancelled():
                        raise _Cancelled()
                    if not chunk:
                        continue
                    if not first_chunk_checked:
                        first_chunk_checked = True
                        if not chunk.startswith(_TIFF_MAGIC):
                            raise _IntegrityMismatch("response is not a GeoTIFF")
                    handle.write(chunk)
                    written += len(chunk)

        if written == 0:
            raise _IntegrityMismatch("received an empty DEM response")
        total = _content_length(response)
        if total is not None and written != total:
            raise _IntegrityMismatch(f"expected {total} bytes but received {written}")

        os.replace(part, dest)
        logger.info("downloaded DEM %s (%d bytes)", request.region_safe_name, written)
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=DemDownloadOutcome.SUCCESS,
            path=dest,
            bytes_written=written,
            message="downloaded",
        )

    def _interrupted(self, request: DemDownloadRequest) -> DemDownloadResult:
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=DemDownloadOutcome.INTERRUPTED,
            message="cancelled by user; partial .part kept",
            error_code=ErrorCode.DEM001.value,
        )

    def verify(self, request: DemDownloadRequest) -> DemDownloadResult:
        """Network preflight: fetch a tiny bbox to confirm key + endpoint work.

        Requests a ~0.01 deg sub-box around the AOI's south-west corner so the
        whole chain (key resolution -> OpenTopography API -> valid GeoTIFF) is
        proven without downloading the full DEM. Nothing is written to disk.
        Returns a result with outcome :attr:`DemDownloadOutcome.VERIFIED` on
        success (or ``FAILED``); never raises.
        """
        if not request.demtype:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message=f"dataset {request.dataset!r} has no OpenTopography demtype",
                error_code=ErrorCode.DEM001.value,
            )
        try:
            session, resolved = self._ensure_session()
        except CredentialError as exc:
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message=mask_text(str(exc)),
                error_code=ErrorCode.DEM005.value,
            )

        bbox = request.bbox
        tiny = BBox(
            west=bbox.west,
            south=bbox.south,
            east=min(bbox.east, bbox.west + _VERIFY_BBOX_SPAN),
            north=min(bbox.north, bbox.south + _VERIFY_BBOX_SPAN),
        )
        params = self._params(request.demtype, tiny, resolved.api_key)
        try:
            with session.get(  # type: ignore[attr-defined]
                self.endpoint, params=params, stream=True, timeout=self.timeout
            ) as response:
                status = int(getattr(response, "status_code", 200))
                if status in (401, 403):
                    return DemDownloadResult(
                        region_safe_name=request.region_safe_name,
                        dataset=request.dataset,
                        outcome=DemDownloadOutcome.FAILED,
                        message="OpenTopography API key was rejected (HTTP 401/403)",
                        error_code=ErrorCode.DEM005.value,
                    )
                if status >= 400:
                    return DemDownloadResult(
                        region_safe_name=request.region_safe_name,
                        dataset=request.dataset,
                        outcome=DemDownloadOutcome.FAILED,
                        message=f"HTTP {status} from OpenTopography",
                        error_code=ErrorCode.DEM001.value,
                    )
                sample = b""
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        sample = chunk
                        break
        except Exception as exc:  # noqa: BLE001 - transport errors are masked, not raised
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message=mask_text(f"{type(exc).__name__}: {exc}"),
                error_code=ErrorCode.DEM001.value,
            )

        if not sample.startswith(_TIFF_MAGIC):
            return DemDownloadResult(
                region_safe_name=request.region_safe_name,
                dataset=request.dataset,
                outcome=DemDownloadOutcome.FAILED,
                message="preflight did not return a GeoTIFF (check dataset/key)",
                error_code=ErrorCode.DEM001.value,
            )
        logger.info("verified OpenTopography DEM access for %s", request.region_safe_name)
        return DemDownloadResult(
            region_safe_name=request.region_safe_name,
            dataset=request.dataset,
            outcome=DemDownloadOutcome.VERIFIED,
            bytes_written=len(sample),
            message="key valid and OpenTopography reachable",
        )


def dem_download_request_from_plan(plan: object) -> DemDownloadRequest | None:
    """Build a :class:`DemDownloadRequest` from a ``DemRequestPlan`` (None if unsupported).

    Uses the plan's buffered ``request_bbox``, dataset, and ``raw_dem_path`` so the
    real download lands exactly where the offline planner said it would. Returns
    ``None`` for datasets without an OpenTopography demtype (e.g. USER_LOCAL).
    """
    dataset = getattr(plan, "dataset", "")
    demtype = opentopo_demtype(dataset)
    if demtype is None:
        return None
    return DemDownloadRequest(
        region_safe_name=getattr(plan, "region_safe_name", ""),
        dataset=dataset,
        demtype=demtype,
        bbox=plan.request_bbox,
        destination=plan.raw_dem_path,
    )
