"""Tests for application-specific exceptions (Task 004)."""

from __future__ import annotations

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import (
    AtmosphereProductError,
    ConfigError,
    CredentialError,
    DemProcessingError,
    DownloadError,
    InputValidationError,
    InsarPrepError,
    OrbitMatchingError,
    ProviderError,
    ReportError,
)

ALL_SUBCLASSES = [
    ConfigError,
    CredentialError,
    ProviderError,
    DownloadError,
    InputValidationError,
    DemProcessingError,
    OrbitMatchingError,
    AtmosphereProductError,
    ReportError,
]


def test_subclasses_inherit_base() -> None:
    for exc_type in ALL_SUBCLASSES:
        assert issubclass(exc_type, InsarPrepError)


def test_each_subclass_has_default_code() -> None:
    for exc_type in ALL_SUBCLASSES:
        error = exc_type()
        assert isinstance(error.code, ErrorCode)


def test_str_format_is_bracketed_code() -> None:
    error = ConfigError("boom")
    assert str(error) == "[CFG001] boom"


def test_default_message_used_when_omitted() -> None:
    error = ConfigError()
    assert str(error).startswith("[CFG001] ")
    assert error.message


def test_code_can_be_overridden() -> None:
    error = ConfigError("bad field", code=ErrorCode.CFG002)
    assert error.code is ErrorCode.CFG002
    assert str(error) == "[CFG002] bad field"


def test_report_error_uses_rep001() -> None:
    assert ReportError().code is ErrorCode.REP001


def test_base_requires_a_code() -> None:
    with pytest.raises(ValueError):
        InsarPrepError("no code provided")


def test_exceptions_are_raisable() -> None:
    with pytest.raises(InsarPrepError):
        raise DownloadError(code=ErrorCode.DL002)
