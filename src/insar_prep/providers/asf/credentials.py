"""Earthdata credential resolution for the real ASF downloader.

Resolves *where* NASA Earthdata Login (EDL) credentials come from, without ever
performing network I/O and without persisting or logging any secret. Supported
sources (see ``docs/asf_download_credential_design.md`` section 4):

- ``keyring``: a token (or username/password) stored in the OS secret store
  (Windows Credential Manager / macOS Keychain / Linux Secret Service) via the
  optional ``keyring`` dependency. This is the friendly, GUI-/CLI-configurable
  source and the design's preferred one -- secrets live in the OS vault, never in
  a project file.
- ``env-token``: a bearer token in the ``EARTHDATA_TOKEN`` environment variable.
- ``netrc``: a standard ``machine urs.earthdata.nasa.gov`` entry in the user's
  ``~/.netrc`` (or ``~/_netrc`` on Windows), read by the HTTP client at the auth
  boundary -- this module only *verifies the entry exists* and never copies the
  login/password into the application.
- ``auto``: try keyring, then env-token, then netrc (the default).

A password is **never** accepted from the command line (threat T5). The resolved
value is held in memory only; :class:`ResolvedCredential` deliberately keeps the
token/password out of its ``repr`` so they cannot leak into a log or traceback.
"""

from __future__ import annotations

import netrc
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger

if TYPE_CHECKING:
    from types import ModuleType

logger = get_logger("providers.asf.credentials")

EARTHDATA_TOKEN_ENV = "EARTHDATA_TOKEN"
EDL_HOST = "urs.earthdata.nasa.gov"

# Where the user generates a personal EDL bearer token (opened by the GUI button).
EARTHDATA_TOKEN_URL = "https://urs.earthdata.nasa.gov/profile"
EARTHDATA_REGISTER_URL = "https://urs.earthdata.nasa.gov/users/new"

# OS keyring storage layout (service + fixed entry names). No secret is part of
# these identifiers; the secret values live only in the OS vault.
KEYRING_SERVICE = "insar-prep:earthdata"
_KR_TOKEN = "token"
_KR_USERNAME = "username"
_KR_PASSWORD = "password"


class CredentialSource(StrEnum):
    """Where the real downloader should obtain Earthdata credentials."""

    AUTO = "auto"
    KEYRING = "keyring"
    NETRC = "netrc"
    ENV_TOKEN = "env-token"


@dataclass(frozen=True)
class ResolvedCredential:
    """An in-memory, non-persisted credential resolution result.

    Holds a bearer ``token``, a ``username``/``password`` pair, or a ``use_netrc``
    flag (the HTTP client reads ``~/.netrc`` itself). Secrets are intentionally
    excluded from ``repr`` so they never reach a log, report, or traceback.
    """

    source: CredentialSource
    token: str | None = None
    username: str | None = None
    password: str | None = None
    use_netrc: bool = False

    def __repr__(self) -> str:
        if self.token:
            kind = "token"
        elif self.username and self.password:
            kind = "login"
        elif self.use_netrc:
            kind = "netrc"
        else:
            kind = "none"
        return f"ResolvedCredential(source={self.source.value}, kind={kind})"


def _default_netrc_paths() -> list[Path]:
    """Return the candidate netrc paths in the user's home (cross-platform)."""
    home = Path.home()
    return [home / ".netrc", home / "_netrc"]


def _verify_netrc(netrc_path: Path | None) -> None:
    """Verify a usable ``urs.earthdata.nasa.gov`` netrc entry exists.

    Never returns or logs the login/password; only confirms the entry is present
    so the user gets an actionable error *before* any network attempt.
    """
    candidates = [netrc_path] if netrc_path is not None else _default_netrc_paths()
    existing = [path for path in candidates if path is not None and path.exists()]
    if not existing:
        raise CredentialError(
            "no .netrc found; create one with a 'machine urs.earthdata.nasa.gov' "
            "entry outside the project directory, or use --credential-source env-token",
            code=ErrorCode.DL004,
        )
    for path in existing:
        try:
            parsed = netrc.netrc(str(path))
        except (netrc.NetrcParseError, OSError) as exc:
            # Do not echo file contents; only the (non-secret) path and reason.
            raise CredentialError(
                f"could not read netrc at {path}: {exc}", code=ErrorCode.DL004
            ) from exc
        if parsed.authenticators(EDL_HOST) is not None:
            logger.debug("found netrc entry for %s in %s", EDL_HOST, path)
            return
    raise CredentialError(
        f"no 'machine {EDL_HOST}' entry found in netrc; add one to enable real download",
        code=ErrorCode.DL004,
    )


def get_keyring(keyring_module: ModuleType | None = None) -> ModuleType:
    """Return the ``keyring`` module (lazy import; part of the ``download`` extra)."""
    if keyring_module is not None:
        return keyring_module
    try:
        import keyring  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:
        raise CredentialError(
            "storing credentials needs the optional 'download' extra (keyring); "
            "install it with 'uv sync --extra download'",
            code=ErrorCode.DL004,
        ) from exc
    return keyring


def store_token(token: str, *, keyring_module: ModuleType | None = None) -> None:
    """Store an Earthdata bearer token in the OS keyring (clears any stored login)."""
    token = token.strip()
    if not token:
        raise CredentialError("refusing to store an empty token", code=ErrorCode.DL004)
    kr = get_keyring(keyring_module)
    kr.set_password(KEYRING_SERVICE, _KR_TOKEN, token)
    _safe_delete(kr, _KR_USERNAME)
    _safe_delete(kr, _KR_PASSWORD)
    logger.info("stored Earthdata token in the OS keyring")


