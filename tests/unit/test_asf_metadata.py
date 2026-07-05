from __future__ import annotations

import pytest
import requests

from insar_prep.core.exceptions import InputValidationError
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.enums import OrbitDirection
from insar_prep.core.models import BBox
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


def test_asf_search_multi_filters_are_applied_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {
            "features": [
                {
                    "properties": {
                        "sceneName": "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
                        "flightDirection": "ASCENDING",
                    }
                },
                {
                    "properties": {
                        "sceneName": "S1A_EW_SLC__1SDH_20240113T100000_20240113T100027_052100_064DEF_5678",
                        "flightDirection": "DESCENDING",
                    }
                },
                {
                    "properties": {
                        "sceneName": "S1A_SM_SLC__1SSV_20240125T100000_20240125T100027_052200_064AAA_9999",
                        "flightDirection": "ASCENDING",
                    }
                },
            ]
        }

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(
        product_type="SLC",
        beam_mode="IW,EW",
        polarization="DV,DH",
        orbit_direction="ASCENDING,DESCENDING",
        max_results=10,
    )

    assert "beamMode" not in captured
    assert "polarization" not in captured
    assert "flightDirection" not in captured
    assert [scene.beam_mode.value for scene in scenes] == ["IW", "EW"]
    assert [scene.polarization.value for scene in scenes] == ["DV", "DH"]


def test_grd_enrichment_query_ids_do_not_force_slc_suffix() -> None:
    scene = metadata.parse_scene_name(
        "S1A_IW_GRDH_1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
    )

    query_ids = metadata._metadata_query_ids([scene])

    assert scene.scene_id in query_ids
    assert f"{scene.scene_id}-GRD" in query_ids
    assert f"{scene.scene_id}-SLC" not in query_ids


def test_asf_search_overfetches_for_aoi_and_filters_footprints(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}
    aoi = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }

    def feature(scene_name: str, west: float, south: float, east: float, north: float) -> dict:
        return {
            "type": "Feature",
            "properties": {"sceneName": scene_name},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[west, south], [east, south], [east, north], [west, north], [west, south]]
                ],
            },
        }

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {
            "features": [
                feature(
                    "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
                    0.2,
                    0.2,
                    0.8,
                    0.8,
                ),
                feature(
                    "S1A_IW_SLC__1SDV_20240113T100000_20240113T100027_052175_064DEF_5678",
                    2.0,
                    2.0,
                    3.0,
                    3.0,
                ),
            ]
        }

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(
        bbox=BBox(west=-10, east=10, south=-10, north=10),
        aoi_geojson=aoi,
        product_type="SLC",
        beam_mode="IW",
        max_results=10,
    )

    assert captured["intersectsWith"].startswith("POLYGON")
    assert "-10" not in captured["intersectsWith"]
    assert captured["maxResults"] == "60"
    assert [scene.scene_id for scene in scenes] == [
        "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
    ]


def test_asf_search_without_aoi_uses_requested_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(product_type="SLC", beam_mode="IW", max_results=30)

    assert scenes == []
    assert captured["maxResults"] == "30"


