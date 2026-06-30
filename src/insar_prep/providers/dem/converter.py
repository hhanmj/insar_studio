"""Real DEM vertical-datum conversion (Task 053).

Executes the steps that :mod:`insar_prep.providers.dem.conversion_planner` only
*plans*: turn an orthometric (EGM96/EGM2008) DEM into a WGS84 *ellipsoidal*
GeoTIFF by adding the geoid undulation ``N`` to every pixel
(``h_ellipsoid = H_orthometric + N``), then export an ENVI-format SARscape DEM
whose main raster filename ends with ``_dem``. Datasets that are already
ellipsoidal (e.g. ``SRTMGL1_E``/``AW3D30_E``) are copied to the ellipsoid GeoTIFF
and exported the same way.

This is opt-in and behind the ``convert`` extra: :mod:`rasterio` (the GeoTIFF
reader/writer) is imported lazily so the offline core never depends on it. The
geoid grid (:mod:`insar_prep.providers.dem.geoid`) uses only numpy. The transfer
writes to a ``.part`` temp file and is atomically renamed only after a valid
GeoTIFF is produced, mirroring the download path's integrity contract.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from xml.etree import ElementTree as ET

import numpy as np

from insar_prep.core.enums import DemDataset, VerticalDatum
from insar_prep.core.error_codes import ErrorCode
from insar_prep.core.exceptions import DemProcessingError
from insar_prep.core.logging import get_logger, mask_text
from insar_prep.core.models import InsarBaseModel
from insar_prep.providers.dem.geoid import GeoidGrid, load_bundled_geoid, load_geoid_file
from insar_prep.providers.dem.types import DemConversionPlan

logger = get_logger("providers.dem.converter")

# Process the raster in row blocks so a large DEM never loads three full-size
# float64 coordinate arrays at once.
_BLOCK_ROWS = 512

_GEOID_SOURCES = frozenset({VerticalDatum.EGM96, VerticalDatum.EGM2008, VerticalDatum.ORTHOMETRIC})
_SARSCAPE_SML_NS = "http://www.sarmap.ch/xml/SARscapeHeaderSchema"
_SARSCAPE_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_SARSCAPE_SML_VERSION = "2.0.2"

# Which vertical datum each OpenTopography dataset's heights are referenced to.
_DATASET_SOURCE_DATUM: dict[str, VerticalDatum] = {
    DemDataset.COP30.value: VerticalDatum.EGM2008,
    DemDataset.COP90.value: VerticalDatum.EGM2008,
    DemDataset.SRTM_GL3.value: VerticalDatum.EGM96,
    DemDataset.SRTM_GL1.value: VerticalDatum.EGM96,
    DemDataset.NASADEM.value: VerticalDatum.EGM96,
    DemDataset.AW3D30.value: VerticalDatum.EGM96,
    DemDataset.SRTM_GL1_ELLIPSOIDAL.value: VerticalDatum.WGS84_ELLIPSOID,
    DemDataset.AW3D30_ELLIPSOIDAL.value: VerticalDatum.WGS84_ELLIPSOID,
}


def dataset_source_vertical_datum(dataset: DemDataset | str) -> VerticalDatum:
    """Return the native vertical datum of ``dataset`` (UNKNOWN if not mapped)."""
    value = dataset.value if isinstance(dataset, DemDataset) else str(dataset)
    return _DATASET_SOURCE_DATUM.get(value, VerticalDatum.UNKNOWN)


def default_geoid_model_for(source: VerticalDatum) -> str | None:
    """Return the geoid model name needed to convert from ``source`` (or None)."""
    if source is VerticalDatum.EGM2008:
        return "EGM2008"
    if source is VerticalDatum.EGM96:
        return "EGM96"
    return None


class DemConversionOutcome(StrEnum):
    """Outcome of a single DEM vertical-datum conversion attempt."""

    SUCCESS = "success"
    COPIED = "copied"  # already ellipsoidal: copied through unchanged
    SKIPPED = "skipped"  # SARscape-ready DEM already present
    FAILED = "failed"


class DemConversionResult(InsarBaseModel):
    """The outcome of a DEM vertical-datum conversion attempt."""

    region_safe_name: str
    dataset: str
    outcome: DemConversionOutcome
    source_vertical_datum: VerticalDatum
    target_vertical_datum: VerticalDatum
    geoid_model: str | None = None
    path: Path | None = None
    message: str = ""
    error_code: str | None = None


@runtime_checkable
class DemConverter(Protocol):
    """The interface a real or fake DEM converter must implement."""

    def convert(self, plan: DemConversionPlan) -> DemConversionResult:
        """Convert (or simulate converting) one DEM and return the result."""
        ...


class FakeDemConverter:
    """An offline, deterministic fake converter for tests (no rasterio).

    With ``outcome=FAILED`` it simulates a failure; otherwise it produces a
    placeholder SARscape-ready ``_dem`` file (so runner/CLI orchestration can be
    exercised without rasterio, a geoid, or a real GeoTIFF).
    """

    def __init__(self, *, outcome: DemConversionOutcome = DemConversionOutcome.SUCCESS) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def convert(self, plan: DemConversionPlan) -> DemConversionResult:
        self.calls.append(plan.region_safe_name)
        if self.outcome is DemConversionOutcome.FAILED:
            return DemConversionResult(
                region_safe_name=plan.region_safe_name,
                dataset=plan.dataset,
                outcome=DemConversionOutcome.FAILED,
                source_vertical_datum=plan.source_vertical_datum,
                target_vertical_datum=plan.target_vertical_datum,
                message="simulated DEM conversion failure",
                error_code=ErrorCode.DEM003.value,
            )
        dest = plan.sarscape_ready_dem_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if plan.raw_dem_path.exists():
            shutil.copyfile(plan.raw_dem_path, dest)
        else:
            dest.write_bytes(b"fake-dem")
        dest.with_name(dest.name + ".hdr").write_text("ENVI\n", encoding="utf-8")
        return DemConversionResult(
            region_safe_name=plan.region_safe_name,
            dataset=plan.dataset,
            outcome=self.outcome,
            source_vertical_datum=plan.source_vertical_datum,
            target_vertical_datum=plan.target_vertical_datum,
            path=dest,
            message="fake conversion ok",
        )


def _import_rasterio() -> object:
    """Import rasterio lazily; raise a clear DemProcessingError if it is missing."""
    try:
        from insar_prep.core.component_manager import activate_component

        activate_component()
    except Exception:
        pass
    try:
        import rasterio  # noqa: PLC0415 - optional dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - exercised via CLI guard
        raise DemProcessingError(
            "real DEM vertical-datum conversion needs rasterio/GDAL; "
            "install the DEM advanced component in the desktop app, or install "
            "the optional 'convert' extra with 'uv sync --extra convert'",
            code=ErrorCode.DEM003,
        ) from exc
    return rasterio


def _is_gdal_proj_runtime_error(exc: Exception) -> bool:
    lowered = f"{type(exc).__name__}: {exc}".lower()
    return any(
        token in lowered
        for token in (
            "proj.db",
            "proj_create_from_database",
            "the epsg code is unknown",
            "cannot find proj.db",
            "gdal",
            "rasterio",
        )
    )


def _gdal_proj_component_message(exc: Exception) -> str:
    return (
        "DEM/GDAL 高级转换组件不完整或未正确激活，无法读取 GDAL/PROJ 坐标数据库。"
        "请到“设置 → 更新与组件”安装或重新安装 DEM/GDAL 高级转换组件后重试。"
        f" 原因：{type(exc).__name__}: {exc}"
    )


class RealDemConverter:
    """Convert a DEM's vertical datum to the WGS84 ellipsoid using a geoid grid.

    Construction does no I/O and imports nothing heavy. The geoid grid is loaded
    lazily on the first conversion that needs one: the bundled EGM96 grid by
    default, or ``geoid_grid_path`` if given (e.g. a user-supplied EGM2008 grid).
    """

    def __init__(
        self,
        *,
        geoid: GeoidGrid | None = None,
        geoid_grid_path: Path | str | None = None,
        block_rows: int = _BLOCK_ROWS,
        write_sarscape_ready: bool = True,
    ) -> None:
        self._geoid = geoid
        self._geoid_grid_path = Path(geoid_grid_path) if geoid_grid_path else None
        self.block_rows = max(1, block_rows)
        self.write_sarscape_ready = write_sarscape_ready

    def _load_geoid(self, model_hint: str | None) -> GeoidGrid:
        if self._geoid is not None:
            return self._geoid
        if self._geoid_grid_path is not None:
            self._geoid = load_geoid_file(self._geoid_grid_path, model=model_hint)
        else:
            if not model_hint:
                raise DemProcessingError(
                    "无法确定 DEM 需要使用哪一种大地水准面模型；请明确选择 EGM96 或 EGM2008。",
                    code=ErrorCode.DEM002,
                )
            if model_hint.upper() == "EGM2008":
                try:
                    from insar_prep.core.component_manager import (  # noqa: PLC0415
                        DEM_GDAL_COMPONENT_ID,
                        EGM2008_GEOID_CANDIDATES,
                        find_component_file,
                    )

                    component_grid = find_component_file(
                        DEM_GDAL_COMPONENT_ID, EGM2008_GEOID_CANDIDATES
                    )
                except Exception:  # noqa: BLE001 - component state is optional.
                    component_grid = None
                if component_grid is not None:
                    self._geoid = load_geoid_file(component_grid, model=model_hint)
                    return self._geoid
            try:
                self._geoid = load_bundled_geoid(model_hint)
            except DemProcessingError as exc:
                if model_hint.upper() == "EGM2008":
                    raise DemProcessingError(
                        "检测到源 DEM 为 EGM2008 正高（例如 COP30/COP90），但当前未安装"
                        "完整的 DEM/GDAL 高级转换组件（缺少 EGM2008 大地水准面网格）。"
                        "为避免误用 EGM96 近似，已停止转换；"
                        "请到“设置 → 更新与组件”安装 DEM/GDAL 高级转换组件后重试，"
                        "或在确认可接受近似时手动选择 EGM96。",
                        code=ErrorCode.DEM003,
                    ) from exc
                raise
        return self._geoid

    def convert(self, plan: DemConversionPlan) -> DemConversionResult:
        """Convert one DEM, returning a :class:`DemConversionResult` (never raises)."""
        source = plan.source_vertical_datum
        target = plan.target_vertical_datum
        dest = plan.sarscape_ready_dem_path if self.write_sarscape_ready else plan.ellipsoid_dem_path

        def failed(message: str, code: ErrorCode = ErrorCode.DEM003) -> DemConversionResult:
            return DemConversionResult(
                region_safe_name=plan.region_safe_name,
                dataset=plan.dataset,
                outcome=DemConversionOutcome.FAILED,
                source_vertical_datum=source,
                target_vertical_datum=target,
                message=mask_text(message),
                error_code=code.value,
            )

        if VerticalDatum.UNKNOWN in (source, target):
            return failed(
                "DEM vertical datum is unknown; specify it before converting",
                ErrorCode.DEM002,
            )
        if not plan.raw_dem_path.exists():
            return failed(
                f"raw DEM not found: {plan.raw_dem_path}; "
                "run 'download-dem --download-mode real' first"
            )

        # No vertical conversion needed: keep a checkable ellipsoid GeoTIFF, then
        # optionally export the SARscape-facing ENVI _dem raster.
        if source == target:
            try:
                plan.ellipsoid_dem_path.parent.mkdir(parents=True, exist_ok=True)
                if plan.raw_dem_path != plan.ellipsoid_dem_path:
                    shutil.copyfile(plan.raw_dem_path, plan.ellipsoid_dem_path)
                if self.write_sarscape_ready:
                    self._write_sarscape_ready(plan.ellipsoid_dem_path, dest)
            except (OSError, DemProcessingError) as exc:
                action = "export SARscape DEM" if self.write_sarscape_ready else "write ellipsoid GeoTIFF"
                return failed(f"could not {action}: {exc}")
            return DemConversionResult(
                region_safe_name=plan.region_safe_name,
                dataset=plan.dataset,
                outcome=DemConversionOutcome.COPIED,
                source_vertical_datum=source,
                target_vertical_datum=target,
                path=dest,
                message=(
                    "dataset already ellipsoidal; exported SARscape ENVI _dem + .hdr + .sml"
                    if self.write_sarscape_ready
                    else "dataset already ellipsoidal; wrote ellipsoid GeoTIFF"
                ),
            )

        if target is not VerticalDatum.WGS84_ELLIPSOID or source not in _GEOID_SOURCES:
            return failed(f"unsupported vertical-datum conversion {source.value} -> {target.value}")

        model_hint = default_geoid_model_for(source)
        if model_hint is None and self._geoid is None and self._geoid_grid_path is None:
            return failed(
                "无法根据当前 DEM 自动判断大地水准面模型；请手动选择 EGM96 或 EGM2008。",
                ErrorCode.DEM002,
            )
        try:
            geoid = self._load_geoid(model_hint)
        except DemProcessingError as exc:
            return failed(str(exc))

        if dest.exists() and dest.stat().st_size > 0:
            return DemConversionResult(
                region_safe_name=plan.region_safe_name,
                dataset=plan.dataset,
                outcome=DemConversionOutcome.SKIPPED,
                source_vertical_datum=source,
                target_vertical_datum=target,
                geoid_model=geoid.model,
                path=dest,
                message=f"SARscape-ready DEM already present; skipped after validating {geoid.model}",
            )

        approximated = source is VerticalDatum.EGM2008 and geoid.model.upper() != "EGM2008"
        try:
            self._convert_raster(plan, geoid)
        except DemProcessingError as exc:
            return failed(str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any raster error as FAILED
            if _is_gdal_proj_runtime_error(exc):
                return failed(_gdal_proj_component_message(exc))
            return failed(f"{type(exc).__name__}: {exc}")

        message = f"converted {source.value} -> {target.value} using {geoid.model}"
        if not self.write_sarscape_ready:
            message += "; wrote ellipsoid GeoTIFF"
        if approximated:
            message += " (EGM96 used as an approximation for an EGM2008 source)"
            logger.warning(
                "DEM %s: EGM96 geoid used to approximate an EGM2008 source", plan.region_safe_name
            )
        return DemConversionResult(
            region_safe_name=plan.region_safe_name,
            dataset=plan.dataset,
            outcome=DemConversionOutcome.SUCCESS,
            source_vertical_datum=source,
            target_vertical_datum=target,
            geoid_model=geoid.model,
            path=dest,
            message=message,
        )

    def _convert_raster(self, plan: DemConversionPlan, geoid: GeoidGrid) -> None:
        """Read the raw DEM, add geoid undulation, and write the ellipsoidal DEM."""
        rasterio = _import_rasterio()

        raw_path = plan.raw_dem_path
        ellipsoid_path = plan.ellipsoid_dem_path
        dest = plan.sarscape_ready_dem_path
        ellipsoid_path.parent.mkdir(parents=True, exist_ok=True)
        part = ellipsoid_path.with_name(ellipsoid_path.name + ".part")

        with rasterio.open(raw_path) as src:
            crs = src.crs
            if crs is None or not crs.is_geographic:
                raise DemProcessingError(
                    "DEM CRS must be geographic WGS84 lon/lat (EPSG:4326); "
                    f"got {crs.to_string() if crs else 'no CRS'}. Reprojection is not performed.",
                    code=ErrorCode.DEM003,
                )
            transform = src.transform
            nodata = src.nodata
            profile = src.profile.copy()
            profile.update(dtype="float32", count=1, compress="deflate")

            self._apply_block_offsets(rasterio, src, profile, part, transform, nodata, geoid)

        os.replace(part, ellipsoid_path)
        if self.write_sarscape_ready:
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._write_sarscape_ready(ellipsoid_path, dest)
            logger.info("converted DEM %s -> %s", plan.region_safe_name, dest)
        else:
            logger.info("converted DEM %s -> %s", plan.region_safe_name, ellipsoid_path)

    def _write_sarscape_ready(self, source_path: Path, dest: Path) -> None:
        """Export an ellipsoid GeoTIFF to SARscape's ENVI ``*_dem`` raster."""
        rasterio = _import_rasterio()
        part = dest.with_name(dest.name + ".part")
        part_hdr = part.with_name(part.name + ".hdr")
        final_hdr = dest.with_name(dest.name + ".hdr")
        final_sml = dest.with_name(dest.name + ".sml")
        for stale in (part, part_hdr, final_sml):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
        with rasterio.open(source_path) as src:  # type: ignore[attr-defined]
            profile = src.profile.copy()
            for key in ("compress", "tiled", "blockxsize", "blockysize", "photometric"):
                profile.pop(key, None)
            profile.update(driver="ENVI", dtype="float32", count=src.count, interleave="bsq")
            with rasterio.open(part, "w", **profile) as dst:  # type: ignore[attr-defined]
                if src.count == 1:
                    for _, window in src.block_windows(1):
                        data = src.read(1, window=window).astype(np.float32)  # type: ignore[attr-defined]
                        dst.write(data, 1, window=window)
                else:
                    for band in range(1, src.count + 1):
                        for _, window in src.block_windows(band):
                            data = src.read(band, window=window).astype(np.float32)  # type: ignore[attr-defined]
                            dst.write(data, band, window=window)
        os.replace(part, dest)
        if part_hdr.exists():
            os.replace(part_hdr, final_hdr)
        self._write_sarscape_sml(dest, final_sml)
        if final_hdr.exists():
            self._normalize_envi_header(final_hdr)

    def _normalize_envi_header(self, header_path: Path) -> None:
        """Remove temporary ``.part`` paths from the ENVI header description."""
        try:
            text = header_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = header_path.read_text(encoding="latin-1")
        text = re.sub(
            r"(?is)description\s*=\s*\{.*?\}",
            "description = {\n   ELLIPSOIDAL DEM.\n   Generated by InSAR Studio}",
            text,
            count=1,
        )
        header_path.write_text(text, encoding="utf-8")

    def _write_sarscape_sml(self, raster_path: Path, sml_path: Path) -> None:
        """Write SARscape's XML sidecar so SBAS can recognize the DEM as ellipsoidal."""
        rasterio = _import_rasterio()
        ET.register_namespace("", _SARSCAPE_SML_NS)
        ET.register_namespace("xsi", _SARSCAPE_XSI_NS)

        def tag(name: str) -> str:
            return f"{{{_SARSCAPE_SML_NS}}}{name}"

        with rasterio.open(raster_path) as src:  # type: ignore[attr-defined]
            transform = src.transform
            bounds = src.bounds
            x_spacing = float(transform.a)
            y_spacing = float(transform.e)
            wkt = self._sarscape_wkt(src.crs)
            nodata = self._format_sml_number(src.nodata) if src.nodata is not None else "NaN"
            root = ET.Element(
                tag("HEADER_INFO"),
                {
                    f"{{{_SARSCAPE_XSI_NS}}}schemaLocation": (
                        f"{_SARSCAPE_SML_NS}\n"
                        f"{_SARSCAPE_SML_NS}/SARscapeHeaderSchema_version_"
                        f"{_SARSCAPE_SML_VERSION}.xsd"
                    )
                },
            )
            raster_info = ET.SubElement(root, tag("RasterInfo"))
            for key, value in (
                ("HeaderOffset", "0"),
                ("RowPrefix", "0"),
                ("RowSuffix", "0"),
                ("CellType", self._sarscape_cell_type(src.dtypes[0])),
                ("DataUnits", "ELLIPSOIDAL DEM"),
                ("NullCellValue", nodata),
                ("NrOfChannels", str(src.count)),
                ("NrOfPixelsPerLine", str(src.width)),
                ("NrOfLinesPerImage", str(src.height)),
                ("GeocodedImage", "OK"),
                ("Interleave", "LAYOUT_BSQ"),
                ("SmlVersion", _SARSCAPE_SML_VERSION),
                ("BytesOrder", "LSBF" if sys.byteorder == "little" else "MSBF"),
            ):
                ET.SubElement(raster_info, tag(key)).text = value

            other = ET.SubElement(raster_info, tag("OtherInfo"))
            matrix = ET.SubElement(other, tag("MatrixString"), NumberOfRows="2", NumberOfColumns="2")
            self._add_sml_matrix_row(matrix, tag, 0, "SOFTWARE", "InSAR Studio")
            self._add_sml_matrix_row(matrix, tag, 1, "SML VERSION", _SARSCAPE_SML_VERSION)

            cart = ET.SubElement(root, tag("CartographicSystem"))
            ET.SubElement(cart, tag("cartographic_system_specification")).text = wkt

            reg = ET.SubElement(root, tag("RegistrationCoordinates"))
            for key, value in (
                ("LatNorthing", self._format_sml_number(bounds.top)),
                ("LonEasting", self._format_sml_number(bounds.left)),
                ("PixelSpacingLatNorth", self._format_sml_number(y_spacing)),
                ("PixelSpacingLonEast", self._format_sml_number(x_spacing)),
            ):
                ET.SubElement(reg, tag(key)).text = value

            dem = ET.SubElement(root, tag("DEMCoordinates"))
            for key, value in (
                ("EastingCoordinateBegin", self._format_sml_number(bounds.left)),
                ("EastingCoordinateEnd", self._format_sml_number(bounds.right)),
                ("EastingGridSize", self._format_sml_number(abs(x_spacing))),
                ("NorthingCoordinateBegin", self._format_sml_number(bounds.bottom)),
                ("NorthingCoordinateEnd", self._format_sml_number(bounds.top)),
                ("NorthingGridSize", self._format_sml_number(abs(y_spacing))),
            ):
                ET.SubElement(dem, tag(key)).text = value

        tree = ET.ElementTree(root)
        ET.indent(tree, space="   ")
        tree.write(sml_path, encoding="utf-8", xml_declaration=True)

    def _add_sml_matrix_row(
        self,
        matrix: ET.Element,
        tag: Callable[[str], str],
        row_id: int,
        key: str,
        value: str,
    ) -> None:
        row = ET.SubElement(matrix, tag("MatrixRowString"), ID=str(row_id))
        ET.SubElement(row, tag("ValueString"), ID="0").text = key
        ET.SubElement(row, tag("ValueString"), ID="1").text = value

    def _sarscape_wkt(self, crs: object) -> str:
        if crs is None:
            return ""
        try:
            return crs.to_wkt(version="WKT1_ESRI")  # type: ignore[attr-defined]
        except TypeError:
            return crs.to_wkt()  # type: ignore[attr-defined]

    def _sarscape_cell_type(self, dtype: str) -> str:
        value = str(dtype).lower()
        if value in {"float32", "single"}:
            return "FLOAT"
        if value in {"float64", "double"}:
            return "DOUBLE"
        if value in {"uint8", "ubyte"}:
            return "UCHAR"
        if value in {"int16"}:
            return "SHORT"
        if value in {"uint16"}:
            return "USHORT"
        if value in {"int32"}:
            return "INT"
        if value in {"uint32"}:
            return "UINT"
        return "FLOAT"

    def _format_sml_number(self, value: object) -> str:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value)
        if np.isnan(number):
            return "NaN"
        return format(number, ".17g")

    def _apply_block_offsets(
        self,
        rasterio: object,
        src: object,
        profile: dict,
        part: Path,
        transform: object,
        nodata: float | None,
        geoid: GeoidGrid,
    ) -> None:
        width = src.width  # type: ignore[attr-defined]
        height = src.height  # type: ignore[attr-defined]
        cols = np.arange(width, dtype=np.float64) + 0.5
        a, b, c = transform.a, transform.b, transform.c  # type: ignore[attr-defined]
        d, e, f = transform.d, transform.e, transform.f  # type: ignore[attr-defined]
        with rasterio.open(part, "w", **profile) as dst:  # type: ignore[attr-defined]
            for row_start in range(0, height, self.block_rows):
                row_stop = min(row_start + self.block_rows, height)
                window = rasterio.windows.Window(0, row_start, width, row_stop - row_start)  # type: ignore[attr-defined]
                block = src.read(1, window=window).astype(np.float64)  # type: ignore[attr-defined]
                rows = np.arange(row_start, row_stop, dtype=np.float64) + 0.5
                col_grid, row_grid = np.meshgrid(cols, rows)
                lon = a * col_grid + b * row_grid + c
                lat = d * col_grid + e * row_grid + f
                undulation = geoid.undulation_at(lat, lon)
                converted = block + undulation
                if nodata is not None:
                    converted = np.where(block == nodata, nodata, converted)
                dst.write(converted.astype(np.float32), 1, window=window)
