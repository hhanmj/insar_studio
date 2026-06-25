"""JS<->Python bridge for the desktop web UI.

Every public method on :class:`Api` is callable from the frontend as
``window.pywebview.api.<method>(...)`` and returns a JSON-serialisable value
(pywebview marshals the return value into a JS Promise). This layer is
deliberately thin: it reuses the existing, fully-tested core
(:mod:`insar_prep.processing`, :mod:`insar_prep.providers`,
:mod:`insar_prep.quality`, :mod:`insar_prep.reporting`) and the Qt-free
:class:`insar_prep.gui.state.GuiState`, adding only (de)serialisation and stable
error codes.

Heavy / optional dependencies (shapely, rasterio, keyring, geopandas, ...) are
imported lazily *inside* the relevant methods so a missing extra only disables
that one feature instead of breaking the whole desktop app on startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insar_prep import __version__
from insar_prep.core.exceptions import InsarPrepError
from insar_prep.gui.state import GuiState, workspace_display_name


def _error(exc: InsarPrepError) -> dict:
    """Render a coded core error as a JSON-friendly envelope for the UI."""
    code = getattr(exc, "code", None)
    return {"ok": False, "error": str(exc), "code": getattr(code, "name", None)}


def _error_msg(message: str, code: str | None = None) -> dict:
    """Build a plain error envelope (no core exception involved)."""
    return {"ok": False, "error": message, "code": code}


def _missing_dep(feature: str, exc: Exception) -> dict:
    """Friendly envelope when an optional dependency is not installed."""
    return {
        "ok": False,
        "error": f"{feature}需要可选依赖，但当前环境未安装：{exc}",
        "code": "DEP000",
    }


def _dump(model: Any) -> Any:
    """Serialise a pydantic model to JSON-safe primitives."""
    return model.model_dump(mode="json")


class Api:
    """The object exposed to the web UI as ``window.pywebview.api``."""

    def __init__(self) -> None:
        self._state = GuiState()
        # The DEM dataset is chosen once (in the download step); the vertical-datum
        # conversion is then auto-detected from it, never chosen by the user.
        self._dem_dataset = "COP30"

    # ------------------------------------------------------------------ app
    def get_app_info(self) -> dict:
        """Return basic app identity (proves the JS<->Python bridge is live)."""
        return {
            "ok": True,
            "name": "InSAR Assistant",
            "version": __version__,
            "offline": True,
        }

    def get_context(self) -> dict:
        """Return the current workspace/project/region selection for any panel."""
        ws = self._state.workspace
        proj = self._state.current_project()
        region = self._state.current_region()
        ctx: dict = {"ok": True, "workspace": None, "project": None, "region": None}
        if ws is not None:
            ctx["workspace"] = {
                "workspace_id": ws.workspace_id,
                "root": str(ws.workspace_root),
                "name": workspace_display_name(ws),
            }
        if proj is not None:
            ctx["project"] = {
                "project_id": proj.project_id,
                "name": proj.project_name,
                "safe_name": proj.safe_name,
            }
        if region is not None:
            has_bbox = region.aoi is not None and region.aoi.bbox is not None
            ctx["region"] = {
                "region_id": region.region_id,
                "name": region.region_name,
                "safe_name": region.region_safe_name,
                "has_aoi": has_bbox,
                "bbox": _dump(region.aoi.bbox) if has_bbox else None,
                "scene_count": len(region.scenes),
            }
        ctx["dem_dataset"] = self._dem_dataset
        return ctx

    def set_dem_dataset(self, dataset: str) -> dict:
        """Set the DEM dataset for the session (conversion is auto-derived)."""
        name = (dataset or "").strip().upper()
        try:
            from insar_prep.core.enums import DemDataset

            valid = {d.value for d in DemDataset}
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 数据集", exc)
        if name not in valid:
            return _error_msg(f"未知 DEM 数据集：{dataset}", "DEM004")
        self._dem_dataset = name
        return {"ok": True, "dataset": name}

    # ------------------------------------------------------ workspace / tree
    def create_workspace(self, root: str, name: str | None = None) -> dict:
        """Create the in-memory workspace from a (logical) root path + name."""
        try:
            ws = self._state.create_workspace(root, name)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "workspace_id": ws.workspace_id,
            "root": str(ws.workspace_root),
            "projects": [],
        }

    def add_project(self, name: str) -> dict:
        """Create a project under the current workspace."""
        try:
            project = self._state.add_project(name)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "project_id": project.project_id,
            "name": project.project_name,
            "safe_name": project.safe_name,
        }

    def select_project(self, project_id: str) -> dict:
        """Make an existing project current (so new regions attach to it)."""
        try:
            project = self._state.select_project(project_id)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "project_id": project.project_id,
            "name": project.project_name,
            "safe_name": project.safe_name,
        }

    def add_region(self, name: str) -> dict:
        """Create a region under the current project and make it current."""
        try:
            region = self._state.add_region(name)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "region_id": region.region_id,
            "name": region.region_name,
            "safe_name": region.region_safe_name,
        }

    def select_region(self, region_id: str) -> dict:
        """Make an existing region current."""
        try:
            region = self._state.select_region(region_id)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "region_id": region.region_id,
            "name": region.region_name,
            "safe_name": region.region_safe_name,
        }

    # --------------------------------------------------------------- 1. AOI
    def set_region_aoi_bbox(
        self, west: float, east: float, south: float, north: float
    ) -> dict:
        """Bind a manual bbox (W/E/S/N) as the current region's processing AOI."""
        try:
            from insar_prep.processing.aoi import make_processing_aoi_from_bbox
        except Exception as exc:  # noqa: BLE001 - optional geo deps
            return _missing_dep("AOI 处理", exc)
        try:
            aoi = make_processing_aoi_from_bbox(
                float(west), float(east), float(south), float(north)
            )
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError etc.
            return _error_msg(_format_validation(exc), "AOI001")
        try:
            region = self._state.set_current_region_aoi(aoi)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    def set_region_aoi_file(self, path: str) -> dict:
        """Bind an AOI loaded from a vector file (shp/kml/kmz/geojson/json)."""
        try:
            from insar_prep.processing.aoi_vector import load_aoi_from_file
        except Exception as exc:  # noqa: BLE001 - optional geo deps
            return _missing_dep("矢量文件导入", exc)
        try:
            aoi = load_aoi_from_file(path)
            region = self._state.set_current_region_aoi(aoi)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001 - file/parse errors
            return _error_msg(str(exc), "AOI001")
        return {
            "ok": True,
            "aoi": _dump(aoi),
            "region_id": region.region_id,
            "region_name": region.region_name,
        }

    # ------------------------------------------------------------ 2. SCENES
    def import_scenes_text(self, text: str) -> dict:
        """Parse pasted granule names / URLs (one per line) into the region."""
        try:
            from insar_prep.providers.asf.scene_parser import (
                deduplicate_scenes,
                parse_scene_name,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("场景解析", exc)
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines:
            return _error_msg("请粘贴至少一个 Sentinel-1 IW SLC 颗粒名或下载链接", "ASF001")
        scenes = []
        errors: list[dict] = []
        for line in lines:
            try:
                scenes.append(parse_scene_name(line))
            except InsarPrepError as exc:
                errors.append({"line": line, "error": str(exc)})
        if not scenes:
            return {
                "ok": False,
                "error": "未能解析出任何有效的 Sentinel-1 IW SLC 场景",
                "code": "ASF001",
                "errors": errors,
            }
        unique, dups = deduplicate_scenes(scenes)
        try:
            region = self._state.set_current_region_scenes(unique)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in region.scenes],
            "duplicates": dups,
            "errors": errors,
        }

    def import_scenes_file(self, path: str) -> dict:
        """Parse an ASF cart file (.py/.txt/.csv/.geojson/.json) into the region."""
        try:
            from insar_prep.providers.asf.cart_parser import parse_asf_cart_file
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("购物车解析", exc)
        try:
            scenes = parse_asf_cart_file(path)
            unique, dups = deduplicate_scenes(scenes)
            region = self._state.set_current_region_scenes(unique)
        except InsarPrepError as exc:
            return _error(exc)
        return {
            "ok": True,
            "scenes": [_scene_row(s) for s in region.scenes],
            "duplicates": dups,
            "errors": [],
        }

    def check_scenes(self) -> dict:
        """Run the consistency check on the current region's scenes."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        try:
            from insar_prep.quality.scene_checks import check_scene_collection
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("一致性核查", exc)
        try:
            report = check_scene_collection(region.scenes)
        except InsarPrepError as exc:
            return _error(exc)
        return {"ok": True, "report": _dump(report)}

    # ----------------------------------------------------------- 3. DOWNLOAD
    def plan_asf_download(self, output_dir: str = "") -> dict:
        """Build (dry-run) the ASF SLC download plan for the region's scenes."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if not region.scenes:
            return _error_msg("请先在『影像核查』导入场景", "ASF001")
        try:
            from insar_prep.providers.asf.download_plan import build_asf_download_plan
            from insar_prep.providers.asf.scene_parser import deduplicate_scenes
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("ASF 下载规划", exc)
        out = output_dir.strip() or self._default_output()
        try:
            unique, _ = deduplicate_scenes(region.scenes)
            plan = build_asf_download_plan(
                scenes=unique,
                output_dir=out,
                region_safe_name=region.region_safe_name,
            )
        except InsarPrepError as exc:
            return _error(exc)
        return {"ok": True, "plan": _dump(plan)}

    def plan_dem_download(self, output_dir: str = "", dataset: str = "COP30") -> dict:
        """Build + validate (dry-run) the DEM request plan for the region AOI."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        try:
            from insar_prep.providers.dem.planner import (
                create_dem_request_plan,
                validate_dem_request_plan,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 下载规划", exc)
        if dataset.strip():
            self._dem_dataset = dataset.strip().upper()
        out = output_dir.strip() or self._default_output()
        try:
            plan = create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_root=out,
                dataset=self._dem_dataset,
                **self._dem_source_kwargs(),
            )
            report = validate_dem_request_plan(plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM004")
        return {"ok": True, "plan": _dump(plan), "report": _dump(report)}

    def plan_gacos_request(self, output_dir: str = "") -> dict:
        """Build + validate (dry-run) the GACOS request plan for the region."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        if not region.scenes:
            return _error_msg("GACOS 需要场景日期，请先导入影像", "GAC001")
        try:
            from insar_prep.providers.gacos.planner import (
                create_gacos_request_plan,
                validate_gacos_request_plan,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("GACOS 规划", exc)
        out = output_dir.strip() or self._default_output()
        try:
            plan = create_gacos_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                scenes=region.scenes,
                output_root=out,
            )
            report = validate_gacos_request_plan(plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "GAC001")
        return {"ok": True, "plan": _dump(plan), "report": _dump(report)}

    def get_credential_status(self) -> dict:
        """Return privacy-safe credential status for ASF / OpenTopo / GACOS."""

        def _safe(loader) -> str:
            try:
                fn = loader()
            except Exception:  # noqa: BLE001
                return "unavailable"
            try:
                return fn()
            except Exception:  # noqa: BLE001 - keyring missing or backend error
                return "unavailable"

        def _asf():
            from insar_prep.providers.asf.credentials import stored_credential_status

            return stored_credential_status

        def _dem():
            from insar_prep.providers.dem.credentials import stored_api_key_status

            return stored_api_key_status

        def _gacos():
            from insar_prep.providers.gacos.credentials import stored_gacos_email_status

            return stored_gacos_email_status

        return {
            "ok": True,
            "earthdata": _safe(_asf),
            "opentopography": _safe(_dem),
            "gacos": _safe(_gacos),
        }

    # ------------------------------------------------------- 4. DEM CONVERT
    def plan_dem_conversion(self, output_dir: str = "") -> dict:
        """Auto-detect + validate (dry-run) the vertical-datum conversion.

        The method (whether to convert at all, and which geoid model) is derived
        from the session's DEM dataset; the user never picks it. Some datasets are
        already ellipsoidal, in which case no conversion is needed.
        """
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        if region.aoi is None or region.aoi.bbox is None:
            return _error_msg("请先在『区域 AOI』设置处理范围（bbox）", "AOI001")
        try:
            from insar_prep.providers.dem.conversion_planner import (
                create_dem_conversion_plan,
                validate_dem_conversion_plan,
            )
            from insar_prep.providers.dem.planner import create_dem_request_plan
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("DEM 转换规划", exc)
        out = output_dir.strip() or self._default_output()
        try:
            request_plan = create_dem_request_plan(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                processing_aoi=region.aoi,
                output_root=out,
                dataset=self._dem_dataset,
                **self._dem_source_kwargs(),
            )
            conv_plan = create_dem_conversion_plan(request_plan)
            report = validate_dem_conversion_plan(conv_plan)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "DEM004")
        return {
            "ok": True,
            "dataset": self._dem_dataset,
            "auto": _conversion_summary(conv_plan),
            "plan": _dump(conv_plan),
            "report": _dump(report),
        }

    # ----------------------------------------------------------- 5. REPORT
    def generate_report(self, output_dir: str = "") -> dict:
        """Generate the five-file data-preparation report set for the region."""
        region = self._state.current_region()
        if region is None:
            return _error_msg("请先创建或选择区域", "GUI002")
        out = output_dir.strip() or self._default_output()
        if not out:
            return _error_msg("请提供报告输出目录", "GUI003")
        try:
            from insar_prep.reporting.generator import (
                build_data_preparation_report,
                save_report,
            )
            from insar_prep.reporting.html import (
                html_report_path_for,
                save_report_html,
            )
            from insar_prep.reporting.manifest import (
                build_manifest_rows,
                manifest_path_for,
                write_manifest_csv,
            )
            from insar_prep.reporting.warnings import (
                build_warning_rows,
                warnings_path_for,
                write_warnings_csv,
            )
        except Exception as exc:  # noqa: BLE001
            return _missing_dep("报告生成", exc)

        gathered = self._gather_reports(region, out)
        ws = self._state.workspace
        try:
            Path(out).mkdir(parents=True, exist_ok=True)
            report = build_data_preparation_report(
                workspace_id=ws.workspace_id if ws is not None else None,
                project_id=self._state.current_project_id,
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
            )
            output = save_report(report, out)
            reports_dir = output.json_path.parent

            html_path = html_report_path_for(reports_dir, region.region_safe_name)
            save_report_html(report, html_path)

            manifest_path = manifest_path_for(reports_dir, region.region_safe_name)
            manifest_rows = build_manifest_rows(
                region_id=region.region_id,
                region_safe_name=region.region_safe_name,
                report=report,
                scenes=region.scenes,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
                json_report_path=output.json_path,
                markdown_report_path=output.markdown_path,
                manifest_csv_path=manifest_path,
            )
            write_manifest_csv(manifest_path, manifest_rows)

            warnings_path = warnings_path_for(reports_dir, region.region_safe_name)
            warning_rows = build_warning_rows(
                region_safe_name=region.region_safe_name,
                scene_check_report=gathered["scene_check"],
                dem_planning_report=gathered["dem_planning"],
                dem_conversion_report=gathered["dem_conversion"],
                gacos_planning_report=gathered["gacos_planning"],
            )
            write_warnings_csv(warnings_path, warning_rows)
        except InsarPrepError as exc:
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_msg(str(exc), "REP001")

        return {
            "ok": True,
            "report": _dump(report),
            "reports_dir": str(reports_dir),
            "included": [k for k, v in gathered.items() if v is not None],
            "paths": {
                "json": str(output.json_path),
                "markdown": str(output.markdown_path),
                "html": str(html_path),
                "manifest": str(manifest_path),
                "warnings": str(warnings_path),
            },
        }

    # --------------------------------------------------------------- helpers
    def _default_output(self) -> str:
        ws = self._state.workspace
        return str(ws.workspace_root) if ws is not None else ""

    def _gather_reports(self, region: Any, out: str) -> dict:
        """Auto-collect every sub-report the current state allows (best-effort).

        Beginner-friendly: the report consolidates scene-check, DEM planning, DEM
        conversion and GACOS planning automatically; the user does not wire each
        one. Any stage that is not yet possible (no AOI / no scenes / missing dep)
        is simply omitted rather than failing the whole report.
        """
        gathered: dict = {
            "scene_check": None,
            "dem_planning": None,
            "dem_conversion": None,
            "gacos_planning": None,
        }
        if region.scenes:
            try:
                from insar_prep.quality.scene_checks import check_scene_collection

                gathered["scene_check"] = check_scene_collection(region.scenes)
            except Exception:  # noqa: BLE001
                pass
        if region.aoi is not None and region.aoi.bbox is not None:
            try:
                from insar_prep.providers.dem.conversion_planner import (
                    create_dem_conversion_plan,
                    validate_dem_conversion_plan,
                )
                from insar_prep.providers.dem.planner import (
                    create_dem_request_plan,
                    validate_dem_request_plan,
                )

                plan = create_dem_request_plan(
                    region_id=region.region_id,
                    region_safe_name=region.region_safe_name,
                    processing_aoi=region.aoi,
                    output_root=out,
                    dataset=self._dem_dataset,
                    **self._dem_source_kwargs(),
                )
                gathered["dem_planning"] = validate_dem_request_plan(plan)
                gathered["dem_conversion"] = validate_dem_conversion_plan(
                    create_dem_conversion_plan(plan)
                )
            except Exception:  # noqa: BLE001
                pass
            if region.scenes:
                try:
                    from insar_prep.providers.gacos.planner import (
                        create_gacos_request_plan,
                        validate_gacos_request_plan,
                    )

                    gplan = create_gacos_request_plan(
                        region_id=region.region_id,
                        region_safe_name=region.region_safe_name,
                        processing_aoi=region.aoi,
                        scenes=region.scenes,
                        output_root=out,
                    )
                    gathered["gacos_planning"] = validate_gacos_request_plan(gplan)
                except Exception:  # noqa: BLE001
                    pass
        return gathered

    def _dem_source_kwargs(self) -> dict:
        """Auto-derive the dataset's native vertical datum for the planner.

        This is what makes already-ellipsoidal datasets (SRTMGL1_E / AW3D30_E)
        skip conversion instead of being wrongly converted from EGM2008.
        """
        try:
            from insar_prep.core.enums import VerticalDatum
            from insar_prep.providers.dem.converter import (
                dataset_source_vertical_datum,
            )
        except Exception:  # noqa: BLE001
            return {}
        src = dataset_source_vertical_datum(self._dem_dataset)
        if src == VerticalDatum.UNKNOWN:
            return {}
        return {"source_vertical_datum": src}


