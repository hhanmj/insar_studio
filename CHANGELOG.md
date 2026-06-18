# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Core data models (Task 002) under `src/insar_prep/core/`: `Workspace`,
  `Project`, `Region`, `Scene`, `Job`, `DownloadTask`, `DemProduct`,
  `AtmosphericProduct`, plus `BBox`/`Aoi`/`AoiBuffer`/`BoundaryCompliance`
  support models, built on pydantic v2.
- `core/enums.py` with status, coverage, platform, provider, AOI source, and
  vertical-datum enumerations.
- `core/serialization.py` JSON helpers (`model_to_json`, `model_from_json`,
  `save_json`, `load_json`); YAML intentionally deferred.
- Unit tests in `tests/unit/` covering enum membership, field defaults,
  validation errors (unknown fields, invalid enums/bbox/safe_name/DEM suffix),
  and JSON round-trips.
- `pydantic>=2` runtime dependency.
- SARscape-safe naming utilities (Task 003) in `src/insar_prep/core/naming.py`:
  `sarscape_safe_name`, `is_sarscape_safe_name`, and `validate_sarscape_ready_path`.
- SARscape adapter in `src/insar_prep/sar_apps/sarscape.py`:
  `ensure_sarscape_dem_name` (enforces the `_dem.tif` suffix and rejects
  `*_ellipsoid.tif`) and `sarscape_ready_dem_path`.
- Error and logging infrastructure (Task 004): `core/error_codes.py`
  (`ErrorCode` + `ERROR_CODE_MESSAGES`), `core/exceptions.py`
  (`InsarPrepError` and typed subclasses incl. `InputValidationError`,
  `ReportError`), `core/events.py` (`EventType`, `Event` with UTC ISO-8601
  timestamps), and `core/logging.py` (per-region/global file logging to
  `app.log`/`task.log`/`events.jsonl`/`errors.log` with UTF-8 and credential
  masking).
- Ruff `T20` rule enabled to forbid `print()`; application code must use the
  project logger.
- AOI input module (Task 005) in `src/insar_prep/processing/aoi.py`: manual
  bbox Processing AOIs, buffered Download AOIs, and multi-feature handling
  (`merge_features_to_one_region`, `select_feature`, `split_features_to_regions`,
  `build_regions`) plus `validate_china_boundary_compliance` (AOI003).
- Model additions for AOI: `BBox.to_polygon()`/`BBox.buffer()`, `Aoi.role`
  (`AoiRole`), `AoiFeature`, and `BoundaryCompliance.country`/
  `requires_review_number`; new `AoiRole` and `MultiFeatureMode` enums.
- `shapely>=2` runtime dependency (geometry, union, bounds; no geopandas/fiona).
- ASF cart parser (Task 006) in `src/insar_prep/providers/asf/`: local parsing
  of Vertex Python scripts (regex-only, never executed), URL text, CSV, and
  GeoJSON into Sentinel-1 SLC `Scene` lists (`parse_asf_cart_file` dispatch),
  `parse_scene_name` granule parsing, and `deduplicate_scenes`. No network,
  no `asf_search`, no credentials.

### Fixed

- Preserve Sentinel-1 product polarization codes (Task 006a): `Polarization`
  now includes `SH`/`SV`/`DH`/`DV`/`UNKNOWN`, and `parse_scene_name` keeps the
  original code so dual-pol (`DH`/`DV`) is no longer collapsed to single-pol
  (`HH`/`VV`). Added `polarization_code_to_channels` helper.

### Added (continued)

- Scene consistency checks (Task 007) in `src/insar_prep/quality/`:
  `check_scene_collection` produces a serializable `SceneCheckReport`
  (`CheckIssue`/`CheckSeverity`) covering empty input, duplicate scene_id/time,
  product/beam/polarization mismatches, mixed DH/DV and mixed platforms, missing
  URL/source, and an `coverage_not_checked` note when footprints are unavailable.
- `ProductType` gained `RAW`/`GRD`/`OCN` and `BeamMode` gained `SM`/`EW`/`WV`
  so non-SLC / non-IW inputs can be represented and flagged.
- Task queue framework (Task 008) in `src/insar_prep/queue/`: `TaskQueue` with a
  validated task state machine (pause/resume/cancel/retry, priority ordering,
  region/type filters), `summarize_job_status`, executors (`DryRunExecutor`,
  `FailingExecutor`, `TaskExecutor` protocol), and a sequential scheduler
  (`QueueRunConfig`/`QueueRunResult`). Fully offline; no real downloads.
