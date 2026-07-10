"""Desktop download/task status orchestration.

The pywebview API keeps stable method names, while this service owns the small
piece of coordination that turns job-manager status snapshots into UI poll
responses and archive updates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

StatusGetter = Callable[[], dict[str, Any]]
ArchiveStatusCallback = Callable[[dict[str, Any]], None]


class DownloadStatusService:
    """Return current task status snapshots and trigger archive side effects."""

    def __init__(
        self,
        *,
        asf_status: StatusGetter,
        orbit_status: StatusGetter,
        dem_status: StatusGetter,
        archive_asf_status: ArchiveStatusCallback,
        archive_orbit_status: ArchiveStatusCallback,
    ) -> None:
        self._asf_status = asf_status
        self._orbit_status = orbit_status
        self._dem_status = dem_status
        self._archive_asf_status = archive_asf_status
        self._archive_orbit_status = archive_orbit_status

    def get_asf_status(self) -> dict[str, Any]:
        """Return ASF download status and preserve archive history."""
        status = self._asf_status()
        self._archive_asf_status(status)
        return status

    def get_orbit_status(self) -> dict[str, Any]:
        """Return orbit download status and preserve archive history."""
        status = self._orbit_status()
        self._archive_orbit_status(status)
        return status

    def get_dem_status(self) -> dict[str, Any]:
        """Return DEM download status.

        DEM archive writes are intentionally not added here yet: the existing
        desktop API only polled this job without archiving on every status read.
        """
        return self._dem_status()
