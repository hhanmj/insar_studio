"""Application-specific exceptions (manual section 18.1).

Every user-visible error carries an :class:`~insar_prep.core.error_codes.ErrorCode`.
``str(error)`` renders as ``[CODE] message``. Each concrete exception defines a
default code, which a caller may override by passing ``code=...``.
"""

from __future__ import annotations

from insar_prep.core.error_codes import ERROR_CODE_MESSAGES, ErrorCode


class InsarPrepError(Exception):
    """Base class for all application-specific errors."""

    default_code: ErrorCode | None = None

    def __init__(self, message: str | None = None, *, code: ErrorCode | None = None) -> None:
        resolved = code or self.default_code
        if resolved is None:
            raise ValueError("InsarPrepError requires an error code")
        self.code: ErrorCode = resolved
        self.message: str = message or ERROR_CODE_MESSAGES.get(resolved, "")
        super().__init__(f"[{resolved}] {self.message}")

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigError(InsarPrepError):
    """Invalid or missing configuration."""

    default_code = ErrorCode.CFG001


class CredentialError(InsarPrepError):
    """Credential is missing, invalid, or cannot be accessed."""

    default_code = ErrorCode.AUTH001


class ProviderError(InsarPrepError):
    """External provider returned an error."""

    default_code = ErrorCode.ASF002


class DownloadError(InsarPrepError):
    """Download failed or file is incomplete."""

    default_code = ErrorCode.DL001


class InputValidationError(InsarPrepError):
    """Input data failed validation (named to avoid clashing with pydantic)."""

    default_code = ErrorCode.AOI001


class DemProcessingError(InsarPrepError):
    """DEM clipping, reprojection, or vertical conversion failed."""

    default_code = ErrorCode.DEM003


class OrbitMatchingError(InsarPrepError):
    """No suitable orbit file can be matched."""

    default_code = ErrorCode.ORB001


class AtmosphereProductError(InsarPrepError):
    """Atmospheric product is missing, invalid, or unmatched."""

    default_code = ErrorCode.GAC002


class ReportError(InsarPrepError):
    """Report generation failed."""

    default_code = ErrorCode.REP001
