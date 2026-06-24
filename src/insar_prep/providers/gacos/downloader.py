"""Real GACOS request submission and result download (Task 054).

GACOS has **no public download API**: a product is obtained in two real steps,
and this module automates both as far as the service allows:

1. **Submit** a request to the GACOS web form
   (``POST http://www.gacos.net/M/action_page.php`` with the bounding box, a date
   list, the time of day, an output format, and the delivery email). GACOS queues
   the job and emails the requester a download link when it is ready.
2. **Fetch** the emailed result archive (an HTTP/FTP link) to disk, so it can be
   organized and integrity-checked by :mod:`insar_prep.providers.gacos.importer`.

Because delivery is by email, the link cannot be predicted; the user pastes the
link they receive into :meth:`GacosClient.fetch` (the ``gacos-download`` command
or the GUI panel). This is the maximum automation possible without scraping a
mailbox, and it never drives a browser or stores a password.

The real client needs the optional ``download`` extra (``requests``), imported
lazily so the offline core never depends on it. A :class:`FakeGacosClient` makes
the submit/fetch orchestration fully offline-testable.
"""

from __future__ import annotations

import datetime
import os
import time
import urllib.request
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import Field

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import BBox, InsarBaseModel
from insar_prep.providers.gacos.credentials import (
    GacosEmailSource,
    ResolvedGacosEmail,
    mask_email,
    resolve_gacos_email,
)

if TYPE_CHECKING:
    from threading import Event

logger = get_logger("providers.gacos.downloader")

# GACOS web-form submission endpoint (the form's action, method POST). The form
# is application/x-www-form-urlencoded with fields N/S/W/E/H/M/date/type/email.
GACOS_BASE_URL = "http://www.gacos.net/"
GACOS_SUBMIT_ENDPOINT = "http://www.gacos.net/M/action_page.php"

# Service limits (per the GACOS website): at most 20 dates and a 10x10 degree
# box per submitted job.
GACOS_MAX_DATES_PER_REQUEST = 20
GACOS_MAX_SPAN_DEGREES = 10.0

_DEFAULT_CHUNK_SIZE = 1024 * 1024
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF = 2.0

# Markers that, if present in the form response body, indicate a rejected job.
_ERROR_MARKERS = ("error", "invalid", "exceed", "maximum", "not allowed", "failed")


class GacosOutputFormat(StrEnum):
    """GACOS output product format (maps to the form's ``type`` radio value)."""

    GEOTIFF = "geotiff"
    BINARY = "binary"


# The form posts ``type=2`` for GeoTIFF (the recommended default) and ``type=1``
# for the little-endian 4-byte-float binary grid.
_FORM_TYPE_VALUE: dict[GacosOutputFormat, str] = {
    GacosOutputFormat.GEOTIFF: "2",
    GacosOutputFormat.BINARY: "1",
}


class GacosSubmitOutcome(StrEnum):
    """Outcome of a single GACOS request submission."""

    SUBMITTED = "submitted"
    FAILED = "failed"


