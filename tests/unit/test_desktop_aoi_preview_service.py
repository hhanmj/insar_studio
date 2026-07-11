from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from insar_prep.desktop.aoi_preview_service import (
    AoiPreviewDesktopService,
    _rough_geometry_area_km2,
    _selected_geojson_from_feature_collection,
)

_KML_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>AOI_Test</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              110.1,30.8,0 110.6,30.8,0 110.6,31.2,0 110.1,31.2,0 110.1,30.8,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


@pytest.fixture
def service_callbacks():
    """Return mock callbacks to construct the service in isolation."""
    region = MagicMock()
    region.region_id = "reg_123"
    region.region_name = "default area"
    region.region_root = "/tmp/region"

    get_state = MagicMock()
    get_state.return_value.current_region.return_value = region
    get_state.return_value.set_current_region_aoi.return_value = region

    save_state = MagicMock()
    ensure_region = MagicMock()
    log_action = MagicMock()
    return get_state, save_state, ensure_region, log_action


def test_aoi_preview_service_preview_content(service_callbacks) -> None:
    get_state, save_state, ensure_region, log_action = service_callbacks
    service = AoiPreviewDesktopService(get_state, save_state, ensure_region, log_action)

    res = service.preview_aoi_file_content("test.kml", _KML_TEXT)
    assert res["ok"] is True
    assert res["file_name"] == "test.kml"
    assert res["total_features"] == 1
    assert "AOI_Test" in [f["name"] for f in res["features"]]
    assert res["display_field"] == "name"


def test_aoi_preview_service_set_and_clear_geojson(service_callbacks) -> None:
    get_state, save_state, ensure_region, log_action = service_callbacks
    service = AoiPreviewDesktopService(get_state, save_state, ensure_region, log_action)

    geojson = {
        "type": "Feature",
        "properties": {"name": "manual_drawn"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[110.1, 30.8], [110.6, 30.8], [110.6, 31.2], [110.1, 31.2], [110.1, 30.8]]
            ],
        },
    }

    # Mock file writing inside `_write_region_aoi_geojson`
    with patch("insar_prep.desktop.aoi_preview_service._write_region_aoi_geojson") as mock_write:
        mock_write.return_value = Path("/tmp/aoi.geojson")
        res = service.set_region_aoi_geojson(geojson)
        assert res["ok"] is True
        assert res["region_name"] == "default area"
        save_state.assert_called_once()
        log_action.assert_called_once()

    # 清除 AOI
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.unlink") as mock_unlink,
    ):
        clear_res = service.clear_region_aoi()
        assert clear_res["ok"] is True
        assert clear_res["cleared_aoi"] is True
        mock_unlink.assert_called_once()


def test_rough_geometry_area_km2_exceptions() -> None:
    # 正常几何对象
    mock_geom = MagicMock()
    mock_geom.bounds = (110.0, 30.0, 110.5, 30.5)
    mock_geom.area = 0.25
    area = _rough_geometry_area_km2(mock_geom)
    assert area > 0.0

    # 缺少 bounds / area 字段的非几何对象防吞拦截
    assert _rough_geometry_area_km2(None) == 0.0
    assert _rough_geometry_area_km2({}) == 0.0


def test_preview_aoi_file_bundle_success(service_callbacks) -> None:
    get_state, save_state, ensure_region, log_action = service_callbacks
    service = AoiPreviewDesktopService(get_state, save_state, ensure_region, log_action)

    # 模拟完整的 shp bundle base64 拖入
    files = [
        {"name": "zone.shp", "base64": base64.b64encode(b"shp_data").decode()},
        {"name": "zone.dbf", "base64": base64.b64encode(b"dbf_data").decode()},
        {"name": "zone.shx", "base64": base64.b64encode(b"shx_data").decode()},
    ]

    mock_features = [
        {
            "properties": {"name": "Feature 1"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[110.1, 30.8], [110.6, 30.8], [110.6, 31.2], [110.1, 31.2], [110.1, 30.8]]
                ],
            },
        }
    ]
    with patch(
        "insar_prep.desktop.aoi_preview_service._read_aoi_vector_features",
        return_value=mock_features,
    ) as mock_read:
        res = service.preview_aoi_file_bundle(files)
        assert res["ok"] is True
        assert res["file_name"] == "zone.shp"
        assert len(res["features"]) == 1

        # 检查是否往临时目录写入了配套文件
        written_path = mock_read.call_args[0][0]
        assert written_path.name == "zone.shp"


def test_preview_aoi_file_bundle_requires_shp_entry(service_callbacks) -> None:
    get_state, save_state, ensure_region, log_action = service_callbacks
    service = AoiPreviewDesktopService(get_state, save_state, ensure_region, log_action)

    # 配套文件不能脱离 .shp 单独识别。
    files = [
        {"name": "zone.dbf", "base64": base64.b64encode(b"dbf_data").decode()},
        {"name": "zone.shx", "base64": base64.b64encode(b"shx_data").decode()},
    ]
    res = service.preview_aoi_file_bundle(files)
    assert res["ok"] is False
    assert ".shp" in res["error"]


def test_selected_geojson_from_feature_collection() -> None:
    geojson = {
        "type": "FeatureCollection",
        "properties": {"source_file": "my_bound.kml"},
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Placemark 1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[110.1, 30.8], [110.6, 30.8], [110.6, 31.2], [110.1, 31.2], [110.1, 30.8]]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "Placemark 2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[110.2, 30.8], [110.7, 30.8], [110.7, 31.2], [110.2, 31.2], [110.2, 30.8]]
                    ],
                },
            },
        ],
    }

    # 测试 split 模式与 merge 模式下的筛选
    res_split = _selected_geojson_from_feature_collection(
        geojson, feature_ids=[0], download_mode="split"
    )
    assert res_split["properties"]["download_mode"] == "split"
    assert len(res_split["features"]) == 1
    assert res_split["features"][0]["properties"]["_insar_feature_name"] == "Placemark 1"