def store_login(username: str, password: str, *, keyring_module: ModuleType | None = None) -> None:
    """Store an Earthdata username/password in the OS keyring (clears any token)."""
    username = username.strip()
    if not username or not password:
        raise CredentialError("username and password are both required", code=ErrorCode.DL004)
    kr = get_keyring(keyring_module)
    kr.set_password(KEYRING_SERVICE, _KR_USERNAME, username)
    kr.set_password(KEYRING_SERVICE, _KR_PASSWORD, password)
    _safe_delete(kr, _KR_TOKEN)
    logger.info("stored Earthdata username/password in the OS keyring")


def clear_stored_credentials(*, keyring_module: ModuleType | None = None) -> bool:
    """Remove any stored Earthdata credentials from the keyring. Returns True if any existed."""
    kr = get_keyring(keyring_module)
    removed = [_safe_delete(kr, key) for key in (_KR_TOKEN, _KR_USERNAME, _KR_PASSWORD)]
    return any(removed)


def mask_username(username: str) -> str:
    """Return a privacy-masked username (first character + ``***``).

    The username is not a secret, but it is personal data, so the GUI/CLI status
    line shows only enough to recognize which account is configured (e.g.
    ``h***``) instead of the full login.
    """
    username = (username or "").strip()
    if len(username) <= 1:
        return "***"
    return f"{username[0]}***"


def stored_credential_status(*, keyring_module: ModuleType | None = None) -> str:
    """Return a privacy-safe status: ``token``, ``login:<masked>``, or ``none``.

    A stored username is masked (``login:h***``) so the full login is never shown
    on screen, in a log, or in a report.
    """
    kr = get_keyring(keyring_module)
    if kr.get_password(KEYRING_SERVICE, _KR_TOKEN):
        return "token"
    username = kr.get_password(KEYRING_SERVICE, _KR_USERNAME)
    if username and kr.get_password(KEYRING_SERVICE, _KR_PASSWORD):
        return f"login:{mask_username(username)}"
    return "none"


def _safe_delete(kr: ModuleType, key: str) -> bool:
    try:
        if kr.get_password(KEYRING_SERVICE, key) is None:
            return False
        kr.delete_password(KEYRING_SERVICE, key)
        return True
    except Exception:  # noqa: BLE001 - best-effort cleanup; backend errors are non-fatal
        logger.debug("could not delete keyring entry %s", key)
        return False


def _resolve_keyring(keyring_module: ModuleType | None = None) -> ResolvedCredential:
    kr = get_keyring(keyring_module)
    token = kr.get_password(KEYRING_SERVICE, _KR_TOKEN)
    if token:
        logger.debug("resolved Earthdata credential from the OS keyring (token)")
        return ResolvedCredential(source=CredentialSource.KEYRING, token=token)
    username = kr.get_password(KEYRING_SERVICE, _KR_USERNAME)
    password = kr.get_password(KEYRING_SERVICE, _KR_PASSWORD)
    if username and password:
        logger.debug("resolved Earthdata credential from the OS keyring (login)")
        return ResolvedCredential(
            source=CredentialSource.KEYRING, username=username, password=password
        )
    raise CredentialError(
        "no Earthdata credentials stored; run 'insar-prep auth login' or use the "
        "GUI 'Earthdata Login' dialog",
        code=ErrorCode.DL004,
    )


def _resolve_env_token(env: dict[str, str]) -> ResolvedCredential:
    token = (env.get(EARTHDATA_TOKEN_ENV) or "").strip()
    if not token:
        raise CredentialError(
            f"{EARTHDATA_TOKEN_ENV} is not set; export an Earthdata bearer token, "
            "store one with 'insar-prep auth login', or use --credential-source netrc",
            code=ErrorCode.DL004,
        )
    logger.debug("resolved Earthdata credential from %s", EARTHDATA_TOKEN_ENV)
    return ResolvedCredential(source=CredentialSource.ENV_TOKEN, token=token)


def resolve_credentials(
    source: CredentialSource,
    *,
    environ: dict[str, str] | None = None,
    netrc_path: Path | None = None,
    keyring_module: ModuleType | None = None,
) -> ResolvedCredential:
    """Resolve Earthdata credentials for ``source`` without any network I/O.

    Raises :class:`CredentialError` (``DL004``) with an actionable, secret-free
    message when the requested source is not configured.
    """
    env = os.environ if environ is None else environ

    if source is CredentialSource.KEYRING:
        return _resolve_keyring(keyring_module)
    if source is CredentialSource.ENV_TOKEN:
        return _resolve_env_token(env)
    if source is CredentialSource.NETRC:
        _verify_netrc(netrc_path)
        return ResolvedCredential(source=CredentialSource.NETRC, use_netrc=True)

    # AUTO: keyring -> env token -> netrc, with a single friendly error if none.
    def _try_netrc() -> ResolvedCredential:
        _verify_netrc(netrc_path)
        return ResolvedCredential(source=CredentialSource.NETRC, use_netrc=True)

    for attempt in (
        lambda: _resolve_keyring(keyring_module),
        lambda: _resolve_env_token(env),
        _try_netrc,
    ):
        try:
            return attempt()
        except CredentialError:
            continue
    raise CredentialError(
        "no Earthdata credentials found; store them with 'insar-prep auth login' "
        f"(or the GUI 'Earthdata Login' dialog), set {EARTHDATA_TOKEN_ENV}, or add a "
        "~/.netrc 'machine urs.earthdata.nasa.gov' entry",
        code=ErrorCode.DL004,
    )
