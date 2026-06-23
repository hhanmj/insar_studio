"""Earthdata credential resolution for the real ASF downloader.

Resolves *where* NASA Earthdata Login (EDL) credentials come from, without ever
performing network I/O and without persisting or logging any secret. Two sources
are supported in this first version (see ``docs/asf_download_credential_design.md``
section 4):

- ``env-token``: a bearer token in the ``EARTHDATA_TOKEN`` environment variable.
- ``netrc``: a standard ``machine urs.earthdata.nasa.gov`` entry in the user's
  ``~/.netrc`` (or ``~/_netrc`` on Windows), read by the HTTP client at the auth
  boundary -- this module only *verifies the entry exists* and never copies the
  login/password into the application.

A password is **never** accepted from the command line (threat T5). The resolved
value is held in memory only; :class:`ResolvedCredential` deliberately keeps the
token out of its ``repr`` so it cannot leak into a log or traceback.
"""

from __future__ import annotations

import netrc
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.core.logging import get_logger

logger = get_logger("providers.asf.credentials")

EARTHDATA_TOKEN_ENV = "EARTHDATA_TOKEN"
EDL_HOST = "urs.earthdata.nasa.gov"


class CredentialSource(StrEnum):
    """Where the real downloader should obtain Earthdata credentials."""

    NETRC = "netrc"
    ENV_TOKEN = "env-token"


@dataclass(frozen=True)
class ResolvedCredential:
    """An in-memory, non-persisted credential resolution result.

    Holds either a bearer ``token`` (from the environment) or a ``use_netrc``
    flag (the HTTP client reads ``~/.netrc`` itself). The token is intentionally
    excluded from ``repr`` so it never reaches a log, report, or traceback.
    """

    source: CredentialSource
    token: str | None = None
    use_netrc: bool = False

    def __repr__(self) -> str:
        kind = "token" if self.token else ("netrc" if self.use_netrc else "none")
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


def resolve_credentials(
    source: CredentialSource,
    *,
    environ: dict[str, str] | None = None,
    netrc_path: Path | None = None,
) -> ResolvedCredential:
    """Resolve Earthdata credentials for ``source`` without any network I/O.

    Raises :class:`CredentialError` (``DL004``) with an actionable, secret-free
    message when the requested source is not configured.
    """
    env = os.environ if environ is None else environ
    if source is CredentialSource.ENV_TOKEN:
        token = (env.get(EARTHDATA_TOKEN_ENV) or "").strip()
        if not token:
            raise CredentialError(
                f"{EARTHDATA_TOKEN_ENV} is not set; export an Earthdata bearer token "
                "or use --credential-source netrc",
                code=ErrorCode.DL004,
            )
        logger.debug("resolved Earthdata credential from %s", EARTHDATA_TOKEN_ENV)
        return ResolvedCredential(source=CredentialSource.ENV_TOKEN, token=token)

    _verify_netrc(netrc_path)
    return ResolvedCredential(source=CredentialSource.NETRC, use_netrc=True)
