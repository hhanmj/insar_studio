"""Tests for logging, structured events, and secret masking (Task 004)."""

from __future__ import annotations

import json
import logging
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from insar_prep.core.events import EventType
from insar_prep.core.logging import (
    configure_region_logging,
    get_logger,
    log_event,
    mask_secret,
    mask_text,
)


@pytest.fixture(autouse=True)
def _cleanup_logging() -> Iterator[None]:
    yield
    for logger_name in list(logging.root.manager.loggerDict):
        if logger_name.startswith("insar_prep"):
            logger = logging.getLogger(logger_name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_region_logging_creates_four_files(tmp_path: Path) -> None:
    configure_region_logging(tmp_path, name="t_files")
    for filename in ("app.log", "task.log", "events.jsonl", "errors.log"):
        assert (tmp_path / filename).exists()


def test_errors_log_only_contains_errors(tmp_path: Path) -> None:
    logger = configure_region_logging(tmp_path, name="t_errors")
    logger.info("an informational message")
    logger.error("a failure happened")
    errors = _read(tmp_path / "errors.log")
    assert "a failure happened" in errors
    assert "an informational message" not in errors
    assert "an informational message" in _read(tmp_path / "app.log")


def test_events_jsonl_is_valid_jsonl(tmp_path: Path) -> None:
    logger = configure_region_logging(tmp_path, name="t_events")
    log_event(
        logger,
        EventType.ASF_CART_IMPORTED,
        "Imported scenes",
        region_id="region_guangdong",
        module="asf",
        payload={"scene_count": 32},
    )
    log_event(logger, EventType.REPORT_GENERATED, "Report ready")
    lines = [ln for ln in _read(tmp_path / "events.jsonl").splitlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert "event_type" in record
        assert record["timestamp"].endswith("Z")


def test_masking_hides_full_token(tmp_path: Path) -> None:
    logger = configure_region_logging(tmp_path, name="t_mask")
    logger.info("Earthdata token=abcdef123456 loaded")
    log_event(logger, EventType.APP_STARTED, "startup", payload={"api_key": "abcdef123456"})
    app = _read(tmp_path / "app.log")
    events = _read(tmp_path / "events.jsonl")
    assert "abcdef123456" not in app
    assert "abcdef123456" not in events
    assert "****3456" in app


def test_mask_helpers() -> None:
    assert mask_secret("abcdef123456") == "****3456"
    assert mask_secret("ab") == "****"
    assert "secret123456" not in mask_text("password: secret123456")


def test_get_logger_namespace() -> None:
    assert get_logger("foo").name == "insar_prep.foo"


def test_ruff_t20_enabled() -> None:
    root = Path(__file__).resolve().parents[2]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "T20" in data["tool"]["ruff"]["lint"]["select"]
