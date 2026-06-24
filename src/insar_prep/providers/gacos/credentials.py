"""GACOS email resolution for the real GACOS request/download client (Task 054).

GACOS has **no API key**: a request is a web-form submission that is tied to the
email address GACOS delivers the result link to. This module resolves *where*
that email address comes from, without ever performing network I/O. The email is
not a password, but it is personal data, so it is kept out of logs/reports
(masked) and out of the resolved value's ``repr``.

Supported sources (mirroring ``providers/dem/credentials.py`` so the model is
identical across providers):

- ``keyring``: the email stored in the OS secret store via the optional
  ``keyring`` dependency (the friendly, GUI-/CLI-configurable source).
- ``env``: the email in the ``GACOS_EMAIL`` environment variable.
- ``auto``: try keyring, then env (the default).

Unlike a token, an email *may* also be supplied directly (e.g. a CLI ``--email``
flag), because it is not a secret; :func:`resolve_gacos_email` is for the stored
sources only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger

if TYPE_CHECKING:
    from types import ModuleType

logger = get_logger("providers.gacos.credentials")

GACOS_EMAIL_ENV = "GACOS_EMAIL"

# GACOS account / submission onboarding URLs (verified 2026-06-24).
GACOS_PORTAL_URL = "http://www.gacos.net/"
GACOS_README_URL = "http://www.gacos.net/static/file/ReadMe.pdf"

# OS keyring storage layout. The email is not a secret, but storing it in the OS
# vault keeps it out of project files and shell history.
KEYRING_SERVICE = "insar-prep:gacos"
_KR_EMAIL = "email"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GacosEmailSource(StrEnum):
    """Where the real GACOS client should obtain the delivery email."""

    AUTO = "auto"
    KEYRING = "keyring"
    ENV = "env"


def mask_email(email: str) -> str:
    """Return a privacy-masked email such as ``a***@example.com``.

    Keeps the first character of the local part and the full domain so the user
    can recognize which address is configured without exposing the whole local
    part in logs, reports, or the UI.
    """
    email = email.strip()
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def is_valid_email(email: str) -> bool:
    """Return True if ``email`` looks like a plausible address (offline check)."""
    return bool(_EMAIL_RE.match(email.strip()))


@dataclass(frozen=True)
class ResolvedGacosEmail:
    """An in-memory, non-persisted GACOS email resolution result.

    The full email is intentionally excluded from ``repr`` (only a masked form is
    shown) so it never reaches a log, report, or traceback verbatim.
    """

    source: GacosEmailSource
    email: str

    def __repr__(self) -> str:
        return f"ResolvedGacosEmail(source={self.source.value}, email={mask_email(self.email)})"


def get_keyring(keyring_module: ModuleType | None = None) -> ModuleType:
    """Return the ``keyring`` module (lazy import; part of the ``download`` extra)."""
    if keyring_module is not None:
        return keyring_module
    try:
        import keyring  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:
        raise CredentialError(
            "storing the GACOS email needs the optional 'download' extra (keyring); "
            "install it with 'uv sync --extra download'",
            code=ErrorCode.GAC003,
        ) from exc
    return keyring


def store_gacos_email(email: str, *, keyring_module: ModuleType | None = None) -> None:
    """Store the GACOS delivery email in the OS keyring."""
    email = email.strip()
    if not email:
        raise CredentialError("refusing to store an empty email", code=ErrorCode.GAC003)
    if not is_valid_email(email):
        raise CredentialError(
            f"{email!r} does not look like an email address", code=ErrorCode.GAC003
        )
    kr = get_keyring(keyring_module)
    kr.set_password(KEYRING_SERVICE, _KR_EMAIL, email)
    logger.info("stored GACOS email in the OS keyring (%s)", mask_email(email))


def clear_stored_gacos_email(*, keyring_module: ModuleType | None = None) -> bool:
    """Remove any stored GACOS email from the keyring. Returns True if one existed."""
    kr = get_keyring(keyring_module)
    return _safe_delete(kr, _KR_EMAIL)


def stored_gacos_email_status(*, keyring_module: ModuleType | None = None) -> str:
    """Return a privacy-safe status: a masked email, or ``none``."""
    kr = get_keyring(keyring_module)
    email = kr.get_password(KEYRING_SERVICE, _KR_EMAIL)
    return mask_email(email) if email else "none"


def _safe_delete(kr: ModuleType, key: str) -> bool:
    try:
        if kr.get_password(KEYRING_SERVICE, key) is None:
            return False
        kr.delete_password(KEYRING_SERVICE, key)
        return True
    except Exception:  # noqa: BLE001 - best-effort cleanup; backend errors are non-fatal
        logger.debug("could not delete keyring entry %s", key)
        return False


def _resolve_keyring(keyring_module: ModuleType | None = None) -> ResolvedGacosEmail:
    kr = get_keyring(keyring_module)
    email = kr.get_password(KEYRING_SERVICE, _KR_EMAIL)
    if email:
        logger.debug("resolved GACOS email from the OS keyring")
        return ResolvedGacosEmail(source=GacosEmailSource.KEYRING, email=email)
    raise CredentialError(
        "no GACOS email stored; run 'insar-prep gacos-auth login', pass --email, or "
        "use the GUI 'GACOS Email' dialog",
        code=ErrorCode.GAC003,
    )


def _resolve_env(env: dict[str, str]) -> ResolvedGacosEmail:
    email = (env.get(GACOS_EMAIL_ENV) or "").strip()
    if not email:
        raise CredentialError(
            f"{GACOS_EMAIL_ENV} is not set; export your GACOS email, store one with "
            "'insar-prep gacos-auth login', or pass --email",
            code=ErrorCode.GAC003,
        )
    logger.debug("resolved GACOS email from %s", GACOS_EMAIL_ENV)
    return ResolvedGacosEmail(source=GacosEmailSource.ENV, email=email)


def resolve_gacos_email(
    source: GacosEmailSource = GacosEmailSource.AUTO,
    *,
    environ: dict[str, str] | None = None,
    keyring_module: ModuleType | None = None,
) -> ResolvedGacosEmail:
    """Resolve the GACOS delivery email for ``source`` without any network I/O.

    Raises :class:`CredentialError` (``GAC003``) with an actionable message when
    the requested source is not configured.
    """
    env = os.environ if environ is None else environ

    if source is GacosEmailSource.KEYRING:
        return _resolve_keyring(keyring_module)
    if source is GacosEmailSource.ENV:
        return _resolve_env(env)

    for attempt in (
        lambda: _resolve_keyring(keyring_module),
        lambda: _resolve_env(env),
    ):
        try:
            return attempt()
        except CredentialError:
            continue
    raise CredentialError(
        "no GACOS email found; store one with 'insar-prep gacos-auth login' (or the "
        f"GUI dialog), set {GACOS_EMAIL_ENV}, or pass --email",
        code=ErrorCode.GAC003,
    )
