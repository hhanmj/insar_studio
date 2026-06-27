"""ASF Sentinel-1 downloader interface, an offline fake, and the real downloader.

Defines the :class:`AsfDownloader` interface, a :class:`FakeAsfDownloader` for
offline testing of retry/error/cancellation paths, and :class:`RealAsfDownloader`
-- a credentialed, NASA Earthdata-authenticated Sentinel-1 SLC downloader.

The real downloader needs the optional ``download`` extra (``requests``), which
is imported lazily so the offline core (``prepare`` / ``plan-asf-downloads`` /
``gui``) never depends on it. It follows the credential-safety contract in
``docs/asf_download_credential_design.md``: credentials live only in memory, the
auth header is preserved only across Earthdata/ASF hosts (never re-sent to a
signed S3 redirect target), downloads stream to a ``.part`` file and are atomically
renamed only after a verified size, and every error string is masked before it is
logged or returned.
"""

from __future__ import annotations

import os
import time
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable
from urllib.parse import urlsplit

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import InsarBaseModel
from insar_prep.providers.asf.credentials import (
    CredentialSource,
    ResolvedCredential,
    resolve_credentials,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from threading import Event

logger = get_logger("providers.asf.downloader")

# Hosts that may keep the Authorization header across redirects. A signed S3 /
# CloudFront data-pool URL is NOT in this list, so the bearer token is dropped
# before it could leak to the storage backend (concept borrowed from
# asf_search's ASFSession; see THIRD_PARTY_REFERENCES.md #1).
_EARTHDATA_AUTH_HOSTS = (
    "urs.earthdata.nasa.gov",
    ".earthdata.nasa.gov",
    ".asf.alaska.edu",
    ".earthdatacloud.nasa.gov",
)

_DEFAULT_CHUNK_SIZE = 1024 * 1024
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF = 2.0
# Bytes fetched by the network preflight (``verify``): enough to prove the whole
# credential -> EDL -> data-pool -> signed-redirect chain works without pulling
# the multi-GB SLC archive.
_DEFAULT_VERIFY_BYTES = 64 * 1024


class DownloadOutcome(StrEnum):
    """Outcome of a (fake) download attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"
    VERIFIED = "verified"


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


class _CredentialRejected(Exception):
    """Server rejected the credentials (HTTP 401/403). Not retryable."""


class _FatalTransport(Exception):
    """A non-retryable transport failure (e.g. HTTP 404)."""


class _TransientError(Exception):
    """A retryable transport failure (timeout, connection reset, 429, 5xx)."""


class _IntegrityMismatch(Exception):
    """Downloaded byte count did not match the expected size. Retryable."""


class _Cancelled(Exception):
    """The caller requested cancellation mid-transfer."""


def _host_allows_auth(host: str) -> bool:
    """Return True if ``host`` is an Earthdata/ASF host allowed to keep auth."""
    host = (host or "").lower()
    for allowed in _EARTHDATA_AUTH_HOSTS:
        if allowed.startswith("."):
            if host == allowed[1:] or host.endswith(allowed):
                return True
        elif host == allowed:
            return True
    return False


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Content-Length") or headers.get("content-length")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _content_range_total(response: object) -> int | None:
    """Parse the total size from a ``Content-Range: bytes 0-N/TOTAL`` header."""
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Content-Range") or headers.get("content-range")
    if not raw or "/" not in str(raw):
        return None
    total = str(raw).rsplit("/", 1)[-1].strip()
    try:
        return int(total)
    except (TypeError, ValueError):
        return None


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best-effort cleanup
        logger.debug("could not remove partial file %s", path)


def build_earthdata_session(resolved: ResolvedCredential) -> object:
    """Build a redirect-aware authenticated ``requests`` session (lazy import).

    The returned session keeps the bearer token only for Earthdata/ASF hosts and
    drops it before a signed S3 redirect. ``.netrc`` Basic auth is delegated to
    ``requests`` via ``trust_env``. Requires the optional ``download`` extra.
    """
    try:
        import requests  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - exercised via CLI guard
        raise CredentialError(
            "the 'download' extra is required for real download; install it with "
            "'uv sync --extra download' (or pip install requests)",
            code=ErrorCode.DL004,
        ) from exc

    class _EarthdataSession(requests.Session):
        """Session that confines the auth header to Earthdata/ASF hosts."""

        def rebuild_auth(self, prepared_request: object, response: object) -> None:
            headers = prepared_request.headers  # type: ignore[attr-defined]
            if "Authorization" in headers:
                host = urlsplit(prepared_request.url).hostname or ""  # type: ignore[attr-defined]
                if not _host_allows_auth(host):
                    del headers["Authorization"]

    session = _EarthdataSession()
    session.trust_env = True  # read ~/.netrc for Basic auth on EDL hosts
    if resolved.token:
        session.headers["Authorization"] = f"Bearer {resolved.token}"
    elif resolved.username and resolved.password:
        import base64  # noqa: PLC0415 - only needed for the basic-auth path

        encoded = base64.b64encode(f"{resolved.username}:{resolved.password}".encode()).decode(
            "ascii"
        )
        basic_header = f"Basic {encoded}"

        class _EdlBasicAuth(requests.auth.AuthBase):
            """Apply Basic auth only to Earthdata/ASF hosts (never to S3)."""

            def __call__(self, request: object) -> object:
                host = urlsplit(request.url).hostname or ""  # type: ignore[attr-defined]
                if _host_allows_auth(host):
                    request.headers["Authorization"] = basic_header  # type: ignore[attr-defined]
                return request

        session.auth = _EdlBasicAuth()
    return session


class RealAsfDownloader:
    """Credentialed ASF Sentinel-1 SLC downloader (NASA Earthdata Login).

    Construction performs no network I/O and reads no secrets: the authenticated
    session is built lazily on the first :meth:`download`. Credentials are taken
    from :func:`resolve_credentials` (``EARTHDATA_TOKEN`` env or ``~/.netrc``) and
    never persisted. For tests, an alternative ``session`` may be injected so the
    transfer logic runs without ``requests`` or the network.
    """

    def __init__(
        self,
        *,
        credential_source: CredentialSource = CredentialSource.AUTO,
        resolved: ResolvedCredential | None = None,
        session: object | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_seconds: float = _DEFAULT_BACKOFF,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        timeout: float = _DEFAULT_TIMEOUT,
        verify_bytes: int = _DEFAULT_VERIFY_BYTES,
        cancel_event: Event | None = None,
        pause_event: Event | None = None,
        progress_callback: Callable[[str, int, int | None], None] | None = None,
    ) -> None:
        self.credential_source = credential_source
        self.max_retries = max(1, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.chunk_size = max(1, chunk_size)
        self.timeout = timeout
        self.verify_bytes = max(1, verify_bytes)
        self.cancel_event = cancel_event
        self.pause_event = pause_event
        self.progress_callback = progress_callback
        self._resolved = resolved
        self._session = session

    def _ensure_session(self) -> object:
        if self._session is None:
            if self._resolved is None:
                self._resolved = resolve_credentials(self.credential_source)
            self._session = build_earthdata_session(self._resolved)
        return self._session

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def _paused(self) -> bool:
        return self.pause_event is not None and self.pause_event.is_set()

    def _wait_if_paused(self) -> None:
        while self._paused() and not self._cancelled():
            time.sleep(0.2)
        if self._cancelled():
            raise _Cancelled()

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Download one SLC, returning a :class:`DownloadResult` (never raises)."""
        dest = request.destination
        part = dest.with_name(dest.name + ".part")

        if dest.exists() and (
            request.expected_size is None or dest.stat().st_size == request.expected_size
        ):
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.SKIPPED,
                path=dest,
                bytes_written=dest.stat().st_size,
                message="already complete; skipped",
            )

        if part.exists() and request.expected_size is not None:
            part_size = part.stat().st_size
            if part_size == request.expected_size:
                part.parent.mkdir(parents=True, exist_ok=True)
                os.replace(part, dest)
                return DownloadResult(
                    scene_id=request.scene_id,
                    outcome=DownloadOutcome.SUCCESS,
                    path=dest,
                    bytes_written=part_size,
                    message="existing .part matched expected size; finalized",
                )
            if part_size > request.expected_size:
                _safe_unlink(part)

        if not request.url:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message="no download URL for scene",
                error_code=ErrorCode.ASF003.value,
            )

        try:
            session = self._ensure_session()
        except CredentialError as exc:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message=mask_text(str(exc)),
                error_code=ErrorCode.DL004.value,
            )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            if self._cancelled():
                return self._interrupted(request)
            try:
                return self._attempt(session, request, dest, part)
            except _CredentialRejected:
                _safe_unlink(part)
                return DownloadResult(
                    scene_id=request.scene_id,
                    outcome=DownloadOutcome.FAILED,
                    message="Earthdata credentials were rejected (HTTP 401/403)",
                    error_code=ErrorCode.DL004.value,
                )
            except _Cancelled:
                return self._interrupted(request)
            except _FatalTransport as exc:
                _safe_unlink(part)
                return DownloadResult(
                    scene_id=request.scene_id,
                    outcome=DownloadOutcome.FAILED,
                    message=mask_text(str(exc)),
                    error_code=ErrorCode.DL005.value,
                )
            except _TransientError as exc:
                last_error = exc
                _safe_unlink(part)
            except _IntegrityMismatch as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    _safe_unlink(part)
            except Exception as exc:  # noqa: BLE001 - transport errors are masked + retried
                last_error = exc
                _safe_unlink(part)
            if attempt < self.max_retries and not self._cancelled():
                time.sleep(self.backoff_seconds * attempt)

        detail = mask_text(f"{type(last_error).__name__}: {last_error}") if last_error else ""
        code = ErrorCode.DL002 if isinstance(last_error, _IntegrityMismatch) else ErrorCode.DL005
        logger.warning(
            "download failed for %s after %d attempts", request.scene_id, self.max_retries
        )
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=DownloadOutcome.FAILED,
            message=f"download failed after {self.max_retries} attempts: {detail}".strip(),
            error_code=code.value,
        )

    def _attempt(
        self,
        session: object,
        request: DownloadRequest,
        dest: Path,
        part: Path,
    ) -> DownloadResult:
        part.parent.mkdir(parents=True, exist_ok=True)
        resume_from = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else None
        with session.get(  # type: ignore[attr-defined]
            request.url,
            stream=True,
            timeout=self.timeout,
            allow_redirects=True,
            headers=headers,
        ) as response:
            status = int(getattr(response, "status_code", 200))
            if status in (401, 403):
                raise _CredentialRejected()
            if status == 429 or status >= 500:
                raise _TransientError(f"HTTP {status} from data pool")
            if status == 416:
                raise _IntegrityMismatch("server rejected resume range (HTTP 416)")
            if status >= 400:
                raise _FatalTransport(f"HTTP {status} from data pool")
            if status == 206 and resume_from > 0:
                written = resume_from
                mode = "ab"
                total = _content_range_total(response)
            else:
                written = 0
                mode = "wb"
                total = _content_length(response)
            expected = request.expected_size if request.expected_size is not None else total
            with part.open(mode) as handle:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._cancelled():
                        raise _Cancelled()
                    self._wait_if_paused()
                    if chunk:
                        handle.write(chunk)
                        written += len(chunk)
                        if self.progress_callback is not None:
                            self.progress_callback(request.scene_id, written, expected)

        if expected is not None and written != expected:
            raise _IntegrityMismatch(f"expected {expected} bytes but received {written}")

        os.replace(part, dest)
        logger.info("downloaded %s (%d bytes)", request.scene_id, written)
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=DownloadOutcome.SUCCESS,
            path=dest,
            bytes_written=written,
            message="downloaded",
        )

    def _interrupted(self, request: DownloadRequest) -> DownloadResult:
        part = request.destination.with_name(request.destination.name + ".part")
        bytes_written = part.stat().st_size if part.exists() else 0
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=DownloadOutcome.INTERRUPTED,
            bytes_written=bytes_written,
            message="cancelled by user; partial .part kept for resume",
            error_code=ErrorCode.DL001.value,
        )

    def verify(self, request: DownloadRequest) -> DownloadResult:
        """Network preflight for one scene without saving the full archive.

        Sends a small ``Range`` request and confirms the whole chain works:
        credential resolution -> EDL authentication -> ASF data pool reachable ->
        the signed redirect is followed and still returns data. Nothing is written
        to disk. Returns a :class:`DownloadResult` with outcome
        :attr:`DownloadOutcome.VERIFIED` on success (or ``FAILED``); never raises.
        """
        if not request.url:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message="no download URL for scene",
                error_code=ErrorCode.ASF003.value,
            )
        try:
            session = self._ensure_session()
        except CredentialError as exc:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message=mask_text(str(exc)),
                error_code=ErrorCode.DL004.value,
            )

        headers = {"Range": f"bytes=0-{self.verify_bytes - 1}"}
        try:
            with session.get(  # type: ignore[attr-defined]
                request.url,
                stream=True,
                timeout=self.timeout,
                allow_redirects=True,
                headers=headers,
            ) as response:
                status = int(getattr(response, "status_code", 200))
                if status in (401, 403):
                    return DownloadResult(
                        scene_id=request.scene_id,
                        outcome=DownloadOutcome.FAILED,
                        message="Earthdata credentials were rejected (HTTP 401/403)",
                        error_code=ErrorCode.DL004.value,
                    )
                # 416 (range not satisfiable) still proves the chain is reachable
                # and authenticated; anything else >=400 is a real failure.
                if status >= 400 and status != 416:
                    return DownloadResult(
                        scene_id=request.scene_id,
                        outcome=DownloadOutcome.FAILED,
                        message=f"HTTP {status} from data pool",
                        error_code=ErrorCode.DL005.value,
                    )
                sample = 0
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        sample += len(chunk)
                    if sample >= self.verify_bytes:
                        break
                total = _content_range_total(response)
                if total is None and status != 206:
                    total = _content_length(response)
        except Exception as exc:  # noqa: BLE001 - transport errors are masked, not raised
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.FAILED,
                message=mask_text(f"{type(exc).__name__}: {exc}"),
                error_code=ErrorCode.DL005.value,
            )

        note = "reachable and authenticated"
        if total is not None:
            note += f"; remote size {total} bytes"
            if request.expected_size is not None and total != request.expected_size:
                note += f" (plan expected {request.expected_size})"
        logger.info("verified %s: %s", request.scene_id, note)
        return DownloadResult(
            scene_id=request.scene_id,
            outcome=DownloadOutcome.VERIFIED,
            bytes_written=sample,
            message=note,
        )


