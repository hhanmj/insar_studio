from __future__ import annotations

import json
import os
from pathlib import Path

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import CredentialError
from insar_prep.desktop.api import Api
from insar_prep.providers.asf.downloader import DownloadOutcome, DownloadResult


def test_local_admin_options_include_city_and_county() -> None:
    api = Api()

    options = api.get_admin_options("内蒙古自治区", "包头市")

    assert options["ok"] is True
    assert "包头市" in options["cities"]
    assert "昆都仑区" in options["districts"]
    assert "达尔罕茂明安联合旗" in options["districts"]


def test_aoi_bind_auto_creates_default_region(tmp_path: Path, monkeypatch) -> None:
    api = Api()
    api._state.workspace = None
    api._state.current_project_id = None
    api._state.current_region_id = None
    api._state_path = tmp_path / "desktop_state.json"
    default_root = tmp_path / "projects"
    monkeypatch.setattr(api, "_default_workspace_root", lambda: default_root)

    result = api.set_region_aoi_bbox(109.0, 110.0, 40.0, 41.0)

    assert result["ok"] is True
    assert result["region_name"] == "default_area"
    context = api.get_context()
    assert context["region"]["has_aoi"] is True
    assert context["region"]["bbox"]["west"] == 109.0
    assert not default_root.exists()


def test_start_asf_download_requires_credentials_before_queue(
    tmp_path: Path, monkeypatch
) -> None:
    api = Api()
    api._state_path = tmp_path / "desktop_state.json"
    imported = api.import_scenes_text(
        "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C"
    )
    assert imported["ok"] is True

    import insar_prep.providers.asf.credentials as credentials

    def missing_credentials(_source):
        raise CredentialError("missing Earthdata credentials", code=ErrorCode.DL004)

    monkeypatch.setattr(credentials, "resolve_credentials", missing_credentials)

    result = api.start_asf_download(str(tmp_path), "auto")

    assert result["ok"] is False
    assert result["code"] == "DL004"
    assert "Earthdata" in result["error"]
    assert api.get_download_status()["state"] == "idle"


def test_start_asf_download_preflight_failure_blocks_queue(
    tmp_path: Path, monkeypatch
) -> None:
    api = Api()
    api._state_path = tmp_path / "desktop_state.json"
    imported = api.import_scenes_text(
        "https://datapool.asf.alaska.edu/SLC/SA/"
        "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C.zip"
    )
    assert imported["ok"] is True

    import insar_prep.providers.asf.credentials as credentials
    import insar_prep.providers.asf.downloader as downloader

    monkeypatch.setattr(credentials, "resolve_credentials", lambda _source: object())

    class FailingDownloader:
        def __init__(self, **_kwargs) -> None:
            pass

        def verify(self, _request) -> DownloadResult:
            return DownloadResult(
                scene_id="S1A",
                outcome=DownloadOutcome.FAILED,
                message="TLS failed",
                error_code="DL005",
            )

    monkeypatch.setattr(downloader, "RealAsfDownloader", FailingDownloader)

    result = api.start_asf_download(str(tmp_path), "auto")

    assert result["ok"] is False
    assert result["code"] == "DL005"
    assert "预检失败" in result["error"]
    assert api.get_download_status()["state"] == "idle"


def test_start_asf_download_preflight_passes_network_settings(
    tmp_path: Path, monkeypatch
) -> None:
    api = Api()
    api._state_path = tmp_path / "desktop_state.json"
    imported = api.import_scenes_text(
        "https://datapool.asf.alaska.edu/SLC/SA/"
        "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C.zip"
    )
    assert imported["ok"] is True
    api._network_settings.update(
        {"proxy_enabled": True, "proxy_url": "127.0.0.1:7897", "asf_ssl_verify": False}
    )

    import insar_prep.providers.asf.credentials as credentials
    import insar_prep.providers.asf.downloader as downloader

    class Resolved:
        username = "fake-user"
        password = "fake-pass"
        use_netrc = False

    monkeypatch.setattr(credentials, "resolve_credentials", lambda _source: Resolved())
    init_kwargs: list[dict] = []

    class PassingDownloader:
        def __init__(self, **kwargs) -> None:
            init_kwargs.append(kwargs)

        def verify(self, request) -> DownloadResult:
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.VERIFIED,
                bytes_written=1,
                message="ok",
            )

    monkeypatch.setattr(downloader, "RealAsfDownloader", PassingDownloader)

    class FakeJob:
        def start(self, *_args, **kwargs):
            init_kwargs.append({"job": kwargs})
            return {"ok": True}

    api._asf_download = FakeJob()
    result = api.start_asf_download(str(tmp_path), "auto")

    assert result == {"ok": True}
    assert init_kwargs[0]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[0]["ssl_verify"] is False
    assert init_kwargs[0]["trust_env"] is True
    assert init_kwargs[1]["job"]["proxy_url"] == "http://127.0.0.1:7897"
    assert init_kwargs[1]["job"]["ssl_verify"] is False
    assert init_kwargs[1]["job"]["trust_env"] is True


