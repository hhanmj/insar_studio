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

### Changed

- `insar-prep prepare` (Task 015a) now writes a concise confirmation to stdout
  on success (the JSON and Markdown report paths) via `sys.stdout.write` (still
  no `print()`); the report content, exit-code policy, `--help`/`--version`, and
  the `07_reports` / `<region_safe_name>_data_preparation_report.{json,md}`
  output paths are unchanged.
- `insar-prep prepare` (Task 016) gained an optional `--orbit-dir` flag: when
  given, it scans the local directory for Sentinel-1 `.EOF` orbit files, matches
  them against the parsed scenes, and adds an "Orbit matching" section to the
  report (matched/unmatched counts and issues). A missing orbit directory exits
  non-zero; a directory with no matching EOFs still produces a report with an
  orbit section flagging the unmatched scenes. Without `--orbit-dir` the Task 015
  behavior is unchanged (no orbit section). Still offline; no orbit downloads,
  no `sentineleof`, no new dependencies.
- `insar-prep prepare` (Task 017) gained optional DEM planning: `--dem-plan`
  with `--bbox WEST SOUTH EAST NORTH` (plus `--dem-dataset`, `--dem-provider`,
  `--dem-buffer`, `--source-vertical-datum`, `--target-vertical-datum`) builds a
  Processing AOI, an offline DEM request plan, and a DEM conversion plan, adding
  "DEM planning" and "DEM conversion" sections to the report (dataset, provider,
  request bbox, `04_dem/raw` + `04_dem/ellipsoid` + `06_sarscape_ready/
  <region_safe_name>_dem.tif` paths, datums, geoid/manual-review status).
  `--dem-plan` without `--bbox`, an invalid bbox, or a negative `--dem-buffer`
  exit non-zero. Without `--dem-plan` the Task 016 behavior is unchanged. No
  network, no OpenTopography/GDAL/rasterio/pyproj, no real `.tif` files, no new
  dependencies.
- `insar-prep prepare` (Task 018) gained optional GACOS request planning:
  `--gacos-plan` with `--bbox WEST SOUTH EAST NORTH` (plus `--gacos-buffer` and
  `--gacos-max-dates-per-batch`) builds a Processing AOI, extracts the unique
  acquisition dates from the parsed scenes, and produces an offline GACOS
  request plan, adding a "GACOS request planning" section to the report (total
  dates, batch count/sizes, buffered request bbox, `05_atmosphere/gacos/requests`
  output directory, `.ztd`/`.ztd.rsc` expected file patterns, manual-submission
  flag, and any missing-scene-date warnings). When both `--dem-plan` and
  `--gacos-plan` are given they reuse the same `--bbox` Processing AOI.
  `--gacos-plan` without `--bbox`, a negative `--gacos-buffer`, or a
  `--gacos-max-dates-per-batch` below 1 exit non-zero. Without `--gacos-plan`
  the Task 017 behavior is unchanged. No network, no GACOS web submission,
  scraping, browser automation, product download, or credentials; no real
  `.ztd` files are created; no new dependencies.
- `insar-prep prepare` (Task 019) gained an optional `--gacos-import-dir` flag
  (with `--bbox WEST SOUTH EAST NORTH`): it wires the existing read-only GACOS
  import checker into the workflow, comparing a local directory of
  already-downloaded GACOS products against the expected acquisition dates and
  adding a "GACOS import check" section to the report (expected/found/missing/
  extra date counts, empty-file count, and per-issue codes for missing `.ztd`/
  `.ztd.rsc`, unexpected dates, malformed filenames, and empty files). Expected
  dates come from an existing `--gacos-plan` plan when given, otherwise from a
  plan built from the parsed scene dates. A missing import directory exits
  non-zero; `--gacos-import-dir` without `--bbox` exits non-zero. Without
  `--gacos-import-dir` the Task 018 behavior is unchanged. Read-only and
  offline: it never downloads, submits, scrapes, drives a browser, reads
  accounts, stores credentials, creates the SARscape-ready atmosphere
  directory, or moves/deletes/creates user files; no new dependencies.
