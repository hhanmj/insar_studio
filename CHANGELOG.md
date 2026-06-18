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

## [0.1.0] - 2026-06-18

### Added

- Initial project skeleton (Task 001).
- `pyproject.toml` with uv, hatchling build backend, ruff, and pytest configuration.
- `insar-prep` CLI entry point supporting `--help` and `--version` only.
- `src/insar_prep` package (src-layout) with a `cli` subpackage.
- Smoke tests in `tests/test_import.py`.
- GitHub Actions CI running ruff and pytest.