def test_start_asf_download_falls_back_to_relaxed_asf_tls(
    tmp_path: Path, monkeypatch
) -> None:
    api = Api()
    api._state_path = tmp_path / "desktop_state.json"
    api._network_settings.update(
        {"proxy_enabled": False, "proxy_url": "", "asf_ssl_verify": True}
    )
    imported = api.import_scenes_text(
        "https://datapool.asf.alaska.edu/SLC/SA/"
        "S1A_IW_SLC__1SDV_20240312T223805_20240312T223832_052914_0667A5_8F5C.zip"
    )
    assert imported["ok"] is True

    import insar_prep.providers.asf.credentials as credentials
    import insar_prep.providers.asf.downloader as downloader

    class Resolved:
        username = "fake-user"
        password = "fake-pass"
        use_netrc = False

    monkeypatch.setattr(credentials, "resolve_credentials", lambda _source: Resolved())
    init_kwargs: list[dict] = []

    class SequencedDownloader:
        def __init__(self, **kwargs) -> None:
            init_kwargs.append(kwargs)

        def verify(self, request) -> DownloadResult:
            if init_kwargs[-1]["ssl_verify"]:
                return DownloadResult(
                    scene_id=request.scene_id,
                    outcome=DownloadOutcome.FAILED,
                    message="certificate verify failed",
                    error_code="DL005",
                )
            return DownloadResult(
                scene_id=request.scene_id,
                outcome=DownloadOutcome.VERIFIED,
                bytes_written=1,
                message="ok",
            )

    monkeypatch.setattr(downloader, "RealAsfDownloader", SequencedDownloader)

    class FakeJob:
        def start(self, *_args, **kwargs):
            init_kwargs.append({"job": kwargs})
            return {"ok": True}

    api._asf_download = FakeJob()
    result = api.start_asf_download(str(tmp_path), "auto")

    assert result == {"ok": True}
    assert init_kwargs[0]["ssl_verify"] is True
    assert init_kwargs[1]["ssl_verify"] is False
    assert init_kwargs[-1]["job"]["ssl_verify"] is False
    assert init_kwargs[-1]["job"]["proxy_url"] == ""
    assert init_kwargs[-1]["job"]["trust_env"] is False


def test_desktop_clean_start_has_no_prefilled_state(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "desktop_state.json"
    monkeypatch.setattr(Api, "_desktop_state_path", staticmethod(lambda: state_path))

    api = Api()

    context = api.get_context()
    assert context["workspace"] is None
    assert context["project"] is None
    assert context["region"] is None
    assert api.list_scenes()["scenes"] == []
    network = api.get_network_settings()
    assert network["proxy_url"] == ""
    assert network["cache_enabled"] is True
    assert network["cache_dir"].replace("/", "\\").endswith("\\InSAR\\insar_assistant_cache")
    assert not state_path.exists()


def test_desktop_selftest_state_is_discarded(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "desktop_state.json"
    state_path.write_text(
        json.dumps(
            {
                "workspace": {
                    "global_settings": {"display_name": "selftest"},
                    "projects": [
                        {
                            "project_name": "p",
                            "regions": [
                                {
                                    "region_name": "r",
                                    "scenes": [
                                        {
                                            "scene_id": (
                                                "S1A_IW_SLC__1SDV_20240312T223805_"
                                                "20240312T223832_052914_0667A5_8F5C"
                                            )
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Api, "_desktop_state_path", staticmethod(lambda: state_path))

    api = Api()

    assert api.get_context()["workspace"] is None
    assert not state_path.exists()


def test_legacy_blank_default_state_is_discarded(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "desktop_state.json"
    state_path.write_text(
        json.dumps(
            {
                "workspace": None,
                "current_project_id": None,
                "current_region_id": None,
                "dem_dataset": "AW3D30_ELLIPSOIDAL",
                "network_settings": {
                    "proxy_enabled": False,
                    "proxy_url": "http://127.0.0.1:10808",
                    "cache_enabled": True,
                    "cache_dir": str(tmp_path / "InSAR Assistant" / "cache"),
                    "cache_limit_mb": 5120,
                    "tianditu_token": "",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Api, "_desktop_state_path", staticmethod(lambda: state_path))

    api = Api()

    assert api.get_context()["workspace"] is None
    assert api.get_network_settings()["proxy_url"] == ""
    assert api.get_network_settings()["cache_dir"].replace("/", "\\").endswith("\\InSAR\\insar_assistant_cache")
    assert not state_path.exists()


def test_proxy_settings_are_explicitly_applied_or_cleared(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "desktop_state.json"
    monkeypatch.setattr(Api, "_desktop_state_path", staticmethod(lambda: state_path))
    monkeypatch.setenv("HTTP_PROXY", "http://old-proxy:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://old-proxy:8080")

    api = Api()
    saved = api.save_network_settings({"proxy_enabled": True, "proxy_url": "127.0.0.1:7890"})

    assert saved["ok"] is True
    assert saved["proxy_url"] == "http://127.0.0.1:7890"
    assert saved["asf_ssl_verify"] is True
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7890"

    saved = api.save_network_settings(
        {"proxy_enabled": False, "proxy_url": "", "asf_ssl_verify": False}
    )

    assert saved["ok"] is True
    assert saved["asf_ssl_verify"] is False
    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ


def test_proxy_settings_auto_detect_system_proxy_when_blank(
    tmp_path: Path, monkeypatch
) -> None:
    state_path = tmp_path / "desktop_state.json"
    monkeypatch.setattr(Api, "_desktop_state_path", staticmethod(lambda: state_path))
    monkeypatch.setattr(
        "urllib.request.getproxies",
        lambda: {"https": "127.0.0.1:7897"},
    )

    api = Api()
    saved = api.save_network_settings({"proxy_enabled": True, "proxy_url": ""})

    assert saved["ok"] is True
    assert saved["proxy_enabled"] is True
    assert saved["proxy_url"] == "http://127.0.0.1:7897"
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7897"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7897"
