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

# Matches "<key><sep><value>" for common secret keys in plain, key=value, JSON
# "key":"value", and URL ?key=value / &key=value query forms. The value class
# includes +/= so base64 tokens and presigned-URL signatures are fully masked.
# Authorization / Bearer / Cookie are handled by dedicated patterns below so the
# header structure (scheme word) survives while the secret itself is masked. A
# leading \b plus a required [:=] separator means Windows paths such as
# C:\Users\...\token_cache\file.zip are never mis-redacted (no separator follows
# the keyword), and only the credential -- not the key -- is rewritten.
_SECRET_KEY_RE = re.compile(
    r"(?i)\b("
    r"access[_-]?token|refresh[_-]?token|id[_-]?token|api[_-]?key|apikey|"
    r"api[_-]?token|token|password|passwd|pwd|secret|sessionid|session|"
    r"credentials?|x-amz-security-token|x-amz-signature|x-amz-credential|"
    r"signature|awsaccesskeyid"
    r")(\"?\s*[:=]\s*\"?)([A-Za-z0-9._+/=\-]+)"
)

# "Authorization: <scheme> <token>" or "Authorization: <token>". The scheme word
# (Bearer/Basic/Token/Negotiate) is preserved; the credential after it is masked.
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+|basic\s+|token\s+|negotiate\s+)?"
    r"([A-Za-z0-9._+/=\-]{2,})"
)

# A bare "Bearer <token>" anywhere (e.g. not preceded by an Authorization key).
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._+/=\-]{2,})")

# A Cookie header: mask the entire cookie payload through the end of the line.
_COOKIE_RE = re.compile(r"(?i)\b(cookie\s*[:=]\s*)([^\r\n]+)")


def mask_secret(value: str) -> str:
    """Mask a secret value, keeping only the last four characters."""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


def mask_text(text: str) -> str:
    """Redact credential-like substrings in arbitrary text.

    Covers ``key<sep>value`` secrets (token/password/api_key/secret/session/
    signature/presigned-URL params, in plain, ``key=value``, JSON, and URL-query
    forms), ``Authorization`` headers (with or without a Bearer/Basic scheme),
    bare ``Bearer`` tokens, and ``Cookie`` headers. Only the credential is
    masked; surrounding text -- keys, scheme words, and Windows paths -- is
    preserved.
    """

    def _mask_keyed(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{mask_secret(match.group(3))}"

    def _mask_auth(match: re.Match[str]) -> str:
        scheme = match.group(2) or ""
        return f"{match.group(1)}{scheme}{mask_secret(match.group(3))}"

    def _mask_value2(match: re.Match[str]) -> str:
        return f"{match.group(1)}{mask_secret(match.group(2))}"

    masked = _AUTH_HEADER_RE.sub(_mask_auth, text)
    masked = _BEARER_RE.sub(_mask_value2, masked)
    masked = _COOKIE_RE.sub(_mask_value2, masked)
    return _SECRET_KEY_RE.sub(_mask_keyed, masked)


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
