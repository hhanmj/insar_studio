"""Tests for error codes (Task 004)."""

from __future__ import annotations

from insar_prep.core.error_codes import ERROR_CODE_MESSAGES, ErrorCode


def test_expected_codes_present() -> None:
    expected = {
        "CFG001",
        "CFG002",
        "AUTH001",
        "AUTH002",
        "ASF001",
        "ASF002",
        "ASF003",
        "AOI001",
        "AOI002",
        "AOI003",
        "DL001",
        "DL002",
        "DL003",
        "ORB001",
        "DEM001",
        "DEM002",
        "DEM003",
        "DEM004",
        "GAC001",
        "GAC002",
        "REP001",
        "GUI001",
        "GUI002",
        "GUI003",
    }
    assert {code.value for code in ErrorCode} == expected


def test_error_codes_are_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))


def test_every_code_has_a_message() -> None:
    assert set(ERROR_CODE_MESSAGES.keys()) == set(ErrorCode)
    for message in ERROR_CODE_MESSAGES.values():
        assert isinstance(message, str)
        assert message