class GacosFetchOutcome(StrEnum):
    """Outcome of fetching a GACOS result archive from its emailed link."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class GacosRequest(InsarBaseModel):
    """One GACOS web-form submission (at most 20 dates, <=10x10 degrees).

    The ``email`` is the delivery address GACOS sends the result link to; it is
    not serialized into any report and is masked in logs.
    """

    region_safe_name: str = ""
    bbox: BBox
    dates: list[datetime.date] = Field(default_factory=list)
    hour: int = 0
    minute: int = 0
    output_format: GacosOutputFormat = GacosOutputFormat.GEOTIFF
    email: str


class GacosSubmitResult(InsarBaseModel):
    """The outcome of submitting one GACOS request batch."""

    region_safe_name: str = ""
    outcome: GacosSubmitOutcome
    date_count: int = 0
    batch_index: int = 1
    batch_count: int = 1
    message: str = ""
    error_code: str | None = None


class GacosFetchResult(InsarBaseModel):
    """The outcome of fetching one GACOS result archive."""

    region_safe_name: str = ""
    outcome: GacosFetchOutcome
    path: Path | None = None
    bytes_written: int = 0
    message: str = ""
    error_code: str | None = None


@runtime_checkable
class GacosClient(Protocol):
    """The interface a real or fake GACOS client must implement."""

    def submit(self, request: GacosRequest) -> GacosSubmitResult:
        """Submit (or simulate submitting) one GACOS request batch."""
        ...

    def fetch(self, url: str, destination: Path) -> GacosFetchResult:
        """Fetch (or simulate fetching) a result archive from its emailed link."""
        ...


class FakeGacosClient:
    """An offline, deterministic fake GACOS client for tests.

    Never opens a socket, reads an email, or contacts GACOS. ``submit_outcome`` /
    ``fetch_outcome`` control the simulated results; with
    ``write_placeholder=True`` :meth:`fetch` writes a tiny ``.zip`` marker so the
    importer step can run end to end offline.
    """

    def __init__(
        self,
        *,
        submit_outcome: GacosSubmitOutcome = GacosSubmitOutcome.SUBMITTED,
        fetch_outcome: GacosFetchOutcome = GacosFetchOutcome.SUCCESS,
        write_placeholder: bool = False,
    ) -> None:
        self.submit_outcome = submit_outcome
        self.fetch_outcome = fetch_outcome
        self.write_placeholder = write_placeholder
        self.submitted: list[GacosRequest] = []
        self.fetched: list[str] = []

    def submit(self, request: GacosRequest) -> GacosSubmitResult:
        self.submitted.append(request)
        if self.submit_outcome is GacosSubmitOutcome.FAILED:
            return GacosSubmitResult(
                region_safe_name=request.region_safe_name,
                outcome=GacosSubmitOutcome.FAILED,
                date_count=len(request.dates),
                message="simulated GACOS submission failure",
                error_code=ErrorCode.GAC003.value,
            )
        return GacosSubmitResult(
            region_safe_name=request.region_safe_name,
            outcome=GacosSubmitOutcome.SUBMITTED,
            date_count=len(request.dates),
            message="fake submission ok",
        )

    def fetch(self, url: str, destination: Path) -> GacosFetchResult:
        self.fetched.append(url)
        if self.fetch_outcome is GacosFetchOutcome.FAILED:
            return GacosFetchResult(
                outcome=GacosFetchOutcome.FAILED,
                message="simulated GACOS fetch failure",
                error_code=ErrorCode.GAC004.value,
            )
        if self.fetch_outcome is GacosFetchOutcome.INTERRUPTED:
            return GacosFetchResult(
                outcome=GacosFetchOutcome.INTERRUPTED,
                message="simulated interrupted fetch",
                error_code=ErrorCode.GAC004.value,
            )
        bytes_written = 0
        path: Path | None = None
        if self.fetch_outcome is GacosFetchOutcome.SUCCESS and self.write_placeholder:
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # empty-zip EOCD marker
            path = destination
            bytes_written = destination.stat().st_size
        message = "fake fetch ok" if self.fetch_outcome is GacosFetchOutcome.SUCCESS else "skipped"
        return GacosFetchResult(
            outcome=self.fetch_outcome,
            path=path,
            bytes_written=bytes_written,
            message=message,
        )


class _TransientError(Exception):
    """A retryable failure (timeout, connection reset, 429, 5xx)."""


class _FatalRequest(Exception):
    """A non-retryable request failure (e.g. HTTP 400 bad params)."""


class _Cancelled(Exception):
    """The caller requested cancellation mid-transfer."""


def build_gacos_session() -> object:
    """Build a plain ``requests`` session (lazy import; needs the ``download`` extra)."""
    try:
        import requests  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - exercised via CLI guard
        raise CredentialError(
            "real GACOS request/download needs the optional 'download' extra; install "
            "it with 'uv sync --extra download' (or pip install requests)",
            code=ErrorCode.GAC004,
        ) from exc
    return requests.Session()


def _strip_html(text: str, limit: int = 200) -> str:
    """Return a short, tag-free snippet of an HTML response for a status message."""
    import re  # noqa: PLC0415 - local, only needed here

    stripped = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped[:limit]


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Content-Length") or headers.get("content-length")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best-effort cleanup
        logger.debug("could not remove partial file %s", path)


class RealGacosClient:
    """Submit GACOS web-form requests and fetch the emailed result archives.

    Construction does no network I/O and reads no email: the delivery email is
    resolved lazily on the first :meth:`submit` (the keyring / ``GACOS_EMAIL``
    env, or a ``resolved`` value injected for tests). A ``session`` may be
    injected so the submit/fetch logic runs without ``requests`` or the network.
    """

    def __init__(
        self,
        *,
        email_source: GacosEmailSource = GacosEmailSource.AUTO,
        resolved: ResolvedGacosEmail | None = None,
        session: object | None = None,
        endpoint: str = GACOS_SUBMIT_ENDPOINT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_seconds: float = _DEFAULT_BACKOFF,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        timeout: float = _DEFAULT_TIMEOUT,
        cancel_event: Event | None = None,
    ) -> None:
        self.email_source = email_source
        self.endpoint = endpoint
        self.max_retries = max(1, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.chunk_size = max(1, chunk_size)
        self.timeout = timeout
        self.cancel_event = cancel_event
        self._resolved = resolved
        self._session = session

    def _ensure_session(self) -> object:
        if self._session is None:
            self._session = build_gacos_session()
        return self._session

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def _form_data(self, request: GacosRequest, email: str) -> dict[str, str]:
        bbox = request.bbox
        date_list = "\n".join(d.strftime("%Y%m%d") for d in request.dates)
        return {
            "N": f"{bbox.north}",
            "S": f"{bbox.south}",
            "W": f"{bbox.west}",
            "E": f"{bbox.east}",
            "H": f"{request.hour}",
            "M": f"{request.minute}",
            "date": date_list,
            "type": _FORM_TYPE_VALUE[request.output_format],
            "email": email,
            "seq": "OSM Map",
        }

    def submit(self, request: GacosRequest) -> GacosSubmitResult:
        """Submit one GACOS request batch, returning a result (never raises)."""
        email = (request.email or "").strip()
        if not email:
            try:
                email = self._resolve_email().email
            except CredentialError as exc:
                return GacosSubmitResult(
                    region_safe_name=request.region_safe_name,
                    outcome=GacosSubmitOutcome.FAILED,
                    date_count=len(request.dates),
                    message=mask_text(str(exc)),
                    error_code=ErrorCode.GAC003.value,
                )
        if not request.dates:
            return GacosSubmitResult(
                region_safe_name=request.region_safe_name,
                outcome=GacosSubmitOutcome.FAILED,
                message="no dates to submit",
                error_code=ErrorCode.GAC003.value,
            )

        try:
            session = self._ensure_session()
        except CredentialError as exc:
            return GacosSubmitResult(
                region_safe_name=request.region_safe_name,
                outcome=GacosSubmitOutcome.FAILED,
                date_count=len(request.dates),
                message=mask_text(str(exc)),
                error_code=ErrorCode.GAC004.value,
            )

        data = self._form_data(request, email)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._attempt_submit(session, request, data, email)
            except _FatalRequest as exc:
                return GacosSubmitResult(
                    region_safe_name=request.region_safe_name,
                    outcome=GacosSubmitOutcome.FAILED,
                    date_count=len(request.dates),
                    message=mask_text(str(exc)),
                    error_code=ErrorCode.GAC003.value,
                )
            except Exception as exc:  # noqa: BLE001 - transport errors are masked + retried
                last_error = exc
            if attempt < self.max_retries:
                time.sleep(self.backoff_seconds * attempt)

        detail = mask_text(f"{type(last_error).__name__}: {last_error}") if last_error else ""
        return GacosSubmitResult(
            region_safe_name=request.region_safe_name,
            outcome=GacosSubmitOutcome.FAILED,
            date_count=len(request.dates),
            message=f"GACOS submission failed after {self.max_retries} attempts: {detail}".strip(),
            error_code=ErrorCode.GAC004.value,
        )

    def _attempt_submit(
        self, session: object, request: GacosRequest, data: dict[str, str], email: str
    ) -> GacosSubmitResult:
        with session.post(  # type: ignore[attr-defined]
            self.endpoint, data=data, timeout=self.timeout
        ) as response:
            status = int(getattr(response, "status_code", 200))
            if status == 429 or status >= 500:
                raise _TransientError(f"HTTP {status} from GACOS")
            if status >= 400:
                raise _FatalRequest(f"HTTP {status} from GACOS (check bbox/dates/email)")
            body = getattr(response, "text", "") or ""
            snippet = _strip_html(body)
            lowered = snippet.lower()
            if any(marker in lowered for marker in _ERROR_MARKERS):
                raise _FatalRequest(f"GACOS rejected the request: {snippet}")
        logger.info(
            "submitted GACOS request: %d date(s) to %s",
            len(request.dates),
            mask_email(email),
        )
        return GacosSubmitResult(
            region_safe_name=request.region_safe_name,
            outcome=GacosSubmitOutcome.SUBMITTED,
            date_count=len(request.dates),
            message=(
                "submitted; GACOS will email the download link to "
                f"{mask_email(email)} when the job is ready"
            ),
        )

    def _resolve_email(self) -> ResolvedGacosEmail:
        if self._resolved is None:
            self._resolved = resolve_gacos_email(self.email_source)
        return self._resolved

    def fetch(self, url: str, destination: Path) -> GacosFetchResult:
        """Fetch a GACOS result archive from ``url`` to ``destination`` (never raises)."""
        destination = Path(destination)
        if destination.exists() and destination.stat().st_size > 0:
            return GacosFetchResult(
                outcome=GacosFetchOutcome.SKIPPED,
                path=destination,
                bytes_written=destination.stat().st_size,
                message="already present; skipped",
            )

        scheme = urlsplit(url).scheme.lower()
        part = destination.with_name(destination.name + ".part")
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            if self._cancelled():
                return self._interrupted()
            try:
                if scheme in ("http", "https"):
                    return self._fetch_http(url, destination, part)
                if scheme == "ftp":
                    return self._fetch_ftp(url, destination, part)
                return GacosFetchResult(
                    outcome=GacosFetchOutcome.FAILED,
                    message=f"unsupported URL scheme {scheme!r}; expected http/https/ftp",
                    error_code=ErrorCode.GAC004.value,
                )
            except _Cancelled:
                return self._interrupted()
            except _FatalRequest as exc:
                _safe_unlink(part)
                return GacosFetchResult(
                    outcome=GacosFetchOutcome.FAILED,
                    message=mask_text(str(exc)),
                    error_code=ErrorCode.GAC004.value,
                )
            except Exception as exc:  # noqa: BLE001 - transport errors are masked + retried
                last_error = exc
                _safe_unlink(part)
            if attempt < self.max_retries and not self._cancelled():
                time.sleep(self.backoff_seconds * attempt)

        detail = mask_text(f"{type(last_error).__name__}: {last_error}") if last_error else ""
        return GacosFetchResult(
            outcome=GacosFetchOutcome.FAILED,
            message=f"GACOS fetch failed after {self.max_retries} attempts: {detail}".strip(),
            error_code=ErrorCode.GAC004.value,
        )

    def _fetch_http(self, url: str, destination: Path, part: Path) -> GacosFetchResult:
        session = self._ensure_session()
        part.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with session.get(url, stream=True, timeout=self.timeout) as response:  # type: ignore[attr-defined]
            status = int(getattr(response, "status_code", 200))
            if status == 429 or status >= 500:
                raise _TransientError(f"HTTP {status} from GACOS")
            if status >= 400:
                raise _FatalRequest(f"HTTP {status} fetching the GACOS archive")
            with part.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._cancelled():
                        raise _Cancelled()
                    if chunk:
                        handle.write(chunk)
                        written += len(chunk)
            total = _content_length(response)
        if written == 0:
            raise _TransientError("received an empty GACOS archive")
        if total is not None and written != total:
            raise _TransientError(f"expected {total} bytes but received {written}")
        os.replace(part, destination)
        logger.info("fetched GACOS archive (%d bytes) -> %s", written, destination.name)
        return GacosFetchResult(
            outcome=GacosFetchOutcome.SUCCESS,
            path=destination,
            bytes_written=written,
            message="fetched",
        )

    def _fetch_ftp(self, url: str, destination: Path, part: Path) -> GacosFetchResult:
        part.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with urllib.request.urlopen(url, timeout=self.timeout) as response:  # noqa: S310 - ftp/http only
            with part.open("wb") as handle:
                while True:
                    if self._cancelled():
                        raise _Cancelled()
                    chunk = response.read(self.chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
        if written == 0:
            raise _TransientError("received an empty GACOS archive")
        os.replace(part, destination)
        logger.info("fetched GACOS archive over FTP (%d bytes) -> %s", written, destination.name)
        return GacosFetchResult(
            outcome=GacosFetchOutcome.SUCCESS,
            path=destination,
            bytes_written=written,
            message="fetched",
        )

    def _interrupted(self) -> GacosFetchResult:
        return GacosFetchResult(
            outcome=GacosFetchOutcome.INTERRUPTED,
            message="cancelled by user; partial .part kept",
            error_code=ErrorCode.GAC004.value,
        )