- `DownloadTask` gained a `priority` field for queue ordering.
- Sentinel-1 orbit matching (Task 009) in `src/insar_prep/providers/orbit/`:
  `parse_orbit_filename`/`scan_orbit_directory` (local EOF parsing, no download)
  and `match_orbit_for_scene`/`match_orbits_for_scenes` preferring
  POEORB > MOEORB > RESORB (newest creation within a type), producing a
  serializable `OrbitMatchReport`. `Platform` gained `S1D`.
- DEM request planner (Task 010) in `src/insar_prep/providers/dem/`:
  `create_dem_request_plan` builds an offline `DemRequestPlan` (buffered request
  bbox, raw/ellipsoid/SARscape-ready DEM paths, planning-only `DownloadTask`),
  `validate_dem_request_plan` returns a serializable `DemPlanningReport`, and
  `create_dem_download_task` produces a PENDING DEM task. No network, no
  OpenTopography calls, no DEM download, no vertical-datum conversion.
- DEM vertical-datum conversion planner (Task 011) in
  `src/insar_prep/providers/dem/conversion_planner.py`:
  `create_dem_conversion_plan` builds an offline `DemConversionPlan` (step list
  of `VERTICAL_DATUM_CONVERSION`/`COPY_TO_SARSCAPE_READY`/`NO_OP`/
  `MANUAL_REVIEW_REQUIRED`), `validate_dem_conversion_plan` returns a
  serializable `DemConversionReport`, plus `requires_geoid_conversion` and
  `suggest_geoid_model` helpers. No GDAL/rasterio, no geoid download, no DEM
  files created.
- GACOS request planner (Task 012) in `src/insar_prep/providers/gacos/`:
  `extract_gacos_dates_from_scenes` (sorted, de-duplicated acquisition dates,
  skipping scenes with no date), `create_gacos_request_plan` builds an offline
  `GacosRequestPlan` (buffered/clamped request bbox, unique dates split into
  `GacosRequestBatch` batches by `max_dates_per_batch`, manual-submission flag,
  `05_atmosphere/gacos/requests` output directory, and `.ztd`/`.ztd.rsc`
  expected file patterns), and `validate_gacos_request_plan` returns a
  serializable `GacosPlanningReport`. No network, no GACOS web submission, no
  scraping, no browser automation, no product download, no credentials.
- GACOS import checker (Task 013) in
  `src/insar_prep/providers/gacos/import_checker.py`:
  `scan_gacos_product_directory` groups well-formed `YYYYMMDD.ztd` /
  `YYYYMMDD.ztd.rsc` files into `GacosProductFile` records (paths + sizes only,
  contents never opened), and `check_gacos_products` compares a local product
  directory against a `GacosRequestPlan` to produce a serializable
  `GacosImportCheckReport` (missing `.ztd`/`.ztd.rsc`, unexpected dates,
  malformed filenames, and empty files). Read-only and offline: it raises
  `AtmosphereProductError` (`GAC002`) for a missing directory and never moves,
  deletes, or creates user files, parses raster/`.rsc` content, downloads, or
  contacts GACOS. Small placeholder fixtures live in `tests/fixtures/gacos/`.
- Data-preparation reports (Task 014) in `src/insar_prep/reporting/`:
  `build_data_preparation_report` consolidates the scene, orbit, DEM, DEM
  conversion, and GACOS planning/import reports into a serializable
  `DataPreparationReport` (per-module `ReportSection`s plus an aggregated
  "Next actions" checklist and an overall `ready`/`ready_with_warnings`/
  `blocked` status), `render_report_markdown` renders a beginner-friendly
  Markdown view, and `save_report` writes UTF-8 JSON + Markdown to a
  SARscape-safe `07_reports` directory. All written text is credential-masked
  via `mask_text`/`mask_secret`. Offline only: no GUI, PDF, HTML, browser,
  network, or new dependencies.
- `prepare` CLI workflow (Task 015) in `src/insar_prep/cli/`: a new
  `insar-prep prepare --cart ... --region-name ... --output-root ...` command
  (with optional `--region-id`, `--require-urls`, `--expected-polarization`)
  that wires the offline pipeline ASF cart parser -> scene consistency check ->
  `DataPreparationReport` -> `save_report`, writing JSON + Markdown to
  `<output_root>/<region_safe_name>/07_reports/`. Region names are normalized
  via `sarscape_safe_name`; missing/invalid carts return a non-zero exit code.
  `--help`/`--version` are unchanged; no `print()`, no network, no new deps.

## [0.1.0] - 2026-06-18

### Added

- Initial project skeleton (Task 001).
- `pyproject.toml` with uv, hatchling build backend, ruff, and pytest configuration.
- `insar-prep` CLI entry point supporting `--help` and `--version` only.
- `src/insar_prep` package (src-layout) with a `cli` subpackage.
- Smoke tests in `tests/test_import.py`.
- GitHub Actions CI running ruff and pytest.
