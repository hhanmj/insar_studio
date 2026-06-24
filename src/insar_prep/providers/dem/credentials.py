"""OpenTopography API-key resolution for the real DEM downloader (Task 052).

Resolves *where* the OpenTopography Global DEM API key comes from, without ever
performing network I/O and without persisting or logging the key. The OpenTopo
API authenticates with a single personal API key (free registration), which is
far simpler than the Earthdata flow used for ASF SLCs -- there is no
username/password or bearer-token exchange, just one key passed as the
``API_Key`` query parameter.

Supported sources (mirroring ``providers/asf/credentials.py`` so the security
model is identical across providers):

- ``keyring``: the key stored in the OS secret store (Windows Credential
  Manager / macOS Keychain / Linux Secret Service) via the optional ``keyring``
  dependency. This is the friendly, GUI-/CLI-configurable source -- the key lives
  in the OS vault, never in a project file.
- ``env``: the key in the ``OPENTOPOGRAPHY_API_KEY`` environment variable.
- ``auto``: try keyring, then env (the default).

A key is **never** accepted as a plain command-line flag (it would leak into the
shell history and process list). The resolved value is held in memory only;
:class:`ResolvedDemKey` keeps the key out of its ``repr`` so it cannot leak into
a log or traceback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger, mask_secret

if TYPE_CHECKING:
    from types import ModuleType

logger = get_logger("providers.dem.credentials")

OPENTOPO_API_KEY_ENV = "OPENTOPOGRAPHY_API_KEY"

# OpenTopography account / API-key onboarding URLs (verified 2026-06-23). Each
# user registers their OWN free account and key: the free key is rate limited and
# tied to the account, so no key is ever bundled or shared by this project.
OPENTOPO_PORTAL_URL = "https://portal.opentopography.org/"
OPENTOPO_REGISTER_URL = "https://portal.opentopography.org/newUser"
OPENTOPO_LOGIN_URL = "https://portal.opentopography.org/login"
# Where the user generates a free personal OpenTopography API key.
OPENTOPO_API_KEY_URL = "https://portal.opentopography.org/requestService?service=api"
OPENTOPO_INFO_EMAIL = "info@opentopography.org"

# Free-tier limits, surfaced in the onboarding guidance so users understand why
# each person needs their own key (a shared key would hit the daily cap fast).
OPENTOPO_RATE_LIMIT_NOTE = (
    "The free key is rate limited (about 200 calls/24 h for academic users, "
    "50/24 h otherwise) and is tied to your account -- do not share it. "
    f"Commercial / for-profit integration needs an Enterprise key ({OPENTOPO_INFO_EMAIL})."
)


def opentopo_api_key_steps() -> list[str]:
    """Return the numbered steps to register and obtain a free OpenTopography key.

    Shared by the CLI (`dem-auth login` / `download-dem`) and the GUI dialog so the
    onboarding guidance lives in exactly one place.
    """
    return [
        f"1. Create a free OpenTopography account: {OPENTOPO_REGISTER_URL}",
        "   (enter email / name / affiliation, accept the Terms of Use, then "
        "activate via the email link).",
        f"2. Log in: {OPENTOPO_LOGIN_URL}",
        "3. Open the 'myOpenTopo' dashboard (top header) and scroll to 'Get an API Key'.",
        "4. Click 'Request API Key' to generate your personal key, then copy it.",
        "5. Store it with 'insar-prep dem-auth login' (saved in your OS keyring).",
    ]


def opentopo_api_key_guidance() -> str:
    """Return a friendly, multi-line 'how to get an API key' block (with the limits)."""
    lines = [
        "How to get a free OpenTopography API key:",
        *opentopo_api_key_steps(),
        "",
        OPENTOPO_RATE_LIMIT_NOTE,
    ]
    return "\n".join(lines)


# OS keyring storage layout. No secret is part of these identifiers; the key
# value lives only in the OS vault.
KEYRING_SERVICE = "insar-prep:opentopography"
_KR_API_KEY = "api_key"


class DemKeySource(StrEnum):
    """Where the real DEM downloader should obtain the OpenTopography key."""

    AUTO = "auto"
    KEYRING = "keyring"
    ENV = "env"


@dataclass(frozen=True)
class ResolvedDemKey:
    """An in-memory, non-persisted OpenTopography API-key resolution result.

    The ``api_key`` is intentionally excluded from ``repr`` so it never reaches a
    log, report, or traceback.
    """

    source: DemKeySource
    api_key: str

    def __repr__(self) -> str:
        return f"ResolvedDemKey(source={self.source.value}, key={mask_secret(self.api_key)})"


def get_keyring(keyring_module: ModuleType | None = None) -> ModuleType:
    """Return the ``keyring`` module (lazy import; part of the ``download`` extra)."""
    if keyring_module is not None:
        return keyring_module
    try:
        import keyring  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:
        raise CredentialError(
            "storing the OpenTopography API key needs the optional 'download' extra "
            "(keyring); install it with 'uv sync --extra download'",
            code=ErrorCode.DEM005,
        ) from exc
    return keyring


def store_api_key(api_key: str, *, keyring_module: ModuleType | None = None) -> None:
    """Store an OpenTopography API key in the OS keyring."""
    api_key = api_key.strip()
    if not api_key:
        raise CredentialError("refusing to store an empty API key", code=ErrorCode.DEM005)
    kr = get_keyring(keyring_module)
    kr.set_password(KEYRING_SERVICE, _KR_API_KEY, api_key)
    logger.info("stored OpenTopography API key in the OS keyring")


def clear_stored_api_key(*, keyring_module: ModuleType | None = None) -> bool:
    """Remove any stored OpenTopography API key from the keyring. Returns True if one existed."""
    kr = get_keyring(keyring_module)
    return _safe_delete(kr, _KR_API_KEY)


def stored_api_key_status(*, keyring_module: ModuleType | None = None) -> str:
    """Return a secret-free status: ``set`` or ``none``."""
    kr = get_keyring(keyring_module)
    return "set" if kr.get_password(KEYRING_SERVICE, _KR_API_KEY) else "none"


def _safe_delete(kr: ModuleType, key: str) -> bool:
    try:
        if kr.get_password(KEYRING_SERVICE, key) is None:
            return False
        kr.delete_password(KEYRING_SERVICE, key)
        return True
    except Exception:  # noqa: BLE001 - best-effort cleanup; backend errors are non-fatal
        logger.debug("could not delete keyring entry %s", key)
        return False


def _resolve_keyring(keyring_module: ModuleType | None = None) -> ResolvedDemKey:
    kr = get_keyring(keyring_module)
    api_key = kr.get_password(KEYRING_SERVICE, _KR_API_KEY)
    if api_key:
        logger.debug("resolved OpenTopography API key from the OS keyring")
        return ResolvedDemKey(source=DemKeySource.KEYRING, api_key=api_key)
    raise CredentialError(
        "no OpenTopography API key stored; run 'insar-prep dem-auth login' or use the "
        "GUI 'OpenTopography API Key' dialog",
        code=ErrorCode.DEM005,
    )


def _resolve_env(env: dict[str, str]) -> ResolvedDemKey:
    api_key = (env.get(OPENTOPO_API_KEY_ENV) or "").strip()
    if not api_key:
        raise CredentialError(
            f"{OPENTOPO_API_KEY_ENV} is not set; export your OpenTopography API key, "
            "store one with 'insar-prep dem-auth login', or get a free key at "
            f"{OPENTOPO_API_KEY_URL}",
            code=ErrorCode.DEM005,
        )
    logger.debug("resolved OpenTopography API key from %s", OPENTOPO_API_KEY_ENV)
    return ResolvedDemKey(source=DemKeySource.ENV, api_key=api_key)


def resolve_dem_api_key(
    source: DemKeySource = DemKeySource.AUTO,
    *,
    environ: dict[str, str] | None = None,
    keyring_module: ModuleType | None = None,
) -> ResolvedDemKey:
    """Resolve the OpenTopography API key for ``source`` without any network I/O.

    Raises :class:`CredentialError` (``DEM005``) with an actionable, secret-free
    message when the requested source is not configured.
    """
    env = os.environ if environ is None else environ

    if source is DemKeySource.KEYRING:
        return _resolve_keyring(keyring_module)
    if source is DemKeySource.ENV:
        return _resolve_env(env)

    # AUTO: keyring -> env, with a single friendly error if neither is set.
    for attempt in (
        lambda: _resolve_keyring(keyring_module),
        lambda: _resolve_env(env),
    ):
        try:
            return attempt()
        except CredentialError:
            continue
    raise CredentialError(
        "no OpenTopography API key found; store one with 'insar-prep dem-auth login' "
        f"(or the GUI dialog), or set {OPENTOPO_API_KEY_ENV}. Get a free key at "
        f"{OPENTOPO_API_KEY_URL}",
        code=ErrorCode.DEM005,
    )