_EDL_PROFILE_URL = "https://urs.earthdata.nasa.gov/profile"


def probe_earthdata_auth(
    resolved: ResolvedCredential,
    *,
    session: object | None = None,
    url: str = _EDL_PROFILE_URL,
    timeout: float = 30.0,
) -> tuple[bool, str]:
    """Best-effort authenticated reachability check. Returns ``(ok, masked_message)``.

    Performs a single authenticated request to Earthdata; any error is masked. Used
    by ``insar-prep auth status --test`` (opt-in, network).
    """
    try:
        sess = session or build_earthdata_session(resolved)
        with sess.get(url, timeout=timeout, allow_redirects=True) as response:  # type: ignore[attr-defined]
            status = int(getattr(response, "status_code", 0))
    except Exception as exc:  # noqa: BLE001 - any transport error is reported, masked
        return False, mask_text(f"{type(exc).__name__}: {exc}")
    if status in (401, 403):
        return False, f"HTTP {status}: credentials rejected"
    if status >= 400:
        return False, f"HTTP {status}"
    return True, f"HTTP {status}: reachable"


def download_requests_from_scenes(
    scenes: Iterable[object],
    *,
    slc_dir: Path,
) -> list[DownloadRequest]:
    """Build :class:`DownloadRequest` objects for scenes that have a URL.

    The destination mirrors the dry-run planner's product-aware layout:
    SLC -> ``02_slc``, GRD -> ``02_grd``, RAW -> ``02_raw`` and OCN -> ``02_ocn``.
    Scenes without a URL are skipped (they cannot be fetched).
    """
    requests_out: list[DownloadRequest] = []
    for scene in scenes:
        url = getattr(scene, "url", None)
        scene_id = getattr(scene, "scene_id", "")
        if not url:
            continue
        expected_filename = f"{scene_id}.zip"
        product = str(getattr(getattr(scene, "product_type", ""), "value", "") or "").lower()
        destination_dir = slc_dir
        if product and product != "slc":
            destination_dir = slc_dir.parent / f"02_{product}"
        requests_out.append(
            DownloadRequest(
                scene_id=scene_id,
                expected_filename=expected_filename,
                destination=destination_dir / expected_filename,
                url=url,
                expected_size=getattr(scene, "file_size_remote", None),
            )
        )
    return requests_out