- End-to-end regression + quickstart docs (Task 020): a new
  `tests/e2e/test_prepare_workflow.py` drives the full offline `prepare`
  workflow through the public CLI with every optional module enabled at once
  (orbit matching, DEM planning + conversion, GACOS request planning, GACOS
  import check), asserting the JSON + Markdown `07_reports` output, all six
  module sections, that no real DEM `.tif` is created, that the GACOS products
  are never moved/deleted/modified, and — by blocking socket creation during the
  run — that the workflow is fully offline. `README.md` was rewritten with the
  project scope, `uv sync` install, base commands, minimal and full offline
  `prepare` examples, the `07_reports` output location, SARscape naming
  constraints, and an explicit "what it does not do" list. No business-module
  changes; no new dependencies.
- Packaging readiness check (Task 021): added `docs/packaging_readiness.md`
  documenting the offline-CLI packaging status, the stable
  `insar_prep.cli.main:main` entry point, runtime-dependency risks for
  PyInstaller (shapely/GEOS native libraries and pydantic-core), files that must
  not be bundled, runtime-only outputs, Windows path handling, a recommended
  Task 022 PyInstaller command, known risks, and a pre-packaging checklist.
  `.gitignore` now also ignores `*.spec` / `*.manifest`; `README.md` gained a
  Windows PowerShell example (with quoting for spaced paths) and a Packaging
  pointer; and a new end-to-end test verifies an `--output-root` that contains
  spaces. No PyInstaller run, no exe/build/dist artifacts, no business-module
  changes, and no new dependencies; the version stays `0.1.0`.
- PyInstaller packaging experiment (Task 022): added
  `packaging/insar_prep_entry.py` (a thin, package-external launcher that calls
  `insar_prep.cli.main:main`), `scripts/build_windows_exe.ps1` (runs the quality
  gate, cleans old artifacts, builds a one-file exe, and runs exe smoke tests),
  and `tests/unit/test_packaging_entry.py`. `pyinstaller` was added as a **dev**
  dependency (no runtime dependency change); `uv.lock` was updated. A local
  `dist/insar-prep.exe` (~28 MB) builds successfully and its `--help` /
  `--version` / `prepare --help` plus an offline `prepare` run (JSON + Markdown
  report, no network, no `.tif`) all pass. Build artifacts (`build/`, `dist/`,
  `*.spec`, `*.exe`) stay git-ignored and are never committed;
  `docs/packaging_readiness.md` records the build result and follow-ups. No
  business-module changes; no new runtime dependencies.
- Windows exe smoke-test package (Task 023): added
  `scripts/make_windows_smoke_package.ps1`, which assembles a local
  `smoke_package/insar_prep_windows_smoke/` containing the built
  `insar-prep.exe`, small offline sample inputs (ASF URL cart, orbit `.EOF`
  files, GACOS `.ztd`/`.ztd.rsc`), a `README_SMOKE_TEST.md`, and a
  `run_smoke_test.ps1` that exercises the full offline `prepare` workflow and
  verifies the JSON + Markdown reports, no `.tif`, and untouched GACOS inputs.
  `docs/windows_exe_smoke_test.md` documents how to generate and run it.
  `smoke_package/` is git-ignored and never committed (only the generator script
  and docs are). Offline only: no GUI, installer, release, upload, or network; no
  business-module changes; no new dependencies.
- v0.1.0 offline CLI MVP release readiness (Task 024): added
  `docs/release_readiness_v0_1_0.md` capturing the version status (stays `0.1.0`),
  the supported feature list, the explicit not-supported list, a release
  checklist (quality gate, CLI surface, repository-hygiene and credential
  `git ls-files` checks), a documentation-consistency summary, and a reference-only
  tag suggestion (`v0.1.0-offline-cli`) that is intentionally **not** executed.
  `README.md` was updated to reflect that a one-file Windows exe can be built
  locally for testing (no official release/installer/GUI yet) and to link the
  release-readiness and Windows smoke-test docs; `.gitignore` was hardened with
  additional archive and remote-sensing data patterns. Documentation/readiness
  only: no business-module, test-logic, CLI, or `pyproject` version changes; no
  new dependencies; no exe / zip / smoke package generated; no real release, tag,
  or upload; the full `pytest`, `ruff check`, and `ruff format --check` quality
  gate stays green.
