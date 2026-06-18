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

## [0.1.0] - 2026-06-18

### Added

- Initial project skeleton (Task 001).
- `pyproject.toml` with uv, hatchling build backend, ruff, and pytest configuration.
- `insar-prep` CLI entry point supporting `--help` and `--version` only.
- `src/insar_prep` package (src-layout) with a `cli` subpackage.
- Smoke tests in `tests/test_import.py`.
- GitHub Actions CI running ruff and pytest.
