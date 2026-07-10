"""Desktop helper service for formatting and validating GACOS web form payloads."""

from __future__ import annotations

import copy
import re
import urllib.parse
from datetime import datetime
from typing import Any

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import InputValidationError

GACOS_OFFICIAL_ENDPOINT = "http://www.gacos.net/M/action_page.php"
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class GacosWebFormService:
    """Handles verification and Curl preview generation for the GACOS web form.

    This service is entirely in-memory and stateless to guarantee that email
    addresses are never persisted on disk.
    """

    def validate_structure_only(self, payload: Any) -> None:
        """Validate the structural fields of the payload without checking the email."""
        if not isinstance(payload, dict):
            raise InputValidationError(
                "Invalid payload format, must be a dict",
                code=ErrorCode.GUI003,
            )

        if payload.get("kind") != "web_form_submission":
            raise InputValidationError(
                "Unsupported payload kind, expected 'web_form_submission'",
                code=ErrorCode.GUI003,
            )

        if payload.get("provider") != "gacos":
            raise InputValidationError(
                "Unsupported provider, only 'gacos' is allowed",
                code=ErrorCode.GUI003,
            )

        if payload.get("execution_mode") != "browser_assisted_web_form":
            raise InputValidationError(
                "Unsupported execution mode",
                code=ErrorCode.GUI003,
            )

        if payload.get("submit_endpoint") != GACOS_OFFICIAL_ENDPOINT:
            raise InputValidationError(
                "GACOS submit endpoint must be the official portal",
                code=ErrorCode.GUI003,
            )

        if payload.get("method") != "POST":
            raise InputValidationError(
                "Submission method must be POST",
                code=ErrorCode.GUI003,
            )

        if payload.get("content_type") != "application/x-www-form-urlencoded":
            raise InputValidationError(
                "Content-Type must be application/x-www-form-urlencoded",
                code=ErrorCode.GUI003,
            )

        batches = payload.get("batches")
        if not isinstance(batches, list):
            raise InputValidationError(
                "Missing batches list in payload",
                code=ErrorCode.GUI003,
            )

        if not batches:
            raise InputValidationError(
                "Batches list cannot be empty",
                code=ErrorCode.GUI003,
            )

        if len(batches) > 100:
            raise InputValidationError(
                "Number of batches exceeds maximum limit of 100",
                code=ErrorCode.GUI003,
            )

        for index, batch in enumerate(batches):
            if not isinstance(batch, dict):
                raise InputValidationError(
                    f"Invalid batch layout at index {index}",
                    code=ErrorCode.GUI003,
                )

            if batch.get("endpoint") != GACOS_OFFICIAL_ENDPOINT:
                raise InputValidationError(
                    f"Invalid endpoint in batch {index}",
                    code=ErrorCode.GUI003,
                )

            if batch.get("method") != "POST":
                raise InputValidationError(
                    f"Method must be POST in batch {index}",
                    code=ErrorCode.GUI003,
                )

            if batch.get("content_type") != "application/x-www-form-urlencoded":
                raise InputValidationError(
                    f"Content-Type must be urlencoded in batch {index}",
                    code=ErrorCode.GUI003,
                )

            form_fields = batch.get("form_fields")
            if not isinstance(form_fields, dict):
                raise InputValidationError(
                    f"Missing form_fields in batch {index}",
                    code=ErrorCode.GUI003,
                )

            # Check all 9 required fields
            required_keys = ["N", "S", "W", "E", "H", "M", "date", "type", "seq"]
            for key in required_keys:
                if key not in form_fields:
                    raise InputValidationError(
                        f"Missing required field '{key}' in batch {index}",
                        code=ErrorCode.GUI003,
                    )

            # Validate Hour and Minute ranges
            h_str = str(form_fields["H"]).strip()
            m_str = str(form_fields["M"]).strip()
            try:
                h_val = int(h_str)
                m_val = int(m_str)
            except ValueError as exc:
                raise InputValidationError(
                    f"Hour and minute must be integers in batch {index}",
                    code=ErrorCode.GUI003,
                ) from exc

            if not (0 <= h_val <= 23):
                raise InputValidationError(
                    f"Hour must be in [0, 23] in batch {index}, got '{h_str}'",
                    code=ErrorCode.GUI003,
                )
            if not (0 <= m_val <= 59):
                raise InputValidationError(
                    f"Minute must be in [0, 59] in batch {index}, got '{m_str}'",
                    code=ErrorCode.GUI003,
                )

            # Validate coordinates bounds
            try:
                n = float(form_fields["N"])
                s = float(form_fields["S"])
                w = float(form_fields["W"])
                e = float(form_fields["E"])
            except ValueError as exc:
                raise InputValidationError(
                    f"Coordinates must be valid numbers in batch {index}",
                    code=ErrorCode.GUI003,
                ) from exc

            if not (-90.0 <= n <= 90.0) or not (-90.0 <= s <= 90.0):
                raise InputValidationError(
                    f"Latitude bounds must be [-90, 90] in batch {index}",
                    code=ErrorCode.GUI003,
                )
            if not (-180.0 <= w <= 180.0) or not (-180.0 <= e <= 180.0):
                raise InputValidationError(
                    f"Longitude bounds must be [-180, 180] in batch {index}",
                    code=ErrorCode.GUI003,
                )

            if n <= s:
                raise InputValidationError(
                    f"Latitude North ({n}) must be greater than South ({s}) in batch {index}",
                    code=ErrorCode.GUI003,
                )

            if e <= w:
                raise InputValidationError(
                    f"Longitude East ({e}) must be greater than West ({w}) in batch {index}",
                    code=ErrorCode.GUI003,
                )

            # Validate dates
            date_text = str(form_fields["date"])
            lines = [line.strip() for line in date_text.splitlines() if line.strip()]
            if not lines:
                raise InputValidationError(
                    f"No dates found in batch {index}",
                    code=ErrorCode.GUI003,
                )
            if len(lines) > 1000:
                raise InputValidationError(
                    f"Number of dates in batch {index} exceeds 1000",
                    code=ErrorCode.GUI003,
                )

            for line in lines:
                if len(line) != 8 or not line.isdigit():
                    raise InputValidationError(
                        f"Invalid 8-digit date format '{line}' in batch {index}",
                        code=ErrorCode.GAC003,
                    )
                try:
                    datetime.strptime(line, "%Y%m%d")
                except ValueError as exc:
                    raise InputValidationError(
                        f"Invalid date value '{line}' in batch {index}",
                        code=ErrorCode.GAC003,
                    ) from exc

    def validate_submission(self, payload: Any, email: str) -> None:
        """Validate structure and confirm the presence of a valid email address."""
        self.validate_structure_only(payload)

        if not email or not email.strip():
            raise InputValidationError(
                "GACOS ZTD request requires a valid Email address",
                code=ErrorCode.GAC003,
            )

        email_clean = email.strip()
        if not EMAIL_REGEX.match(email_clean):
            raise InputValidationError(
                "Invalid GACOS Email address format",
                code=ErrorCode.GAC003,
            )

    def dry_run_preview(self, payload: Any, email: str = "") -> dict:
        """Generate dual masked and real Curl previews for GACOS submission.

        Always performs structural check first. If email is empty or invalid,
        form_fields_real and curl_preview_real will be empty/null, ensuring
        no exceptions are thrown for missing emails during preview phase.
        """
        cloned_payload = copy.deepcopy(payload)

        # Validate basic structure without email
        # (so we can generate masked preview even if email is missing)
        self.validate_structure_only(cloned_payload)

        email_clean = email.strip() if email else ""
        has_valid_email = bool(email_clean and EMAIL_REGEX.match(email_clean))

        batches_preview = []
        for index, batch in enumerate(cloned_payload["batches"]):
            form_fields = batch["form_fields"]

            # Masked version
            masked_fields = copy.deepcopy(form_fields)
            if "email" in batch.get("required_sensitive_fields", []):
                masked_fields["email"] = "<EMAIL>"

            # Sort fields to maintain stable output ordering in preview Curl
            sorted_masked_items = sorted(masked_fields.items())
            masked_data_parts = [
                f'-d "{k}={urllib.parse.quote_plus(str(v))}"'
                for k, v in sorted_masked_items
            ]
            masked_data_str = " \\\n  ".join(masked_data_parts)
            endpoint = batch.get("endpoint") or cloned_payload["submit_endpoint"]
            masked_curl = (
                f'curl -X POST "{endpoint}" \\\n'
                f'  -H "Content-Type: application/x-www-form-urlencoded" \\\n'
                f'  {masked_data_str}'
            )

            # Real version (Only if email is valid)
            real_fields = None
            real_curl = ""
            if has_valid_email:
                real_fields = copy.deepcopy(form_fields)
                if "email" in batch.get("required_sensitive_fields", []):
                    real_fields["email"] = email_clean

                sorted_real_items = sorted(real_fields.items())
                real_data_parts = [
                    f'-d "{k}={urllib.parse.quote_plus(str(v))}"'
                    for k, v in sorted_real_items
                ]
                real_data_str = " \\\n  ".join(real_data_parts)
                real_curl = (
                    f'curl -X POST "{endpoint}" \\\n'
                    f'  -H "Content-Type: application/x-www-form-urlencoded" \\\n'
                    f'  {real_data_str}'
                )

            batches_preview.append({
                "batch_id": batch.get("batch_id") or f"batch_{index + 1}",
                "batch_index": batch.get("batch_index") or (index + 1),
                "form_fields_masked": masked_fields,
                "form_fields_real": real_fields,
                "curl_preview_masked": masked_curl,
                "curl_preview_real": real_curl,
            })

        return {
            "ok": True,
            "provider": "gacos",
            "portal_url": cloned_payload.get("portal_url"),
            "submit_endpoint": cloned_payload.get("submit_endpoint"),
            "batches": batches_preview,
        }

    def submit_webform(self, payload: Any, email: str) -> dict:
        """Endpoint reserved for real submission. Always returns disabled message."""
        self.validate_submission(payload, email)
        return {
            "ok": False,
            "error": "真实提交：第一阶段未启用",
            "code": "GUI003",
        }
