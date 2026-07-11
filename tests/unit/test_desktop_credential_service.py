from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from insar_prep.desktop.credential_service import CredentialDesktopService
from insar_prep.providers.asf.credentials import CredentialSource, ResolvedCredential


@pytest.fixture
def service_callbacks():
    """Return mock callbacks to construct the service in isolation."""
    get_settings = MagicMock(
        return_value={"proxy_enabled": True, "proxy_url": "127.0.0.1:8080", "asf_ssl_verify": True}
    )
    default_dir = MagicMock(return_value=Path("/tmp/cache"))
    log_action = MagicMock()
    return get_settings, default_dir, log_action


def test_credential_service_initialization(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)
    status = service.get_credential_status()
    assert status["ok"] is True
    assert "earthdata" in status
    assert "opentopography" in status
    assert "gacos" in status


def test_credential_status_returns_saved_token_for_form_refill(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with (
        patch(
            "insar_prep.providers.asf.credentials.stored_credential_status",
            return_value="token",
        ),
        patch(
            "insar_prep.providers.asf.credentials.resolve_credentials",
            return_value=ResolvedCredential(
                source=CredentialSource.KEYRING,
                token="saved-token",
            ),
        ),
    ):
        status = service.get_credential_status()

    assert status["earthdata_input"] == {
        "mode": "token",
        "token": "saved-token",
        "username": "",
        "password": "",
    }


def test_credential_status_returns_saved_login_for_form_refill(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with (
        patch(
            "insar_prep.providers.asf.credentials.stored_credential_status",
            return_value="login:u***",
        ),
        patch(
            "insar_prep.providers.asf.credentials.resolve_credentials",
            return_value=ResolvedCredential(
                source=CredentialSource.KEYRING,
                username="user",
                password="saved-password",
            ),
        ),
    ):
        status = service.get_credential_status()

    assert status["earthdata_input"] == {
        "mode": "login",
        "token": "",
        "username": "user",
        "password": "saved-password",
    }


def test_credential_status_marks_netrc_without_copying_its_secrets(
    service_callbacks, monkeypatch
) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)

    with (
        patch(
            "insar_prep.providers.asf.credentials.stored_credential_status",
            return_value="none",
        ),
        patch(
            "insar_prep.providers.asf.credentials.resolve_credentials",
            return_value=ResolvedCredential(
                source=CredentialSource.NETRC,
                use_netrc=True,
            ),
        ),
    ):
        status = service.get_credential_status()

    assert status["earthdata"] == "netrc"
    assert status["earthdata_input"] == {
        "mode": "netrc",
        "token": "",
        "username": "",
        "password": "",
    }


def test_credential_service_auth_cache_behavior(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    assert service._cached_earthdata_auth_failure() is None
    assert service._cached_earthdata_auth_success() is None

    service._remember_earthdata_auth_success({"status": "valid", "message": "OK"})
    cached_success = service._cached_earthdata_auth_success()
    assert cached_success is not None
    assert "当前会话内直接复用" in cached_success["message"]

    service._remember_earthdata_auth_failure({"status": "invalid", "message": "FAIL"})
    cached_failure = service._cached_earthdata_auth_failure()
    assert cached_failure is not None
    assert "分钟内不会重复请求" in cached_failure["message"]

    service._reset_earthdata_auth_cache()
    assert service._cached_earthdata_auth_failure() is None
    assert service._cached_earthdata_auth_success() is None


def test_earthdata_candidate_failure_cache(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)
    key = "dummy_key"

    assert service._cached_earthdata_candidate_failure(key) is None
    service._remember_earthdata_candidate_failure(key, "Invalid credentials")
    cached = service._cached_earthdata_candidate_failure(key)
    assert cached is not None
    assert "Invalid credentials" in cached["error"]

    service._earthdata_candidate_failure[key]["until"] = time.monotonic() - 10
    assert service._cached_earthdata_candidate_failure(key) is None


def test_earthdata_candidate_cache_recovers_missing_legacy_fields(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)
    del service._earthdata_candidate_failure
    del service._earthdata_candidate_failure_until

    assert service._cached_earthdata_candidate_failure("legacy") is None
    service._remember_earthdata_candidate_failure("legacy", "失败")
    assert service._cached_earthdata_candidate_failure("legacy") is not None

def test_earthdata_network_options(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    opts = service._earthdata_network_options()
    assert opts["proxy_url"] == "http://127.0.0.1:8080"
    assert opts["ssl_verify"] is True
    assert opts["trust_env"] is True

    # 代理未启用
    get_settings.return_value["proxy_enabled"] = False
    opts = service._earthdata_network_options()
    assert opts["proxy_url"] == ""


def test_save_earthdata_token(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with (
        patch("insar_prep.providers.asf.credentials.store_token") as mock_store,
        patch.object(
            service, "_validate_earthdata_candidate", return_value={"ok": True, "status": "valid"}
        ),
    ):
        res = service.save_earthdata_token("my_token")
        assert res["ok"] is True
        mock_store.assert_called_once_with("my_token")
        log_action.assert_called_once()

    # 测试空token阻拦
    res = service.save_earthdata_token("  ")
    assert res["ok"] is False
    assert "不能为空" in res["error"]


def test_save_earthdata_login(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with (
        patch("insar_prep.providers.asf.credentials.store_login") as mock_store,
        patch.object(
            service, "_validate_earthdata_candidate", return_value={"ok": True, "status": "valid"}
        ),
    ):
        res = service.save_earthdata_login("user", "pass")
        assert res["ok"] is True
        mock_store.assert_called_once_with("user", "pass")

    # 空值拦截
    res = service.save_earthdata_login("", "pass")
    assert res["ok"] is False


def test_clear_earthdata_credentials(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with patch(
        "insar_prep.providers.asf.credentials.clear_stored_credentials", return_value=True
    ) as mock_clear:
        res = service.clear_earthdata_credentials()
        assert res["ok"] is True
        mock_clear.assert_called_once()


def test_save_opentopography_key(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with (
        patch("insar_prep.providers.dem.credentials.store_api_key") as mock_store,
        patch.object(service, "_validate_opentopography_key", return_value={"ok": True}),
    ):
        res = service.save_opentopography_key("opento_key")
        assert res["ok"] is True
        mock_store.assert_called_once_with("opento_key")


def test_clear_opentopography_key(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with patch(
        "insar_prep.providers.dem.credentials.clear_stored_api_key", return_value=True
    ) as mock_clear:
        res = service.clear_opentopography_key()
        assert res["ok"] is True
        mock_clear.assert_called_once()


def test_save_and_clear_gacos_email(service_callbacks) -> None:
    get_settings, default_dir, log_action = service_callbacks
    service = CredentialDesktopService(get_settings, default_dir, log_action)

    with patch("insar_prep.providers.gacos.credentials.store_gacos_email") as mock_store:
        res = service.save_gacos_email("test@gacos.com")
        assert res["ok"] is True
        mock_store.assert_called_once_with("test@gacos.com")

    with patch(
        "insar_prep.providers.gacos.credentials.clear_stored_gacos_email", return_value=True
    ) as mock_clear:
        res = service.clear_gacos_email()
        assert res["ok"] is True
        mock_clear.assert_called_once()
