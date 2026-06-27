"""ASF Sentinel-1 orbit companion downloader.

Downloads the best available Sentinel-1 orbit file for each scene from ASF's
public s1-orbits service, but only stores precise POEORB products. No Earthdata
credentials are required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import DownloadError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.providers.orbit.orbit_parser import parse_orbit_filename
from insar_prep.providers.orbit.types import OrbitType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from insar_prep.core.models import Scene

logger = get_logger("providers.orbit.downloader")

ASF_ORBIT_SCENE_URL = "https://s1-orbits.asf.alaska.edu/scene/{scene_id}"
ORBIT_ROOT_DIR = "Sentinel_Orbit"
POEORB_SUBDIR = "AUX_POEORB"
POEORB_RECENT_HINT_DAYS = 25
_TIMEOUT_SECONDS = 60
_CHUNK_SIZE = 1024 * 256


class OrbitDownloadOutcome(StrEnum):
    """Outcome of one orbit companion download."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class OrbitDownloadResult:
    """One per-scene orbit download result."""

    scene_id: str
    outcome: OrbitDownloadOutcome
    orbit_file: str = ""
    orbit_type: str = ""
    path: Path | None = None
    bytes_written: int = 0
    message: str = ""
    error_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "outcome": self.outcome.value,
            "orbit_file": self.orbit_file,
            "orbit_type": self.orbit_type,
            "path": str(self.path) if self.path else "",
            "bytes_written": self.bytes_written,
            "message": mask_text(self.message),
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class OrbitDownloadSummary:
    """Aggregate result for an orbit companion download run."""

    results: list[OrbitDownloadResult]
    orbit_dir: Path

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for result in self.results if result.outcome is OrbitDownloadOutcome.SUCCESS)

    @property
    def skipped(self) -> int:
        return sum(1 for result in self.results if result.outcome is OrbitDownloadOutcome.SKIPPED)

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if result.outcome is OrbitDownloadOutcome.FAILED)

    @property
    def unavailable(self) -> int:
        return sum(
            1 for result in self.results if result.outcome is OrbitDownloadOutcome.UNAVAILABLE
        )

    @property
    def has_failures(self) -> bool:
        return self.failed > 0

    def summary_line(self) -> str:
        return (
            f"{self.succeeded} downloaded, {self.skipped} skipped, "
            f"{self.unavailable} unavailable, {self.failed} failed"
        )


def _scene_url(scene_id: str) -> str:
    return ASF_ORBIT_SCENE_URL.format(scene_id=scene_id)


def poeorb_directory(output_root: Path | str) -> Path:
    """Return the required local precise-orbit directory."""
    return Path(output_root) / ORBIT_ROOT_DIR / POEORB_SUBDIR


def _recent_scene_hint(scene: "Scene") -> str:
    acquired = getattr(scene, "acquisition_datetime", None)
    if acquired is None:
        return "ASF 未返回 POEORB 精密轨道。"
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=UTC)
    age_days = (datetime.now(tz=UTC) - acquired).days
    if age_days < POEORB_RECENT_HINT_DAYS:
        return (
            "场景采集时间较近，ASF 可能尚未发布 POEORB 精密轨道；"
            "可稍后重试，或临时使用 RESORB。"
        )
    return "ASF 未返回该场景对应的 POEORB 精密轨道。"


def _response_filename(response: object) -> str:
    headers = getattr(response, "headers", {}) or {}
    disposition = str(headers.get("content-disposition") or "")
    if "filename=" in disposition:
        name = disposition.rsplit("filename=", 1)[-1].strip().strip('"')
        if name:
            return unquote(name)
    url = str(getattr(response, "url", "") or "")
    return unquote(Path(urlparse(url).path).name)


def _download_one(scene: "Scene", orbit_dir: Path) -> OrbitDownloadResult:
    try:
        import requests  # noqa: PLC0415 - optional download extra
    except ImportError as exc:
        raise DownloadError(
            "orbit download needs requests; install the download extra",
            code=ErrorCode.ORB001,
        ) from exc

    try:
        response = requests.get(
            _scene_url(scene.scene_id),
            stream=True,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        message = _recent_scene_hint(scene)
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.UNAVAILABLE,
            message=f"{message} 请求详情：{exc}",
            error_code=ErrorCode.ORB001.value,
        )

    filename = _response_filename(response)
    try:
        orbit = parse_orbit_filename(filename)
    except Exception:  # noqa: BLE001
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.UNAVAILABLE,
            message=f"ASF 未返回 Sentinel-1 orbit EOF 文件：{filename or response.url}",
            error_code=ErrorCode.ORB001.value,
        )
    if orbit.orbit_type is not OrbitType.POEORB:
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.UNAVAILABLE,
            orbit_file=orbit.file_name,
            orbit_type=orbit.orbit_type.value,
            message=f"{_recent_scene_hint(scene)} ASF 当前返回的是 {orbit.orbit_type.value}。",
            error_code=ErrorCode.ORB001.value,
        )
    target = orbit_dir / orbit.file_name
    if target.exists() and target.stat().st_size > 0:
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.SKIPPED,
            orbit_file=orbit.file_name,
            orbit_type=orbit.orbit_type.value,
            path=target,
            message="精密轨道文件已存在，已跳过下载。",
        )

    try:
        orbit_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
    except OSError as exc:
        return OrbitDownloadResult(
            scene_id=scene.scene_id,
            outcome=OrbitDownloadOutcome.FAILED,
            orbit_file=orbit.file_name,
            orbit_type=orbit.orbit_type.value,
            path=target,
            message=f"无法写入精密轨道文件：{exc}",
            error_code=ErrorCode.ORB001.value,
        )

    logger.info("downloaded orbit %s for %s", orbit.file_name, scene.scene_id)
    return OrbitDownloadResult(
        scene_id=scene.scene_id,
        outcome=OrbitDownloadOutcome.SUCCESS,
        orbit_file=orbit.file_name,
        orbit_type=orbit.orbit_type.value,
        path=target,
        bytes_written=written,
        message="已从 ASF 下载 POEORB 精密轨道文件。",
    )


def download_orbit_for_scene(scene: "Scene", orbit_dir: Path | str) -> OrbitDownloadResult:
    """Download one scene's POEORB companion file into an existing orbit directory."""
    return _download_one(scene, Path(orbit_dir))


def download_orbits_for_scenes(
    scenes: "Iterable[Scene]",
    output_root: Path | str,
) -> OrbitDownloadSummary:
    """Download POEORB files for ``scenes`` under ``Sentinel_Orbit/AUX_POEORB``."""
    orbit_dir = poeorb_directory(output_root)
    results: list[OrbitDownloadResult] = []
    seen_scene_ids: set[str] = set()
    seen_orbit_files: set[str] = set()
    for scene in scenes:
        if scene.scene_id in seen_scene_ids:
            continue
        seen_scene_ids.add(scene.scene_id)
        result = _download_one(scene, orbit_dir)
        if result.orbit_file and result.orbit_file in seen_orbit_files:
            result = OrbitDownloadResult(
                scene_id=result.scene_id,
                outcome=OrbitDownloadOutcome.SKIPPED,
                orbit_file=result.orbit_file,
                orbit_type=result.orbit_type,
                path=result.path,
                message="同一精密轨道已由另一景下载，已复用。",
            )
        if result.orbit_file:
            seen_orbit_files.add(result.orbit_file)
        results.append(result)
    return OrbitDownloadSummary(results=results, orbit_dir=orbit_dir)