- `insar-prep prepare` (Task 026) now also writes a flat `manifest.csv` next to
  the JSON + Markdown report in `07_reports`, named
  `<region_safe_name>_manifest.csv`. A new offline `src/insar_prep/reporting/
  manifest.py` adds `ManifestRow`, `build_manifest_rows`, `write_manifest_csv`,
  and `manifest_path_for` (standard-library `csv` only; no new dependencies). The
  manifest has the fixed columns
  `section,item_type,item_id,item_name,status,path,value,notes` and inventories
  the workflow (region, generated time), parsed scenes, orbit matches, DEM
  request/conversion plans, GACOS request dates and import-check dates, and the
  generated report files; optional modules that were not run contribute a single
  `SKIPPED` row. It reuses the objects already built during the run (no
  re-parsing, re-scanning, or downloads), writes every cell credential-masked via
  `mask_text`, uses `newline=""` for cross-platform-stable CSV, and raises
  `ReportError` (`REP001`) on write failure. The success stdout now also prints
  the `Manifest:` path; `README.md` documents the new output. No business-module,
  CLI-flag, or `pyproject` version changes; the version stays `0.1.0`.
- Windows exe smoke test verifies the manifest output (Task 027): rebuilt the
  one-file `dist/insar-prep.exe` from the current code with
  `scripts/build_windows_exe.ps1` (full quality gate green; exe `--version` still
  `insar-prep 0.1.0`; ~28 MB) so the frozen exe now carries the Task 026
  `manifest.csv`. `scripts/make_windows_smoke_package.ps1` was extended so the
  generated `run_smoke_test.ps1` captures the `prepare` stdout and additionally
  asserts: stdout reports a `Manifest:` path; `<region>_manifest.csv` exists in
  `07_reports`; the manifest's first line is the fixed header
  `section,item_type,item_id,item_name,status,path,value,notes`; and the manifest
  inventories the `workflow`, `scene`, `orbit`, `dem`, `gacos`, and `report`
  sections (alongside the existing no-`.tif` and untouched-GACOS-input checks).
  `docs/windows_exe_smoke_test.md` and `docs/packaging_readiness.md` document the
  manifest verification. Offline only; no business-module, CLI, test-logic, or
  `pyproject` version changes; no new dependencies; build/`dist`/`*.spec`/`*.exe`
  and `smoke_package/` stay git-ignored and uncommitted.
- `insar-prep prepare` (Task 028) now also writes a `warnings.csv` next to the
  JSON + Markdown report and `manifest.csv` in `07_reports`, named
  `<region_safe_name>_warnings.csv`. A new offline
  `src/insar_prep/reporting/warnings.py` adds `WarningRow`, `build_warning_rows`,
  `write_warnings_csv`, and `warnings_path_for` (standard-library `csv` only; no
  new dependencies). Unlike the full `manifest.csv` inventory, `warnings.csv` is a
  focused problem summary with the fixed columns
  `severity,section,item_type,item_id,item_name,code,message,path,action`: it
  aggregates only the `WARNING`/`ERROR` issues from the scene, orbit, DEM, and
  GACOS sub-reports (plus the `SCENE_COVERAGE_NOT_CHECKED` limitation note),
  excludes `OK`/selection/"ready" `INFO` notes, and adds an `action` hint per row;
  when nothing is wrong it writes a single `INFO` "no warnings" summary row. It
  reuses the objects already built during the run (no re-parsing, re-scanning, or
  downloads), masks every cell via `mask_text`, uses `newline=""` for
  cross-platform-stable CSV, and raises `ReportError` (`REP001`) on write failure.
  The success stdout now also prints the `Warnings:` path; the Windows smoke test
  (`scripts/make_windows_smoke_package.ps1` → `run_smoke_test.ps1`) and
  `docs/windows_exe_smoke_test.md` verify `warnings.csv` and its header; `README.md`
  documents the new output. No business-module, CLI-flag, or `pyproject` version
  changes; the version stays `0.1.0`.
