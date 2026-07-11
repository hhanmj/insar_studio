"""Unit tests for GacosWebFormService."""

from __future__ import annotations

import copy
import urllib.parse

import pytest

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError
from insar_prep.desktop.gacos_webform_service import GacosWebFormService


@pytest.fixture
def valid_submission_payload() -> dict:
    return {
        "kind": "web_form_submission",
        "provider": "gacos",
        "execution_mode": "browser_assisted_web_form",
        "portal_url": "http://www.gacos.net/",
        "submit_endpoint": "http://www.gacos.net/M/action_page.php",
        "method": "POST",
        "content_type": "application/x-www-form-urlencoded",
        "output_format": "geotiff",
        "requires_user_confirmation": True,
        "requires_email_delivery": True,
        "email_field": "email",
        "result_delivery": "email_link",
        "download_link_handling": "paste_email_link_then_import",
        "batches": [
            {
                "batch_id": "gacos_batch_1",
                "batch_index": 1,
                "batch_count": 1,
                "date_count": 2,
                "dates": ["2024-03-12", "2024-03-24"],
                "date_text": "20240312\n20240324",
                "bbox": {
                    "west": 109.45,
                    "east": 117.55,
                    "south": 19.95,
                    "north": 25.55,
                    "crs": "EPSG:4326",
                },
                "method": "POST",
                "endpoint": "http://www.gacos.net/M/action_page.php",
                "content_type": "application/x-www-form-urlencoded",
                "form_fields": {
                    "N": "25.55",
                    "S": "19.95",
                    "W": "109.45",
                    "E": "117.55",
                    "H": "10",
                    "M": "26",
                    "date": "20240312\n20240324",
                    "type": "2",
                    "seq": "OSM Map",
                },
                "required_sensitive_fields": ["email"],
            }
        ],
    }


def test_gacos_service_dry_run_success(valid_submission_payload) -> None:
    service = GacosWebFormService()
    email = "test@example.com"

    res = service.dry_run_preview(valid_submission_payload, email)

    assert res["ok"] is True
    assert len(res["batches"]) == 1
    batch = res["batches"][0]

    # Verify masked fields
    assert batch["form_fields_masked"]["email"] == "<EMAIL>"
    assert '-d "email=%3CEMAIL%3E"' in batch["curl_preview_masked"]
    assert batch["form_fields_masked"]["N"] == "25.55"
    assert batch["form_fields_masked"]["H"] == "10"

    # Verify real fields
    assert batch["form_fields_real"]["email"] == email
    assert f'-d "email={urllib.parse.quote_plus(email)}"' in batch["curl_preview_real"]
    assert batch["form_fields_real"]["N"] == "25.55"
    assert batch["form_fields_real"]["M"] == "26"

    # Verify URL encoding
    assert "date=20240312%0A20240324" in batch["curl_preview_masked"]
    assert (
        "seq=OSM+Map" in batch["curl_preview_masked"]
        or "seq=OSM%20Map" in batch["curl_preview_masked"]
    )


def test_gacos_service_missing_email(valid_submission_payload) -> None:
    service = GacosWebFormService()

    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(valid_submission_payload, email="")
    assert exc_info.value.code == ErrorCode.GAC003
    assert "Email" in str(exc_info.value)


def test_gacos_service_invalid_email_format(valid_submission_payload) -> None:
    service = GacosWebFormService()

    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(valid_submission_payload, email="invalid-email")
    assert exc_info.value.code == ErrorCode.GAC003


def test_gacos_service_endpoint_check(valid_submission_payload) -> None:
    service = GacosWebFormService()

    bad_payload = copy.deepcopy(valid_submission_payload)
    bad_payload["submit_endpoint"] = "http://malicious.com/action.php"

    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003
    assert "official" in str(exc_info.value)


def test_gacos_service_unsupported_execution_mode(valid_submission_payload) -> None:
    service = GacosWebFormService()

    bad_payload = copy.deepcopy(valid_submission_payload)
    bad_payload["execution_mode"] = "direct_download"

    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003


