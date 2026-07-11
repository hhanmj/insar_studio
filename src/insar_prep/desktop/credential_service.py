from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from insar_prep.core.exceptions import InsarPrepError
from insar_prep.core.logging import mask_text
from insar_prep.desktop.helpers import (
    _detect_system_proxy,
    _error,
    _error_msg,
    _normalise_proxy_url,
)

_EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS = 5 * 60
_EARTHDATA_AUTH_SUCCESS_CACHE_SECONDS = 90 * 60


class CredentialDesktopService:
    """Own credential lifecycle actions decoupled from the main Api class."""

    def __init__(
        self,
        get_network_settings_cb: Any,
        default_cache_dir_cb: Any,
        log_action_cb: Any,
    ) -> None:
        self._get_network_settings = get_network_settings_cb
        self._default_cache_dir = default_cache_dir_cb
        self._log_action = log_action_cb
        self._earthdata_auth_failure_cache: dict[str, Any] | None = None
        self._earthdata_auth_failure_until: float = 0.0
        self._earthdata_auth_success_cache: dict[str, Any] | None = None
        self._earthdata_auth_success_until: float = 0.0
        self._earthdata_candidate_failure: dict[str, dict[str, Any]] = {}
        self._earthdata_candidate_failure_until: float = 0.0

    def _ensure_candidate_cache_fields(self) -> None:
        """Repair credential cache fields created by older desktop builds."""
        if not isinstance(getattr(self, "_earthdata_candidate_failure", None), dict):
            self._earthdata_candidate_failure = {}
        if not isinstance(getattr(self, "_earthdata_candidate_failure_until", None), (int, float)):
            self._earthdata_candidate_failure_until = 0.0

    def get_credential_status(self) -> dict:
        """Return privacy-safe credential status for ASF / OpenTopo / GACOS."""

        def _safe(loader) -> str:
            try:
                fn = loader()
            except Exception:  # noqa: BLE001
                return "unavailable"
            try:
                return fn()
            except Exception:  # noqa: BLE001
                return "unavailable"

        def _asf():
            from insar_prep.providers.asf.credentials import (
                EARTHDATA_TOKEN_ENV,
                CredentialSource,
                resolve_credentials,
                stored_credential_status,
            )

            def status() -> str:
                try:
                    stored = stored_credential_status()
                except Exception:  # noqa: BLE001
                    stored = "unavailable"
                if stored not in {"none", "unavailable"}:
                    return stored
                if os.environ.get(EARTHDATA_TOKEN_ENV):
                    return "env-token"
                try:
                    resolved = resolve_credentials(CredentialSource.NETRC)
                except Exception:  # noqa: BLE001
                    return "unavailable" if stored == "unavailable" else "none"
                return "netrc" if resolved.use_netrc else resolved.source.value

            return status

        def _dem():
            from insar_prep.providers.dem.credentials import stored_api_key_status

            return stored_api_key_status

        def _gacos():
            from insar_prep.providers.gacos.credentials import stored_gacos_email_status

            return stored_gacos_email_status

        earthdata_status = _safe(_asf)
        earthdata_input = {
            "mode": "none",
            "token": "",
            "username": "",
            "password": "",
        }
        if earthdata_status == "token" or earthdata_status.startswith("login:"):
            try:
                from insar_prep.providers.asf.credentials import (
                    CredentialSource,
                    resolve_credentials,
                )

                resolved = resolve_credentials(CredentialSource.KEYRING)
                if resolved.token:
                    earthdata_input.update(mode="token", token=resolved.token)
                elif resolved.username and resolved.password:
                    earthdata_input.update(
                        mode="login",
                        username=resolved.username,
                        password=resolved.password,
                    )
            except Exception:  # noqa: BLE001 - status still remains useful
                earthdata_input["mode"] = (
                    "token" if earthdata_status == "token" else "login"
                )
        elif earthdata_status == "env-token":
            earthdata_input.update(
                mode="token",
                token=str(os.environ.get("EARTHDATA_TOKEN") or ""),
            )
        elif earthdata_status == "netrc":
            earthdata_input["mode"] = "netrc"

        return {
            "ok": True,
            "earthdata": earthdata_status,
            "earthdata_input": earthdata_input,
            "opentopography": _safe(_dem),
            "gacos": _safe(_gacos),
        }

    def _cached_earthdata_auth_failure(self) -> dict | None:
        now = time.monotonic()
        if not self._earthdata_auth_failure_cache or now >= self._earthdata_auth_failure_until:
            self._earthdata_auth_failure_cache = None
            self._earthdata_auth_failure_until = 0.0
            return None
        remaining_minutes = max(1, int((self._earthdata_auth_failure_until - now + 59) // 60))
        cached = dict(self._earthdata_auth_failure_cache)
        message = str(cached.get("message") or "Earthdata/ASF 凭据未通过检测。")
        cached["message"] = (
            f"{message} 为保护账号，{remaining_minutes} 分钟内不会重复请求登录接口。"
        )
        return cached

    def _cached_earthdata_auth_success(self) -> dict | None:
        now = time.monotonic()
        if not self._earthdata_auth_success_cache or now >= self._earthdata_auth_success_until:
            self._earthdata_auth_success_cache = None
            self._earthdata_auth_success_until = 0.0
            return None
        cached = dict(self._earthdata_auth_success_cache)
        cached["message"] = "Earthdata/ASF 凭据最近已通过检测，当前会话内直接复用该状态。"
        return cached

    def _remember_earthdata_auth_failure(self, result: dict) -> dict:
        self._earthdata_auth_failure_cache = dict(result)
        self._earthdata_auth_failure_until = (
            time.monotonic() + _EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS
        )
        self._earthdata_auth_success_cache = None
        self._earthdata_auth_success_until = 0.0
        return result

    def _remember_earthdata_auth_success(self, result: dict) -> dict:
        self._earthdata_auth_success_cache = dict(result)
        self._earthdata_auth_success_until = (
            time.monotonic() + _EARTHDATA_AUTH_SUCCESS_CACHE_SECONDS
        )
        self._earthdata_auth_failure_cache = None
        self._earthdata_auth_failure_until = 0.0
        return result

    def _reset_earthdata_auth_cache(self) -> None:
        self._earthdata_auth_failure_cache = None
        self._earthdata_auth_failure_until = 0.0
        self._earthdata_auth_success_cache = None
        self._earthdata_auth_success_until = 0.0

    @staticmethod
    def _earthdata_candidate_key(resolved: object) -> str:
        token = str(getattr(resolved, "token", "") or "")
        username = str(getattr(resolved, "username", "") or "")
        password = str(getattr(resolved, "password", "") or "")
        use_netrc = str(bool(getattr(resolved, "use_netrc", False)))
        source = str(
            getattr(getattr(resolved, "source", ""), "value", getattr(resolved, "source", ""))
        )
        raw = "\0".join([source, token, username, password, use_netrc])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cached_earthdata_candidate_failure(self, key: str) -> dict | None:
        self._ensure_candidate_cache_fields()
        cached = self._earthdata_candidate_failure.get(key)
        if not cached:
            return None
        until = cached.get("until", 0.0)
        now = time.monotonic()
        if until <= now:
            self._earthdata_candidate_failure.pop(key, None)
            return None
        remaining_minutes = max(1, int((until - now + 59) // 60))
        message = cached.get("message", "这组 Earthdata/ASF 凭据刚刚校验失败。")
        return _error_msg(
            f"{message} 为保护账号，{remaining_minutes} "
            "分钟内不会对同一组账号/token 重复请求登录接口；"
            "请确认输入后修改凭据再保存。",
            "DL004",
        )

    def _remember_earthdata_candidate_failure(self, key: str, message: str) -> None:
        self._ensure_candidate_cache_fields()
        until = time.monotonic() + _EARTHDATA_AUTH_FAILURE_COOLDOWN_SECONDS
        self._earthdata_candidate_failure[key] = {
            "until": until,
            "message": message,
        }
        self._earthdata_candidate_failure_until = max(
            self._earthdata_candidate_failure_until, until
        )

    def _earthdata_network_options(self) -> dict[str, Any]:
        settings = self._get_network_settings()
        proxy_enabled = bool(settings.get("proxy_enabled"))
        proxy_url = _normalise_proxy_url(settings.get("proxy_url")) if proxy_enabled else ""
        if proxy_enabled and not proxy_url:
            proxy_url = _detect_system_proxy()
        return {
            "proxy_url": proxy_url,
            "ssl_verify": bool(settings.get("asf_ssl_verify", True)),
            "trust_env": proxy_enabled,
        }

    def _probe_earthdata_resolved(self, resolved: object) -> dict:
        from insar_prep.providers.asf.downloader import probe_earthdata_auth

        network = self._earthdata_network_options()
        ok, message = probe_earthdata_auth(
            resolved,  # type: ignore[arg-type]
            proxy_url=network["proxy_url"],
            ssl_verify=network["ssl_verify"],
            trust_env=network["trust_env"],
            timeout=20.0,
        )
        if ok:
            return {
                "ok": True,
                "configured": True,
                "status": "valid",
                "message": "Earthdata/ASF 凭据正常。",
            }
        status = (
            "expired"
            if "401" in message or "403" in message or "rejected" in message
            else "unknown"
        )
        return {
            "ok": True,
            "configured": True,
            "status": status,
            "message": message,
        }

    def _validate_earthdata_candidate(self, resolved: object) -> dict:
        key = self._earthdata_candidate_key(resolved)
        cached = self._cached_earthdata_candidate_failure(key)
        if cached is not None:
            return cached
        try:
            auth = self._probe_earthdata_resolved(resolved)
        except Exception as exc:  # noqa: BLE001
            message = f"Earthdata/ASF 凭据校验不可用，未保存：{mask_text(str(exc))}"
            self._remember_earthdata_candidate_failure(key, message)
            return _error_msg(message, "DL004")
        if auth.get("status") == "valid":
            self._earthdata_candidate_failure.pop(key, None)
            return auth
        message = (
            f"Earthdata/ASF 凭据校验失败，未保存；原有凭据保持不变。{auth.get('message') or ''}"
        )
        self._remember_earthdata_candidate_failure(key, message)
        return _error_msg(message, "DL004")

    def _validate_opentopography_key(self, api_key: str) -> dict:
        api_key = str(api_key or "").strip()
        if not api_key:
            return _error_msg("OpenTopography API Key 不能为空，未保存。", "DEM005")
        try:
            from insar_prep.core.models import BBox
            from insar_prep.providers.dem.credentials import DemKeySource, ResolvedDemKey
            from insar_prep.providers.dem.downloader import (
                DemDownloadOutcome,
                DemDownloadRequest,
                RealDemDownloader,
            )

            resolved = ResolvedDemKey(source=DemKeySource.KEYRING, api_key=api_key)
            request = DemDownloadRequest(
                region_safe_name="credential_probe",
                dataset="COP30",
                demtype="COP30",
                bbox=BBox(west=110.0, east=110.02, south=30.0, north=30.02),
                destination=self._default_cache_dir() / "_credential_probe" / "opentopo_probe.tif",
            )
            result = RealDemDownloader(
                resolved=resolved,
                max_retries=1,
                timeout=20.0,
            ).verify(request)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(
                f"OpenTopography API Key 联网校验不可用，未保存：{mask_text(str(exc))}",
                "DEM005",
            )
        if result.outcome == DemDownloadOutcome.VERIFIED:
            return {
                "ok": True,
                "message": "OpenTopography API Key 校验通过。",
            }
        code = result.error_code or "DEM005"
        prefix = "OpenTopography API Key 校验失败，未保存"
        if code != "DEM005":
            prefix = "OpenTopography API Key 无法完成联网校验，未保存"
        return _error_msg(f"{prefix}：{mask_text(result.message)}", code)

    def check_earthdata_auth(self, force: bool = False) -> dict:
        """Probe saved Earthdata credentials and report only user-actionable states."""
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                resolve_credentials,
                stored_credential_status,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": True,
                "configured": False,
                "status": "unavailable",
                "message": f"Earthdata 凭据检查不可用：{exc}",
            }

        cached_failure = self._cached_earthdata_auth_failure()
        if cached_failure is not None:
            return cached_failure
        if not bool(force):
            cached_success = self._cached_earthdata_auth_success()
            if cached_success is not None:
                return cached_success

        try:
            stored = stored_credential_status()
        except Exception:  # noqa: BLE001
            stored = "unavailable"
        try:
            resolved = resolve_credentials(CredentialSource.AUTO)
        except Exception as exc:  # noqa: BLE001
            if stored in {"none", "unavailable"}:
                return {
                    "ok": True,
                    "configured": False,
                    "status": "missing",
                    "message": "未保存 Earthdata/ASF 凭据。",
                }
            return self._remember_earthdata_auth_failure(
                {
                    "ok": True,
                    "configured": True,
                    "status": "invalid",
                    "message": f"Earthdata 凭据无法读取：{exc}",
                }
            )

        try:
            result = self._probe_earthdata_resolved(resolved)
        except Exception as exc:  # noqa: BLE001
            result = {
                "ok": True,
                "configured": True,
                "status": "unknown",
                "message": f"Earthdata/ASF 凭据联网检测失败：{mask_text(str(exc))}",
            }
        if result.get("status") == "valid":
            return self._remember_earthdata_auth_success(result)
        return self._remember_earthdata_auth_failure(result)

    def save_earthdata_token(self, token: str) -> dict:
        """Store a NASA Earthdata bearer token in the OS keyring."""
        token = str(token or "").strip()
        if not token:
            return _error_msg("Earthdata Token 不能为空，未保存。", "DL004")
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                ResolvedCredential,
                store_token,
            )

            auth = self._validate_earthdata_candidate(
                ResolvedCredential(source=CredentialSource.KEYRING, token=token)
            )
            if not auth.get("ok"):
                return auth
            store_token(token)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._reset_earthdata_auth_cache()
        self._remember_earthdata_auth_success(auth)
        self._log_action("Earthdata Token 校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "auth": auth}

    def save_earthdata_login(self, username: str, password: str) -> dict:
        """Store NASA Earthdata username/password in the OS keyring."""
        username = str(username or "").strip()
        password = str(password or "")
        if not username or not password:
            return _error_msg("Earthdata 用户名和密码都不能为空，未保存。", "DL004")
        try:
            from insar_prep.providers.asf.credentials import (
                CredentialSource,
                ResolvedCredential,
                store_login,
            )

            auth = self._validate_earthdata_candidate(
                ResolvedCredential(
                    source=CredentialSource.KEYRING,
                    username=username,
                    password=password,
                )
            )
            if not auth.get("ok"):
                return auth
            store_login(username, password)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._reset_earthdata_auth_cache()
        self._remember_earthdata_auth_success(auth)
        self._log_action("Earthdata 登录凭据校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "auth": auth}

    def clear_earthdata_credentials(self) -> dict:
        """Remove stored NASA Earthdata credentials from the OS keyring."""
        try:
            from insar_prep.providers.asf.credentials import clear_stored_credentials

            removed = clear_stored_credentials()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DL004")
        self._reset_earthdata_auth_cache()
        self._log_action("已清除 Earthdata 凭据", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}

    def save_opentopography_key(self, api_key: str) -> dict:
        """Store an OpenTopography API key in the OS keyring."""
        api_key = str(api_key or "").strip()
        check = self._validate_opentopography_key(api_key)
        if not check.get("ok"):
            return check
        try:
            from insar_prep.providers.dem.credentials import store_api_key

            store_api_key(api_key)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM005")
        self._log_action("OpenTopography API Key 校验通过并已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status(), "check": check}

    def clear_opentopography_key(self) -> dict:
        """Remove the stored OpenTopography API key from the OS keyring."""
        try:
            from insar_prep.providers.dem.credentials import clear_stored_api_key

            removed = clear_stored_api_key()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM005")
        self._log_action("已清除 OpenTopography API Key", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}

    def save_gacos_email(self, email: str) -> dict:
        """Store a GACOS email in the OS keyring."""
        email = str(email or "").strip()
        if not email:
            return _error_msg("GACOS 邮箱不能为空，未保存。", "GAC003")
        try:
            from insar_prep.providers.gacos.credentials import store_gacos_email

            store_gacos_email(email)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC003")
        self._log_action("GACOS 邮箱已保存", kind="settings")
        return {"ok": True, "status": self.get_credential_status()}

    def clear_gacos_email(self) -> dict:
        """Remove the stored GACOS email from the OS keyring."""
        try:
            from insar_prep.providers.gacos.credentials import clear_stored_gacos_email

            removed = clear_stored_gacos_email()
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC003")
        self._log_action("已清除 GACOS 邮箱", kind="settings")
        return {"ok": True, "removed": removed, "status": self.get_credential_status()}