def _format_validation(exc: Exception) -> str:
    """Turn a pydantic ValidationError (or any error) into a short message."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            msgs = [str(e.get("msg", "")).strip() for e in errors()]
            msgs = [m for m in msgs if m]
            if msgs:
                return "；".join(dict.fromkeys(msgs))
        except Exception:  # noqa: BLE001
            pass
    return str(exc) or "无效的坐标范围"


def _conversion_summary(conv_plan: Any) -> dict:
    """Beginner-friendly, auto-derived description of the conversion decision."""
    source = str(getattr(conv_plan, "source_vertical_datum", ""))
    target = str(getattr(conv_plan, "target_vertical_datum", ""))
    requires = bool(getattr(conv_plan, "requires_conversion", False))
    requires_geoid = bool(getattr(conv_plan, "requires_geoid", False))
    geoid = None
    for step in getattr(conv_plan, "steps", []) or []:
        if getattr(step, "geoid_model", None):
            geoid = str(step.geoid_model)
            break
    if not requires:
        message = (
            f"该 DEM 高程基准已为 {source}（椭球高），无需转换，"
            "直接复制为 SARscape 就绪 DEM。"
        )
    elif requires_geoid and geoid:
        message = (
            f"检测到高程基准为 {source}（正高），将自动转换为 {target}，"
            f"采用大地水准面模型 {geoid}（系统自动选择）。"
        )
    else:
        message = f"将自动把高程基准从 {source} 转换为 {target}。"
    return {
        "requires_conversion": requires,
        "requires_geoid": requires_geoid,
        "source": source,
        "target": target,
        "geoid_model": geoid,
        "message": message,
    }


def _scene_row(scene: Any) -> dict:
    """Pick the table-relevant, JSON-safe fields from a Scene."""
    d = scene.model_dump(mode="json")
    return {
        "scene_id": d.get("scene_id"),
        "platform": d.get("platform"),
        "product_type": d.get("product_type"),
        "beam_mode": d.get("beam_mode"),
        "polarization": d.get("polarization"),
        "acquisition_datetime": d.get("acquisition_datetime"),
        "absolute_orbit": d.get("absolute_orbit"),
        "relative_orbit": d.get("relative_orbit"),
        "orbit_direction": d.get("orbit_direction"),
        "has_url": bool(d.get("url")),
    }
