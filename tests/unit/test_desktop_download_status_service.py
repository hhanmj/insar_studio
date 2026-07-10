from __future__ import annotations

from insar_prep.desktop.download_status_service import DownloadStatusService


def test_download_status_service_archives_asf_and_orbit_status() -> None:
    archived_asf: list[dict] = []
    archived_orbit: list[dict] = []
    service = DownloadStatusService(
        asf_status=lambda: {"ok": True, "state": "finished", "kind": "asf"},
        orbit_status=lambda: {"ok": True, "state": "paused", "kind": "orbit"},
        dem_status=lambda: {"ok": True, "state": "idle", "kind": "dem"},
        archive_asf_status=archived_asf.append,
        archive_orbit_status=archived_orbit.append,
    )

    assert service.get_asf_status()["kind"] == "asf"
    assert service.get_orbit_status()["kind"] == "orbit"
    assert archived_asf == [{"ok": True, "state": "finished", "kind": "asf"}]
    assert archived_orbit == [{"ok": True, "state": "paused", "kind": "orbit"}]


def test_download_status_service_keeps_dem_polling_read_only() -> None:
    archived_asf: list[dict] = []
    archived_orbit: list[dict] = []
    service = DownloadStatusService(
        asf_status=lambda: {"ok": True, "state": "idle"},
        orbit_status=lambda: {"ok": True, "state": "idle"},
        dem_status=lambda: {"ok": True, "state": "running", "dataset": "COP30"},
        archive_asf_status=archived_asf.append,
        archive_orbit_status=archived_orbit.append,
    )

    assert service.get_dem_status() == {"ok": True, "state": "running", "dataset": "COP30"}
    assert archived_asf == []
    assert archived_orbit == []


def test_download_status_service_uses_latest_getter_target() -> None:
    state = {"status": {"ok": True, "state": "idle"}}
    service = DownloadStatusService(
        asf_status=lambda: state["status"],
        orbit_status=lambda: {"ok": True, "state": "idle"},
        dem_status=lambda: {"ok": True, "state": "idle"},
        archive_asf_status=lambda _status: None,
        archive_orbit_status=lambda _status: None,
    )

    assert service.get_asf_status()["state"] == "idle"
    state["status"] = {"ok": True, "state": "running"}
    assert service.get_asf_status()["state"] == "running"
