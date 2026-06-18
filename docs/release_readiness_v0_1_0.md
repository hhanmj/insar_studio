# Release readiness — v0.1.0 (offline CLI MVP)

This document captures the **release-readiness** state of `insar-prep` as the
`v0.1.0 offline CLI MVP`. It is a readiness review only: it does **not** cut a
release, build or upload an executable, create a GitHub Release, or change any
business logic. Its purpose is to make a future, deliberate tag/release a simple,
well-documented step.

- Version under review: **`0.1.0`** (unchanged; see `pyproject.toml` and
  `insar_prep/__init__.py` → `__version__ = "0.1.0"`).
- Stage classifier: `Development Status :: 2 - Pre-Alpha`.
- Scope: **offline, local-only CLI**. Every command runs with no network, no
  downloads, and no GUI.

## 1. Version status

- The version stays `0.1.0`; this readiness pass does **not** bump it.
- `--version` prints `insar-prep 0.1.0` (verified via `uv run insar-prep
  --version`).
- `__version__` is a hard-coded literal, so `--version` keeps working inside a
  frozen exe (no `importlib.metadata` lookup at runtime).
- This release line is positioned to users as an **offline CLI MVP**: a data
  *preparation and quality-check* assistant that runs **before** SARscape, not a
  processing engine and not a downloader.

## 2. Supported features (what v0.1.0 does)

All features below are offline and covered by the unit + end-to-end test suite.

- **ASF cart parsing** from local files: Vertex Python scripts (regex-only, never
  executed), URL text, CSV, and GeoJSON.
- **Sentinel-1 scene parsing**: granule-name parsing into `Scene` records, with
  polarization-code preservation and de-duplication.
- **Scene consistency check**: duplicates, product/beam/polarization mismatches,
  mixed platforms, missing URL/source, and coverage notes.
- **Local orbit matching**: scans a local directory of `.EOF` files and matches
  POEORB > MOEORB > RESORB by filename only (no download).
- **DEM request plan**: offline `DemRequestPlan` with buffered request bbox and
  SARscape-ready DEM paths (planning only).
- **DEM vertical-datum conversion plan**: offline `DemConversionPlan` step list
  (planning only; no GDAL/rasterio/pyproj, no `.tif` produced).
- **GACOS request plan**: unique acquisition dates batched into request batches,
  buffered bbox, expected `.ztd` / `.ztd.rsc` patterns, manual-submission flag.
- **GACOS import check**: read-only comparison of an already-downloaded GACOS
  product directory against the expected dates (missing / extra / malformed /
  empty), never touching the user's files.
- **Reports**: consolidated JSON + Markdown `DataPreparationReport` written to
  `<output_root>/<region_safe_name>/07_reports/`, credential-masked.
- **`prepare` CLI workflow**: one command wires the whole offline pipeline,
  exposing every optional module via flags.
- **PyInstaller one-file exe smoke test** (dev-only): `scripts/build_windows_exe.ps1`
  builds a local `dist/insar-prep.exe` and smoke-tests it.
- **Windows smoke-test package generator** (dev-only):
  `scripts/make_windows_smoke_package.ps1` assembles a local, self-contained
  smoke package.

## 3. Not supported in v0.1.0 (by design)

The MVP intentionally never performs any of the following:

- Download ASF / Sentinel-1 SLC data.
- Download Sentinel-1 precise/restituted orbits.
- Call OpenTopography (or any DEM API).
- Download a real DEM.
- Perform real DEM vertical-datum (geoid) conversion.
- Submit, scrape, or automate the GACOS web service.
- Download GACOS products.
- Provide a GUI.
- Invoke SARscape (or ISCE / MintPy / SNAP).
- Produce an official installer.
- Build, sign, upload, or publish a GitHub Release.

## 4. Release checklist

Run from the repository root with the project virtual environment synced. None of
these commands touch the network beyond `uv sync` resolving declared packages.

Quality gate:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

CLI surface:

```bash
uv run insar-prep --help
uv run insar-prep --version          # expect: insar-prep 0.1.0
uv run insar-prep prepare --help
```

Optional local packaging verification (dev-only; artifacts stay git-ignored):

```bash
scripts/build_windows_exe.ps1            # builds dist/insar-prep.exe + smoke test
scripts/make_windows_smoke_package.ps1   # assembles smoke_package/ locally
# then run smoke_package/insar_prep_windows_smoke/run_smoke_test.ps1
```

Repository hygiene (all of these must return **no output**):

```bash
git status --short
git ls-files "*.exe"
git ls-files "*.zip"
git ls-files "*.tif"
git ls-files "*.SAFE"
git ls-files "*.spec"
git ls-files "build/*" "dist/*" "smoke_package/*"
```

Credential / secret check — confirm none are tracked:

```bash
git ls-files ".env" "*.env" ".netrc" "*.key" "*.token"
```

## 5. Tag suggestion (do NOT run as part of this task)

When a real release is intended (a separate, future task), an annotated tag can be
created and pushed. These commands are documented for reference only and are
**not** executed here:

```bash
git tag -a v0.1.0-offline-cli -m "v0.1.0 offline CLI MVP"
git push origin v0.1.0-offline-cli
```

## 6. Documentation consistency

- `README.md` — states the offline CLI MVP scope and boundaries, the `uv sync`
  install, the base commands, minimal and full `prepare` examples (matching the
  actual `prepare --help` flags), the `07_reports` output location, SARscape
  naming constraints, and an explicit "what it does not do" list. It links to
  this document, `docs/packaging_readiness.md`, and
  `docs/windows_exe_smoke_test.md`.
- `CHANGELOG.md` — keeps the detailed `Unreleased` history and a
  `v0.1.0 offline CLI MVP readiness` subsection for this pass. No release date is
  fabricated and no `[0.1.0]` release entry is altered beyond the existing one.
- `docs/packaging_readiness.md` — records the packaging status and the Task 022
  build result.
- `docs/windows_exe_smoke_test.md` — explains how to generate and run the local
  Windows smoke package.

## 7. Readiness summary

- Version `0.1.0`, offline CLI MVP scope confirmed.
- Quality gate green: `pytest` (full suite), `ruff check`, and
  `ruff format --check` all pass.
- No exe / zip / tif / SAFE / spec / build / dist / smoke_package / credential /
  large remote-sensing data tracked in the repository.
- A future release only needs a deliberate tag + (optional) build/publish step;
  the codebase, docs, and checklist are prepared for it.
