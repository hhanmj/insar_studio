"""Project logging: file loggers, structured events, and secret masking.

Provides per-region and global file logging that writes ``app.log``,
``task.log``, ``events.jsonl``, and ``errors.log`` (all UTF-8), with a masking
filter that redacts credentials. No log rotation, no rich console output, no
``print()`` usage. Application code must log through these helpers.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from insar_prep.core.events import Event, EventType

_HUMAN_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"

# Matches "<key><sep><value>" for common secret keys (token, password, api_key,
# cookie, authorization, ...) in plain, key=value, and JSON "key":"value" forms.
_SECRET_KEY_RE = re.compile(
    r"(?i)(token|password|passwd|pwd|secret|api[_-]?key|apikey|cookie|authorization)"
    r"(\"?\s*[:=]\s*\"?)"
    r"([A-Za-z0-9._\-]+)"
)


def mask_secret(value: str) -> str:
    """Mask a secret value, keeping only the last four characters."""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


def mask_text(text: str) -> str:
    """Redact credential-like substrings (token/password/api_key/...) in text."""

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{mask_secret(match.group(3))}"

    return _SECRET_KEY_RE.sub(_replace, text)


class _MaskingFilter(logging.Filter):
    """Logging filter that masks credentials in the fully rendered message."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_text(record.getMessage())
        record.args = ()
        return True


_RAW_FORMATTER = logging.Formatter("%(message)s")


def _human_formatter() -> logging.Formatter:
    formatter = logging.Formatter(_HUMAN_FORMAT, datefmt=_DATEFMT)
    formatter.converter = time.gmtime
    return formatter


def _file_handler(path: Path, level: int, *, raw: bool = False) -> logging.FileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(_RAW_FORMATTER if raw else _human_formatter())
    handler.addFilter(_MaskingFilter())
    return handler


def _reset(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def get_logger(name: str) -> logging.Logger:
    """Return a project logger under the ``insar_prep`` namespace."""
    return logging.getLogger(f"insar_prep.{name}")


def _setup_file_loggers(log_dir: str | Path, name: str) -> logging.Logger:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    base = get_logger(name)
    base.setLevel(logging.DEBUG)
    base.propagate = False
    _reset(base)
    base.addHandler(_file_handler(directory / "app.log", logging.INFO))
    base.addHandler(_file_handler(directory / "errors.log", logging.ERROR))

    task = base.getChild("task")
    task.setLevel(logging.DEBUG)
    task.propagate = True
    _reset(task)
    task.addHandler(_file_handler(directory / "task.log", logging.INFO))

    events = base.getChild("events")
    events.setLevel(logging.DEBUG)
    events.propagate = False
    _reset(events)
    events.addHandler(_file_handler(directory / "events.jsonl", logging.DEBUG, raw=True))

    return base


def configure_region_logging(log_dir: str | Path, *, name: str = "region") -> logging.Logger:
    """Configure per-region loggers writing app/task/events/errors files."""
    return _setup_file_loggers(log_dir, name)


def configure_global_logging(log_dir: str | Path, *, name: str = "global") -> logging.Logger:
    """Configure global loggers writing app/task/events/errors files."""
    return _setup_file_loggers(log_dir, name)


def _to_level_number(level: int | str) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, level.upper(), logging.INFO)


def log_event(
    logger: logging.Logger,
    event_type: EventType,
    message: str,
    *,
    level: int | str = "INFO",
    module: str = "",
    workspace_id: str | None = None,
    project_id: str | None = None,
    region_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Build an :class:`Event` and write it as one JSON line to events.jsonl."""
    level_name = level if isinstance(level, str) else logging.getLevelName(level)
    event = Event(
        event_type=event_type,
        message=message,
        level=str(level_name),
        module=module,
        workspace_id=workspace_id,
        project_id=project_id,
        region_id=region_id,
        payload=payload or {},
    )
    logger.getChild("events").log(_to_level_number(level), event.to_json())
    return event