- `insar-prep prepare` (Task 029) gained GeoJSON / WKT Processing AOI import: a
  new offline `src/insar_prep/processing/aoi_import.py` (`load_aoi_from_geojson`,
  `load_aoi_from_wkt`, `geometry_to_processing_aoi`) builds a Processing AOI from
  a GeoJSON file (a `Polygon`/`MultiPolygon` geometry, a `Feature`, or a
  `FeatureCollection` — multiple features are merged via `shapely.ops.unary_union`
  and their combined bounds used) or a WKT `POLYGON`/`MULTIPOLYGON` string, using
  only the standard-library `json` plus the existing `shapely` (no new
  dependencies; no geopandas/fiona/rasterio/pyproj/GDAL). The `prepare` CLI added
  `--aoi-geojson PATH` and `--aoi-wkt WKT`, mutually exclusive with `--bbox` and
  with each other (argparse rejects any combination with exit code 2); the
  imported geometry's bounds become the Processing AOI bbox and the existing
  Download-AOI buffer logic is unchanged. WGS84 lon/lat (`EPSG:4326`) only: a
  non-EPSG:4326 GeoJSON `crs`, out-of-range coordinates, an empty/invalid or
  unsupported geometry (points/lines/`GeometryCollection`), a missing file, or
  invalid JSON/WKT raise `InputValidationError` (`AOI001`) and the CLI exits `2`;
  `shapefile`/`KML`/`GeoPackage` inputs and coordinate transforms remain
  unsupported. Added `tests/unit/test_aoi_import.py` and extended
  `tests/e2e/test_prepare_workflow.py` (GeoJSON/WKT `prepare` runs plus
  mutual-exclusion exit-`2` checks); `README.md` documents the new AOI options. No
  changes to the ASF parser, DEM/GACOS/orbit modules, reporting manifest/warnings,
  queue, or core models; the `--bbox` behavior is unchanged; the version stays
  `0.1.0`.
- Windows exe smoke test verifies the AOI import (Task 030): rebuilt the one-file
  `dist/insar-prep.exe` from the current code with `scripts/build_windows_exe.ps1`
  (full quality gate green; exe `--version` still `insar-prep 0.1.0`; ~28 MB) so
  the frozen exe now carries the Task 029 `--aoi-geojson` / `--aoi-wkt` AOI import.
  `scripts/make_windows_smoke_package.ps1` was extended to also write an EPSG:4326
  Polygon `input/aoi.geojson` sample, and the generated `run_smoke_test.ps1` now
  asserts `prepare --help` advertises `--bbox`/`--aoi-geojson`/`--aoi-wkt` and runs
  the offline `prepare` workflow three times — once per AOI source (`--bbox`,
  `--aoi-geojson`, `--aoi-wkt`) — checking for each run the four report files
  (JSON, Markdown, `manifest.csv`, `warnings.csv`), the fixed manifest/warnings
  headers, the manifest section coverage, and `JSON:`/`Markdown:`/`Manifest:`/
  `Warnings:` stdout lines, alongside the existing no-`.tif` and
  untouched-GACOS-input checks. `docs/windows_exe_smoke_test.md` and
  `docs/packaging_readiness.md` document the AOI smoke coverage. Offline only; no
  business-module, CLI, test-logic, or `pyproject` version changes; no new
  dependencies; build/`dist`/`*.spec`/`*.exe` and `smoke_package/` stay
  git-ignored and uncommitted.
- `insar-prep prepare` (Task 031) now also writes a self-contained HTML report
  next to the JSON + Markdown report, `manifest.csv`, and `warnings.csv` in
  `07_reports`, named `<region_safe_name>_data_preparation_report.html`. A new
  offline `src/insar_prep/reporting/html.py` adds `render_report_html`,
  `save_report_html`, and `html_report_path_for` (standard-library `html.escape`
  plus string building only — no Jinja2/Markdown/pandas/plotly; no new
  dependency). The HTML is a static HTML5 page (UTF-8, inline minimal CSS, no
  external CSS/JS/CDN, no network, no PDF): a header, summary cards
  (status/sections/errors/warnings), and one section per module (Scene
  consistency, Orbit matching, DEM planning/conversion, GACOS request planning,
  GACOS import check, Next actions) with key-value items and an issue table. It
  reuses the same `DataPreparationReport` object (no business logic re-run),
  HTML-escapes every user-controllable value, and is credential-masked via
  `mask_text` before writing. The success stdout now also prints the `HTML:` path
  (order: JSON, Markdown, HTML, Manifest, Warnings); the Windows smoke test
  (`scripts/make_windows_smoke_package.ps1` → `run_smoke_test.ps1`) verifies the
  HTML across all three AOI runs, and `docs/windows_exe_smoke_test.md`,
  `docs/packaging_readiness.md`, and `README.md` document the new output. No
  business-module changes (ASF/AOI/DEM/GACOS/orbit/queue/core models and
  `manifest.py`/`warnings.py` untouched); no CLI-flag or `pyproject` version
  changes; the version stays `0.1.0`.