def test_asf_search_accepts_requested_limit_above_500(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(product_type="SLC", beam_mode="IW", max_results=600)

    assert scenes == []
    assert captured["maxResults"] == "600"


def test_asf_search_keeps_large_explicit_limit_with_aoi(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}
    aoi = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    scenes = metadata.search_scenes_from_asf(
        bbox=BBox(west=-10, east=10, south=-10, north=10),
        aoi_geojson=aoi,
        product_type="SLC",
        beam_mode="IW",
        max_results=1900,
    )

    assert scenes == []
    assert captured["maxResults"] == "1900"


def test_asf_search_rejects_invalid_date_text() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        metadata.search_scenes_from_asf(product_type="SLC", beam_mode="IW", end="1900", max_results=1)

    assert "日期格式" in str(excinfo.value)


def test_asf_search_empty_limit_uses_total_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_count(params):
        assert params["processingLevel"] == "SLC"
        return 640

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_count", fake_get_asf_count)
    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    stats: dict[str, object] = {}
    scenes = metadata.search_scenes_from_asf(
        product_type="SLC",
        beam_mode="IW",
        max_results=None,
        stats=stats,
    )

    assert scenes == []
    assert captured["maxResults"] == "640"
    assert stats["requested_limit"] == 640


def test_asf_search_empty_limit_falls_back_to_conservative_limit_without_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_get_asf_geojson(params):
        captured.update(params)
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_count", lambda _params: None)
    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    stats: dict[str, object] = {}
    scenes = metadata.search_scenes_from_asf(
        product_type="SLC",
        beam_mode="IW",
        max_results=None,
        stats=stats,
        progress=lambda *_args: None,
    )

    assert scenes == []
    assert captured["maxResults"] == "500"
    assert stats["requested_limit"] == 500


def test_cmr_fallback_enriches_before_direction_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    base_scene = metadata.parse_scene_name(
        "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234"
    )

    def fake_get_asf_geojson(_params):
        raise InputValidationError("ASF timeout", code="ASF002")

    def fake_cmr_search(**_kwargs):
        return [base_scene]

    def fake_enrich(scenes, *, progress=None, cancelled=None):
        return [
            scenes[0].model_copy(
                update={
                    "orbit_direction": OrbitDirection.ASCENDING,
                    "relative_orbit": 88,
                    "path": 88,
                    "frame": 456,
                }
            )
        ]

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)
    monkeypatch.setattr(metadata, "_search_scenes_from_cmr", fake_cmr_search)
    monkeypatch.setattr(metadata, "enrich_scenes_from_asf_search", fake_enrich)

    scenes = metadata.search_scenes_from_asf(
        product_type="SLC",
        beam_mode="IW",
        orbit_direction="ASCENDING",
        max_results=1,
    )

    assert len(scenes) == 1
    assert scenes[0].orbit_direction == OrbitDirection.ASCENDING
    assert scenes[0].relative_orbit == 88
    assert scenes[0].frame == 456


def test_asf_search_can_be_cancelled_before_network_request(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_get_asf_geojson(_params):
        nonlocal called
        called = True
        return {"features": []}

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    with pytest.raises(InputValidationError) as excinfo:
        metadata.search_scenes_from_asf(
            product_type="SLC",
            beam_mode="IW",
            max_results=1,
            cancelled=lambda: True,
        )

    assert excinfo.value.code == ErrorCode.DL001
    assert called is False


def test_asf_search_large_explicit_limit_does_not_auto_fallback_to_cmr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cmr_called = False

    def fake_get_asf_geojson(_params):
        raise InputValidationError("ASF timeout", code=ErrorCode.ASF002)

    def fake_cmr_search(**_kwargs):
        nonlocal cmr_called
        cmr_called = True
        return []

    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)
    monkeypatch.setattr(metadata, "_search_scenes_from_cmr", fake_cmr_search)

    with pytest.raises(InputValidationError) as excinfo:
        metadata.search_scenes_from_asf(
            product_type="SLC",
            beam_mode="IW",
            max_results=2500,
            allow_cmr_fallback=False,
        )

    assert excinfo.value.code == ErrorCode.ASF002
    assert cmr_called is False


def test_asf_search_reports_total_count_when_stats_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def fake_get_asf_count(params):
        assert params["processingLevel"] == "SLC"
        assert params["maxResults"] == "10"
        return 123

    def fake_get_asf_geojson(params):
        return {
            "features": [
                {
                    "properties": {
                        "sceneName": "S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234",
                    }
                }
            ]
        }

    monkeypatch.setattr(metadata, "_get_asf_count", fake_get_asf_count)
    monkeypatch.setattr(metadata, "_get_asf_geojson", fake_get_asf_geojson)

    stats: dict[str, object] = {}
    scenes = metadata.search_scenes_from_asf(
        product_type="SLC",
        beam_mode="IW",
        max_results=10,
        stats=stats,
        progress=lambda _done, _total, msg: messages.append(msg),
    )

    assert len(scenes) == 1
    assert stats["total_count"] == 123
    assert stats["requested_limit"] == 10
    assert stats["returned_count"] == 1
    assert "匹配总量 123 景" in messages[0]
