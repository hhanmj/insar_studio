from __future__ import annotations

from insar_prep.desktop.api import Api


def _asf_test_scenes(count: int):
    from insar_prep.providers.asf.metadata import parse_scene_name

    dates = ["20240101", "20240113", "20240125", "20240206", "20240218", "20240301"]
    scenes = []
    for idx in range(count):
        day = dates[idx % len(dates)]
        orbit = 52000 + idx
        scenes.append(
            parse_scene_name(
                f"S1A_IW_SLC__1SDV_{day}T100000_{day}T100027_{orbit:06d}_064ABC_{idx:04d}"
            )
        )
    return scenes


def test_desktop_asf_search_empty_limit_requests_all_available(tmp_path, monkeypatch) -> None:
    import insar_prep.providers.asf.metadata as metadata

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_search_scenes_from_asf(**kwargs):
        captured["max_results"] = kwargs.get("max_results")
        stats = kwargs.get("stats")
        if isinstance(stats, dict):
            stats.update(
                {
                    "requested_limit": 640,
                    "query_limit": 640,
                    "total_count": 640,
                    "returned_count": 0,
                    "source": "ASF",
                }
            )
        return []

    monkeypatch.setattr(metadata, "search_scenes_from_asf", fake_search_scenes_from_asf)

    result = Api().search_asf_scenes({"max_results": ""})

    assert result["ok"] is True
    assert captured["max_results"] is None
    assert result["search"]["requested_limit"] == 640


def test_desktop_asf_search_large_explicit_limit_allows_cmr_fallback(tmp_path, monkeypatch) -> None:
    import insar_prep.providers.asf.metadata as metadata

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_search_scenes_from_asf(**kwargs):
        captured["max_results"] = kwargs.get("max_results")
        captured["allow_cmr_fallback"] = kwargs.get("allow_cmr_fallback")
        captured["cancelled"] = kwargs.get("cancelled")
        stats = kwargs.get("stats")
        if isinstance(stats, dict):
            stats.update(
                {
                    "requested_limit": kwargs.get("max_results"),
                    "query_limit": kwargs.get("max_results"),
                    "total_count": 5000,
                    "returned_count": 0,
                    "source": "ASF",
                }
            )
        return []

    monkeypatch.setattr(metadata, "search_scenes_from_asf", fake_search_scenes_from_asf)

    result = Api().search_asf_scenes({"max_results": "2500"})

    assert result["ok"] is True
    assert captured["max_results"] == 2500
    assert captured["allow_cmr_fallback"] is True
    assert callable(captured["cancelled"])
    assert captured["cancelled"]() is False


def test_desktop_cancel_asf_search_reports_cancelled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    api = Api()

    result = api.cancel_asf_search()
    status = api.get_metadata_status()

    assert result == {"ok": True, "cancelled": True}
    assert status["state"] == "cancelled"


def test_desktop_asf_search_reuses_cached_superset(tmp_path, monkeypatch) -> None:
    import insar_prep.providers.asf.metadata as metadata

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls: list[int | None] = []
    scenes = _asf_test_scenes(5)

    def fake_search_scenes_from_asf(**kwargs):
        limit = kwargs.get("max_results")
        calls.append(limit)
        stats = kwargs.get("stats")
        if isinstance(stats, dict):
            stats.update(
                {
                    "requested_limit": limit,
                    "query_limit": limit,
                    "total_count": 10,
                    "returned_count": min(int(limit or len(scenes)), len(scenes)),
                    "source": "ASF",
                }
            )
        return scenes[: int(limit or len(scenes))]

    monkeypatch.setattr(metadata, "search_scenes_from_asf", fake_search_scenes_from_asf)

    api = Api()
    first = api.search_asf_scenes({"max_results": "5", "product_type": "SLC", "beam_mode": "IW"})
    second = api.search_asf_scenes({"max_results": "3", "product_type": "SLC", "beam_mode": "IW"})

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert len(second["scenes"]) == 3
    assert calls == [5]


def test_desktop_asf_search_reuses_broad_cache_for_narrow_frame(tmp_path, monkeypatch) -> None:
    import insar_prep.providers.asf.metadata as metadata

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls: list[int | None] = []
    scenes = [
        scene.model_copy(update={"frame": 460 + idx, "relative_orbit": 11, "path": 11})
        for idx, scene in enumerate(_asf_test_scenes(5))
    ]

    def fake_search_scenes_from_asf(**kwargs):
        limit = kwargs.get("max_results")
        calls.append(limit)
        stats = kwargs.get("stats")
        if isinstance(stats, dict):
            stats.update(
                {
                    "requested_limit": limit or len(scenes),
                    "query_limit": limit or len(scenes),
                    "total_count": len(scenes),
                    "returned_count": len(scenes),
                    "source": "ASF",
                }
            )
        return scenes

    monkeypatch.setattr(metadata, "search_scenes_from_asf", fake_search_scenes_from_asf)

    api = Api()
    first = api.search_asf_scenes({"max_results": "", "product_type": "SLC", "beam_mode": "IW"})
    second = api.search_asf_scenes(
        {"max_results": "1", "product_type": "SLC", "beam_mode": "IW", "frame_start": "462", "frame_end": "462"}
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["cache"]["hit"] is True
    assert len(second["scenes"]) == 1
    assert second["scenes"][0]["frame"] == 462
    assert calls == [None]


def test_desktop_asf_search_reuses_bbox_cache_when_aoi_wrapper_changes(tmp_path, monkeypatch) -> None:
    import insar_prep.providers.asf.metadata as metadata

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls: list[int | None] = []
    scenes = _asf_test_scenes(3)
    bbox = {"west": 100.0, "east": 101.0, "south": 30.0, "north": 31.0, "crs": "EPSG:4326"}
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [100.0, 30.0],
            [101.0, 30.0],
            [101.0, 31.0],
            [100.0, 31.0],
            [100.0, 30.0],
        ]],
    }

    def fake_search_scenes_from_asf(**kwargs):
        calls.append(kwargs.get("max_results"))
        stats = kwargs.get("stats")
        if isinstance(stats, dict):
            stats.update(
                {
                    "requested_limit": kwargs.get("max_results"),
                    "query_limit": kwargs.get("max_results"),
                    "total_count": len(scenes),
                    "returned_count": len(scenes),
                    "source": "ASF",
                }
            )
        return scenes

    monkeypatch.setattr(metadata, "search_scenes_from_asf", fake_search_scenes_from_asf)

    api = Api()
    first = api.search_asf_scenes(
        {
            "bbox": bbox,
            "aoi_geojson": {"type": "Feature", "properties": {"name": "四川"}, "geometry": geometry},
            "max_results": "3",
            "product_type": "SLC",
            "beam_mode": "IW",
        }
    )
    second = api.search_asf_scenes(
        {
            "bbox": bbox,
            "aoi_geojson": geometry,
            "max_results": "3",
            "product_type": "SLC",
            "beam_mode": "IW",
        }
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert calls == [3]