- Credential-safe design for future ASF downloads (Task 032), documented in
  `docs/asf_download_credential_design.md`. **Design only — nothing is
  implemented**: no downloader, login, session, or credential read; no
  `asf_search`/`keyring`/HTTP dependency; no `.netrc`/`.env`/env-var/prompt
  access; no new CLI argument; and no change to the `prepare` workflow. The
  document specifies the scope/non-goals, a threat model (keeping
  username/password/token/cookie/session out of Git, logs, JSON/Markdown/HTML
  reports, `manifest.csv`/`warnings.csv`, tracebacks, shell history, the smoke
  package, and CI logs, and large SLC/zip/SAFE files out of the repo), the
  binding credential-handling principles (no plaintext credentials in the
  project dir; `dry-run` default; explicit opt-in for real download), the
  proposed credential sources (OS keyring / env vars / interactive prompt /
  user-managed external `.netrc`; `.env` is never the default and never
  committed), the forbidden practices, the redaction rules (reuse `mask_secret`
  / `mask_text` / `_MaskingFilter`, plus the known `_SECRET_KEY_RE` gaps to
  close — bearer tokens, cookie values, presigned S3/data-pool query params, URL
  userinfo, `.netrc` lines), the download modes (`dry-run` default vs explicit
  `real`), dry-run / real-download / file-integrity / error-handling behavior, a
  CLI proposal (recommend dedicated `plan-asf-downloads` / `download-asf`
  subcommands over folding into `prepare`), an offline-by-default test strategy
  (fake credentials, socket-monkeypatched, opt-in real-download marker excluded
  from CI), and a Task 033–036 breakdown (with real download deferred to a later,
  separately-authorized task). `README.md` notes that real ASF download is not
  yet implemented and links the design. No changes to `src/`, `tests/`,
  `pyproject.toml`, `uv.lock`, or scripts; no new dependency; the version stays
  `0.1.0`.
- `insar-prep plan-asf-downloads` (Task 033): an offline ASF SLC download
  *dry-run planner*. It reads a local ASF cart and writes
  `asf_download_plan.json` + `asf_download_plan.csv` under
  `<output-dir>/asf_download_plan/`, listing per scene the platform, acquisition
  time, product/beam/polarization, `url_status`, `expected_filename`, intended
  `<output-dir>/02_slc/<expected_filename>` path, a `PLANNED`/`MISSING_URL`
  status, and a `credential_required` flag (always `yes`). New
  `src/insar_prep/providers/asf/download_plan.py` adds `build_asf_download_plan`,
  `write_asf_download_plan`, and `asf_download_plan_paths` (standard-library
  `csv` + the existing pydantic/`mask_text` only — no new dependency). It never
  downloads data, contacts ASF/Earthdata, reads credentials, or creates the
  `02_slc/` directory or any `.zip`/`.SAFE`; URLs, query strings, and tokens are
  never written to the plan (only a present/missing flag and the granule-derived
  filename), and every cell is `mask_text`-masked before writing. The CSV header
  is fixed
  (`scene_id,platform,acquisition_datetime,product,beam,polarization,url_status,expected_filename,planned_path,status,credential_required,notes`).
  Missing URLs are reported as `MISSING_URL` with exit code `0` unless
  `--require-urls` is passed (then the plan is still written but the command exits
  non-zero). The success stdout prints the JSON + CSV plan paths (via
  `sys.stdout.write`, no `print()`). Added `tests/unit/test_asf_download_plan.py`
  and `tests/e2e/test_asf_download_plan_cli.py` (socket-monkeypatched offline
  checks, header/round-trip, no-leak, and no-large-file assertions); `README.md`
  documents the new subcommand. No business-module changes beyond the new ASF
  planner and CLI wiring; no `pyproject` version change; the version stays
  `0.1.0`.
