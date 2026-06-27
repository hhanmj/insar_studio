from __future__ import annotations

import pytest
import requests

from insar_prep.core.exceptions import InputValidationError
from insar_prep.providers.asf import metadata


def test_asf_ssl_error_is_translated_without_raw_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args, **kwargs):
        raise requests.exceptions.SSLError(
            "HTTPSConnectionPool(host='api.daac.asf.alaska.edu', port=443): "
            "SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING]')"
        )

    monkeypatch.setattr(metadata, "time", type("T", (), {"sleep": staticmethod(lambda _: None)}))
    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(InputValidationError) as excinfo:
        metadata.search_scenes_from_asf(max_results=1)

    message = str(excinfo.value)
    assert "TLS/SSL 连接被中断" in message
    assert "HTTPSConnectionPool" not in message
    assert "api.daac.asf.alaska.edu" not in message
    assert "SSLEOFError" not in message


def test_asf_transient_http_uses_get_and_post_before_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Response504:
        status_code = 504

        def raise_for_status(self) -> None:
            error = requests.exceptions.HTTPError("gateway timeout")
            error.response = self
            raise error

    def fake_get(*args, **kwargs):
        calls.append("GET")
        return Response504()

    def fake_post(*args, **kwargs):
        calls.append("POST")
        return Response504()

    monkeypatch.setattr(metadata, "time", type("T", (), {"sleep": staticmethod(lambda _: None)}))
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(InputValidationError) as excinfo:
        metadata.search_scenes_from_asf(max_results=1)

    assert calls[:2] == ["GET", "POST"]
    assert "已尝试 GET 与 POST" in str(excinfo.value)


def test_cmr_entry_to_scene_adds_polygon_bbox_and_download_url() -> None:
    entry = {
        "producer_granule_id": "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
        "granule_size": "1024",
        "orbit_calculated_spatial_domains": [{"orbit_number": "52000"}],
        "polygons": [["30.0 110.0 30.0 111.0 31.0 111.0 31.0 110.0 30.0 110.0"]],
        "links": [
            {
                "rel": "http://esipfed.org/ns/fedsearch/1.1/data#",
                "title": "This link provides direct download access to the granule.",
                "href": "https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234.zip",
            }
        ],
    }

    scene = metadata._cmr_entry_to_scene(entry)

    assert scene is not None
    assert scene.footprint_bbox is not None
    assert scene.footprint_bbox.west == 110.0
    assert scene.footprint_bbox.east == 111.0
    assert scene.footprint_bbox.south == 30.0
    assert scene.footprint_bbox.north == 31.0
    assert scene.footprint_geojson["type"] == "Polygon"
    assert scene.url and scene.url.startswith("https://datapool.asf.alaska.edu/")


def test_asf_search_passes_grd_beam_and_polarization(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {
            "features": [
                {
                    "properties": {
                        "sceneName": "S1A_IW_GRDH_1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
                    }
                }
            ]
        }

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(
        product_type="GRD",
        beam_mode="IW",
        polarization="DV",
        max_results=1,
    )

    assert captured["processingLevel"] == "GRD"
    assert captured["beamMode"] == "IW"
    assert captured["polarization"] == "VV+VH"
    assert len(scenes) == 1
    assert str(scenes[0].product_type) == "GRD"


def test_grd_enrichment_query_ids_do_not_force_slc_suffix() -> None:
    scene = metadata.parse_scene_name(
        "S1A_IW_GRDH_1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
    )

    query_ids = metadata._metadata_query_ids([scene])

    assert scene.scene_id in query_ids
    assert f"{scene.scene_id}-GRD" in query_ids
    assert f"{scene.scene_id}-SLC" not in query_ids
