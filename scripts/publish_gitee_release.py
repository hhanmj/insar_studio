from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://gitee.com/api/v5"


class GiteeError(RuntimeError):
    pass


def _read_json_response(response: Any) -> Any:
    body = response.read()
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return body.decode("utf-8", errors="replace")


def _request_json(
    method: str,
    path: str,
    *,
    token: str,
    data: dict[str, Any] | None = None,
    timeout: int = 60,
    allow_404: bool = False,
) -> Any:
    query = urllib.parse.urlencode({"access_token": token})
    url = f"{API_BASE}{path}?{query}"
    body: bytes | None = None
    headers = {"User-Agent": "InSAR-Studio-Release"}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return _read_json_response(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if allow_404 and exc.code == 404:
            return None
        raise GiteeError(f"Gitee API {method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise GiteeError(f"Gitee API {method} {path} failed: {exc}") from exc


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----InSARStudioGiteeReleaseBoundary7MA4YWxkTrZu0gW"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), boundary


def _upload_file(path: str, *, token: str, release_id: str, file_path: Path) -> Any:
    query = urllib.parse.urlencode({"access_token": token})
    url = f"{API_BASE}{path}?{query}"
    body, boundary = _multipart_body({"access_token": token}, "file", file_path)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "InSAR-Studio-Release",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
            return _read_json_response(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GiteeError(
            f"Gitee API POST upload for release {release_id} failed: HTTP {exc.code}: {detail}"
        ) from exc
    except OSError as exc:
        raise GiteeError(f"Gitee API POST upload for release {release_id} failed: {exc}") from exc


def _release_path(owner: str, repo: str, suffix: str) -> str:
    return f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/releases{suffix}"


def _get_release(owner: str, repo: str, tag: str, *, token: str) -> dict[str, Any] | None:
    payload = _request_json(
        "GET",
        _release_path(owner, repo, f"/tags/{urllib.parse.quote(tag)}"),
        token=token,
        allow_404=True,
    )
    return payload if isinstance(payload, dict) else None


def _save_release(
    owner: str,
    repo: str,
    *,
    token: str,
    tag: str,
    target: str,
    name: str,
    body: str,
) -> dict[str, Any]:
    existing = _get_release(owner, repo, tag, token=token)
    fields = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "prerelease": "false",
        "draft": "false",
    }
    if target:
        fields["target_commitish"] = target
    if existing:
        release_id = str(existing.get("id") or "")
        if not release_id:
            raise GiteeError("Existing Gitee release did not include an id.")
        payload = _request_json(
            "PATCH",
            _release_path(owner, repo, f"/{urllib.parse.quote(release_id)}"),
            token=token,
            data=fields,
        )
    else:
        payload = _request_json(
            "POST",
            _release_path(owner, repo, ""),
            token=token,
            data=fields,
        )
    if not isinstance(payload, dict):
        raise GiteeError(f"Unexpected Gitee release response: {payload!r}")
    return payload


def _iter_attachments(release: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("attach_files", "attachments", "assets"):
        value = release.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _delete_matching_attachments(
    owner: str,
    repo: str,
    *,
    token: str,
    release_id: str,
    asset_name: str,
    release: dict[str, Any],
) -> None:
    for item in _iter_attachments(release):
        if str(item.get("name") or "") != asset_name:
            continue
        attachment_id = str(item.get("id") or item.get("attach_file_id") or "")
        if not attachment_id:
            continue
        _request_json(
            "DELETE",
            _release_path(
                owner,
                repo,
                f"/{urllib.parse.quote(release_id)}/attach_files/{urllib.parse.quote(attachment_id)}",
            ),
            token=token,
        )


def _walk_json(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_json(child))
    return found


def _download_url_from_payload(payload: Any, asset_name: str) -> str:
    for item in _walk_json(payload):
        name = str(item.get("name") or item.get("filename") or "")
        if name and name != asset_name:
            continue
        for key in ("browser_download_url", "download_url", "url"):
            url = str(item.get(key) or "").strip()
            if not url.startswith("https://"):
                continue
            parsed_name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
            if not parsed_name or parsed_name == asset_name:
                return url
    return ""


def _write_outputs(mirror_url: str, marker_output: Path | None) -> None:
    if marker_output is not None:
        marker_output.parent.mkdir(parents=True, exist_ok=True)
        marker_output.write_text(
            f"<!-- insar-update-mirror: {mirror_url} -->\n",
            encoding="utf-8",
        )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"mirror_url={mirror_url}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/update a Gitee release mirror.")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--name", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--marker-output", default="")
    args = parser.parse_args()

    token = os.environ.get("GITEE_TOKEN", "").strip()
    if not token:
        raise GiteeError("GITEE_TOKEN is required.")

    asset = Path(args.asset)
    if not asset.is_file():
        raise GiteeError(f"Release asset does not exist: {asset}")
    body = Path(args.body_file).read_text(encoding="utf-8")

    release = _save_release(
        args.owner,
        args.repo,
        token=token,
        tag=args.tag,
        target=args.target,
        name=args.name,
        body=body,
    )
    release_id = str(release.get("id") or "")
    if not release_id:
        raise GiteeError("Gitee release response did not include an id.")

    _delete_matching_attachments(
        args.owner,
        args.repo,
        token=token,
        release_id=release_id,
        asset_name=asset.name,
        release=release,
    )
    upload = _upload_file(
        _release_path(args.owner, args.repo, f"/{urllib.parse.quote(release_id)}/attach_files"),
        token=token,
        release_id=release_id,
        file_path=asset,
    )
    mirror_url = _download_url_from_payload(upload, asset.name)
    if not mirror_url:
        refreshed = _get_release(args.owner, args.repo, args.tag, token=token)
        mirror_url = _download_url_from_payload(refreshed, asset.name)
    if not mirror_url:
        raise GiteeError("Could not determine a direct HTTPS download URL from Gitee.")

    marker_output = Path(args.marker_output) if args.marker_output else None
    _write_outputs(mirror_url, marker_output)
    print(f"Gitee mirror ready: {mirror_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GiteeError as exc:
        print(f"[publish_gitee_release] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