- Credential redaction hardening (Task 034). Strengthened the existing
  `mask_text` in `src/insar_prep/core/logging.py` (still the single source of
  truth behind the logging `_MaskingFilter` and every report/manifest/warnings/
  HTML/ASF-plan writer) so it now also masks: `Authorization` headers (with or
  without a `Bearer`/`Basic`/`Token`/`Negotiate` scheme, keeping only the scheme
  word), bare `Bearer <token>` strings, `Cookie` headers (whole payload), and a
  broader key set — `session`/`sessionid`, `access_token`/`refresh_token`/
  `id_token`, `credentials`, and presigned-URL params (`X-Amz-Signature`,
  `X-Amz-Credential`, `X-Amz-Security-Token`, `Signature`, `AWSAccessKeyId`) — in
  plain, `key=value`, JSON, and URL-query forms, with a value class that includes
  `+`/`/`/`=` so base64 tokens and signatures are fully masked. A required `[:=]`
  separator after each keyword means Windows paths (e.g.
  `C:\...\tokens\file.zip`) are never mis-redacted. Added
  `tests/unit/test_redaction.py` (fake secrets only; no real credentials, no
  environment reads, no network) proving redaction across `mask_text` forms and
  the report JSON/Markdown/HTML, `manifest.csv`, and `warnings.csv` writers, plus
  Windows-path and non-secret-text preservation; existing `test_logging.py`
  behavior is unchanged. `README.md` notes the hardened redaction. No new
  dependency; no CLI change; the version stays `0.1.0`.
- Fake ASF downloader interface and no-network guards (Task 035). New
  `src/insar_prep/providers/asf/downloader.py` defines the downloader interface a
  future real downloader will implement (`AsfDownloader` protocol,
  `DownloadRequest`, `DownloadResult`, `DownloadOutcome`) plus a
  `FakeAsfDownloader` for offline tests of success/failure/interrupted paths. The
  fake never opens a socket, reads credentials, or writes a real archive: by
  default it writes nothing, and with `write_placeholder=True` it writes only a
  tiny `.fake`/`.part` text marker (never `.zip`/`.SAFE`). `RealAsfDownloader` is
  a deliberate `NotImplementedError` stub so real, credentialed download can
  never run accidentally — it stays a separate, later, user-authorized task.
  Added `tests/unit/test_asf_fake_downloader.py` and
  `tests/e2e/test_no_network_guards.py` (socket-monkeypatched) proving the
  planner CLI and the fake downloader open no socket, that the guard itself
  blocks network access, and that no `.zip`/`.SAFE` is produced. No
  requests/aiohttp/httpx or any new dependency; no CLI change; the version stays
  `0.1.0`.
- Windows exe smoke test for the ASF dry-run planner (Task 036). The rebuilt
  one-file `dist/insar-prep.exe` now carries the `plan-asf-downloads` subcommand;
  `scripts/make_windows_smoke_package.ps1` extends the generated
  `run_smoke_test.ps1` to assert `plan-asf-downloads --help` advertises
  `--cart`/`--output-dir`, run one offline `plan-asf-downloads` dry-run, and
  verify its stdout reports the `JSON:`/`CSV:` plan paths, that
  `output\asf_plan\asf_download_plan\asf_download_plan.json` + `.csv` exist, that
  the plan CSV header is the fixed
  `scene_id,platform,acquisition_datetime,product,beam,polarization,url_status,expected_filename,planned_path,status,credential_required,notes`,
  that the JSON parses, and that **no `.zip`/`.SAFE`** is produced anywhere in the
  package (alongside the existing no-`.tif` and untouched-GACOS-input checks).
  `docs/windows_exe_smoke_test.md` and `docs/packaging_readiness.md` document the
  new dry-run plan smoke. Offline only; no business-module, CLI, test-logic, or
  `pyproject` version changes; no new dependency; build/`dist`/`*.spec`/`*.exe`
  and `smoke_package/` stay git-ignored and uncommitted.