def test_gacos_service_structural_headers(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # 1. Invalid payload kind
    bad_payload1 = copy.deepcopy(valid_submission_payload)
    bad_payload1["kind"] = "direct_download_execution"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload1, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003

    # 2. Invalid root method
    bad_payload2 = copy.deepcopy(valid_submission_payload)
    bad_payload2["method"] = "GET"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload2, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003

    # 3. Invalid batch content type
    bad_payload3 = copy.deepcopy(valid_submission_payload)
    bad_payload3["batches"][0]["content_type"] = "multipart/form-data"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload3, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003

    # 4. Empty batches list
    bad_payload4 = copy.deepcopy(valid_submission_payload)
    bad_payload4["batches"] = []
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload4, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003


def test_gacos_service_hour_minute_validation(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # 1. Hour bounds check (greater than 23)
    bad_payload1 = copy.deepcopy(valid_submission_payload)
    bad_payload1["batches"][0]["form_fields"]["H"] = "24"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload1, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003
    assert "Hour must be in [0, 23]" in str(exc_info.value)

    # 2. Minute bounds check (less than 0)
    bad_payload2 = copy.deepcopy(valid_submission_payload)
    bad_payload2["batches"][0]["form_fields"]["M"] = "-5"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload2, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003
    assert "Minute must be in [0, 59]" in str(exc_info.value)

    # 3. Non-integer inputs
    bad_payload3 = copy.deepcopy(valid_submission_payload)
    bad_payload3["batches"][0]["form_fields"]["H"] = "ten"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload3, "test@example.com")
    assert exc_info.value.code == ErrorCode.GUI003
    assert "must be integers" in str(exc_info.value)


def test_gacos_service_invalid_coordinates(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # 1. Latitude out of bounds
    bad_payload1 = copy.deepcopy(valid_submission_payload)
    bad_payload1["batches"][0]["form_fields"]["N"] = "95.55"
    with pytest.raises(InputValidationError):
        service.validate_submission(bad_payload1, "test@example.com")

    # 2. Longitude out of bounds
    bad_payload2 = copy.deepcopy(valid_submission_payload)
    bad_payload2["batches"][0]["form_fields"]["E"] = "185.0"
    with pytest.raises(InputValidationError):
        service.validate_submission(bad_payload2, "test@example.com")

    # 3. N <= S conflict
    bad_payload3 = copy.deepcopy(valid_submission_payload)
    bad_payload3["batches"][0]["form_fields"]["N"] = "19.0"
    bad_payload3["batches"][0]["form_fields"]["S"] = "20.0"
    with pytest.raises(InputValidationError):
        service.validate_submission(bad_payload3, "test@example.com")


def test_gacos_service_invalid_date_text(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # Invalid YYYY-MM-DD hyphen format
    bad_payload1 = copy.deepcopy(valid_submission_payload)
    bad_payload1["batches"][0]["form_fields"]["date"] = "2024-03-12"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload1, "test@example.com")
    assert exc_info.value.code == ErrorCode.GAC003

    # Invalid dates values (such as month 13)
    bad_payload2 = copy.deepcopy(valid_submission_payload)
    bad_payload2["batches"][0]["form_fields"]["date"] = "20241345"
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload2, "test@example.com")
    assert exc_info.value.code == ErrorCode.GAC003


def test_gacos_service_limits(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # 1. Batches limit exceeds 100
    bad_payload1 = copy.deepcopy(valid_submission_payload)
    single_batch = bad_payload1["batches"][0]
    bad_payload1["batches"] = [single_batch] * 101
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload1, "test@example.com")
    assert "exceeds maximum limit" in str(exc_info.value)

    # 2. Dates line count exceeds 1000
    bad_payload2 = copy.deepcopy(valid_submission_payload)
    bad_payload2["batches"][0]["form_fields"]["date"] = "\n".join(["20240312"] * 1001)
    with pytest.raises(InputValidationError) as exc_info:
        service.validate_submission(bad_payload2, "test@example.com")
    assert "exceeds 1000" in str(exc_info.value)


def test_gacos_service_no_side_effects(valid_submission_payload) -> None:
    service = GacosWebFormService()
    payload_copy = copy.deepcopy(valid_submission_payload)

    # Dry run execution
    service.dry_run_preview(payload_copy, "test@example.com")

    # Verify original payload object is completely untouched
    assert payload_copy == valid_submission_payload


def test_gacos_service_forbidden_persist(valid_submission_payload, monkeypatch) -> None:
    service = GacosWebFormService()
    email = "secret_email@leak.com"

    # 1. Physical level defense: block open/write operations to disk
    def forbidden_io(*args, **kwargs):
        raise AssertionError("Security Alert: write/IO operations on disk!")

    import builtins  # noqa: PLC0415

    monkeypatch.setattr(builtins, "open", forbidden_io)

    service.validate_submission(valid_submission_payload, email)
    res = service.dry_run_preview(valid_submission_payload, email)

    assert res["ok"] is True

    # 2. Memory state defense: no email fields inside the service instance
    assert not hasattr(service, "email")
    assert not hasattr(service, "gacos_email")
    for val in service.__dict__.values():
        assert email not in str(val)


def test_gacos_service_submit_disabled(valid_submission_payload) -> None:
    service = GacosWebFormService()

    # Real submit must fail with standard GUI003 disabled envelope
    res = service.submit_webform(valid_submission_payload, "test@example.com")
    assert res["ok"] is False
    assert "真实提交：第一阶段未启用" in res["error"]
    assert res["code"] == "GUI003"