- PySide6 GUI skeleton (Task 037): a new **optional** desktop GUI behind the
  `gui` extra. A new `src/insar_prep/gui/` package adds the application launcher
  (`app.py`: `create_application` / `launch_gui`), the `MainWindow`
  (`main_window.py`) four-zone shell, and four placeholder widgets — `widgets/
  project_tree.py` (Workspace / Project / Region tree), `widgets/workflow_steps.py`
  (Region workflow steps), `widgets/queue_log_panel.py` (task queue + read-only
  log), and `widgets/status_bar.py` (warnings/errors bar starting at `Ready`).
  Shared plain constants (`WINDOW_TITLE`, `WORKFLOW_STEPS`,
  `PYSIDE6_MISSING_MESSAGE`) live in `gui/__init__.py` so they import without
  PySide6. A new `insar-prep gui` subcommand (`cli/commands.py` + `cli/main.py`)
  launches it, checking PySide6 via `importlib.util.find_spec` *without*
  importing it: when the `gui` extra is missing it writes a clear single-line
  message tagged with the new `GUI001` error code (added to
  `core/error_codes.py`) and exits non-zero (no traceback), and the GUI modules
  are imported lazily only after that check passes. PySide6 is an optional dependency
  (`[project.optional-dependencies] gui = ["PySide6>=6.7"]`; `uv.lock` updated),
  so the plain CLI (`--help`, `--version`, `prepare --help`,
  `plan-asf-downloads --help`) never needs it. The GUI is a read-only skeleton:
  it holds no business logic, runs no workflow, and performs no network or
  downloads — real ASF/DEM/GACOS download and DEM vertical-datum conversion stay
  deferred. Added `tests/unit/test_gui_entry.py` (constants import without
  PySide6, subcommand registration, `--help` for every command without PySide6,
  the missing-extra error path via a monkeypatched `find_spec`, and a headless
  `offscreen` `MainWindow` smoke test that skips when PySide6 is absent); the
  existing suite stays green. `README.md` documents the GUI beta (install/launch
  and the read-only scope). No business-module changes; no version change (stays
  `0.1.0`); no exe/build/dist/spec/smoke_package generated.
- GUI Workspace / Project / Region tree binding (Task 038): the GUI left tree
  becomes a live, creatable hierarchy. A new PySide6-free
  `src/insar_prep/gui/state.py` (`GuiState`) holds the current
  `Workspace -> Project -> Region` as **existing** core models
  (`insar_prep.core.models`), deriving SARscape-safe names via
  `sarscape_safe_name` and raising coded errors (`GUI002` for a missing
  prerequisite, `GUI003` for invalid input — both added to
  `core/error_codes.py`); it persists nothing to disk and creates no data files.
  New `src/insar_prep/gui/dialogs/` adds `WorkspaceDialog` / `ProjectDialog` /
  `RegionDialog` (thin input dialogs). `widgets/project_tree.py` now renders the
  hierarchy from `GuiState` (a placeholder `Workspace` until one is created), and
  `main_window.py` gains a toolbar (*New Workspace / New Project / New Region*)
  plus guarded `apply_new_*` methods that refresh the tree and show success or
  the coded error in the bottom status bar. The GUI holds no business logic; it
  only calls existing core models/naming. Added `tests/unit/test_gui_state.py`
  (headless: create workspace/project/region, precondition `GUI002` and
  invalid-input `GUI003` errors) and `tests/unit/test_gui_project_tree.py`
  (offscreen PySide6: tree reflects state, main-window apply methods, error
  surfaced). `README.md` updated. No real downloads, no network, no DEM
  conversion; no new runtime dependency (PySide6 stays the optional `gui` extra);
  version stays `0.1.0`.
- GUI AOI input panel (Task 039): a new `src/insar_prep/gui/widgets/aoi_panel.py`
  (`AoiPanel`) adds a centre-column panel that defines the current Region's
  Processing AOI from one of three **mutually exclusive** sources — a manual
  bounding box (W/S/E/N), a GeoJSON file path, or a WKT string — selected via a
  combo box backed by a `QStackedWidget`. The panel re-implements no parsing: it
  calls the existing core interfaces `make_processing_aoi_from_bbox`,
  `load_aoi_from_geojson`, and `load_aoi_from_wkt`, wrapping bad input as a coded
  `AOI001` error. `main_window.py` now hosts the panel in a scrollable centre
  column and adds a guarded `apply_set_region_aoi` method (binds the AOI to the
  current region via `GuiState.set_current_region_aoi`, refreshes the tree so the
  region shows `[AOI set]`, and reports success or the coded error — `GUI002`
  when no region is selected — in the status bar). Added
  `tests/unit/test_gui_aoi_panel.py` (offscreen PySide6: bbox/GeoJSON/WKT build
  an AOI, invalid bbox/WKT raise `AOI001`, the main window binds the AOI or
  surfaces `GUI002`/`AOI001`) and a `set_current_region_aoi` success case in
  `tests/unit/test_gui_state.py`. No Shapefile/KML/GeoPackage, no coordinate
  transforms, no network, no downloads; no new dependency; version stays `0.1.0`;
  the CLI is unchanged.
- GUI ASF cart import and scene list (Task 040): a new
  `src/insar_prep/gui/widgets/asf_cart_panel.py` (`AsfCartPanel`) collects a local
  ASF cart path and parses it into scenes through the existing core parser
  `parse_asf_cart_file` (Vertex Python script / URL text / CSV / GeoJSON), with
  empty-path and parser failures surfaced as a coded `ASF001` error; the GUI
  re-implements no ASF parsing. A new
  `src/insar_prep/gui/widgets/scene_table.py` (`SceneTableWidget`) renders the
  parsed scenes read-only (scene id, platform, acquisition time, product, beam,
  polarization, URL status). `main_window.py` hosts both in the centre column and
  adds a guarded `apply_import_scenes` method that stores scenes on the current
  region via `GuiState.set_current_region_scenes`, fills the table, and reports
  the count (or `GUI002` when no region is selected) in the status bar. Added
  `tests/unit/test_gui_asf_cart_panel.py` (offscreen PySide6: cart parsing,
  table population, the main-window import flow, and `ASF001`/`GUI002` errors).
  No downloads, no network, no SLC files; no new dependency; version stays
  `0.1.0`; the CLI is unchanged.
- GUI scene consistency check (Task 041): a new
  `src/insar_prep/gui/widgets/scene_check_panel.py` (`SceneCheckPanel`) adds a
  *Run scene check* button plus an optional expected-polarization selector, runs
  the existing core `check_scene_collection` over the current Region's scenes
  (the GUI re-implements no checking logic), and displays the total scene count,
  the error/warning counts, and the full issue list. `main_window.py` adds a
  guarded `apply_run_scene_check` method that fetches the region's scenes
  (`GUI002` when no region is selected) and links the resulting
  `SceneCheckReport` to the bottom warnings/errors bar — showing the error count
  when there are errors, the warning count when there are warnings, or `Ready`
  when clean. Added `tests/unit/test_gui_scene_check_panel.py` (offscreen
  PySide6: totals, empty-collection error, platform-mix warning, expected
  polarization mismatch, and the main-window status linkage for error / warning /
  ready / no-region cases). No network, no downloads; no new dependency; version
  stays `0.1.0`; the CLI is unchanged.

### Release readiness

- **v0.1.0 — offline CLI MVP.** Readiness reviewed in Task 024; see
  [`docs/release_readiness_v0_1_0.md`](docs/release_readiness_v0_1_0.md). The
  version is unchanged and **no** official release is cut here. A future release
  would only need a deliberate tag plus an optional local build/publish step.

## [0.1.0] - 2026-06-18

### Added

- Initial project skeleton (Task 001).
- `pyproject.toml` with uv, hatchling build backend, ruff, and pytest configuration.
- `insar-prep` CLI entry point supporting `--help` and `--version` only.
- `src/insar_prep` package (src-layout) with a `cli` subpackage.
- Smoke tests in `tests/test_import.py`.
- GitHub Actions CI running ruff and pytest.
