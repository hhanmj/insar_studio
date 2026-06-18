# InSAR Data Preparation Assistant (`insar-prep`)

A SARscape-oriented InSAR **data preparation and quality-checking assistant** for
Sentinel-1 / InSAR beginners.

- It is **not** a full InSAR processing engine and does not replace SARscape,
  ISCE, MintPy, SNAP, or ASF Vertex.
- It is a **data preparation assistant** that runs *before* SARscape: it parses
  local ASF carts, checks scene consistency, matches local precise orbits, plans
  DEM and GACOS requests, checks already-downloaded GACOS products, and writes a
  beginner-friendly data-preparation report.
- The current version is an **offline CLI MVP**: every command runs locally with
  no network, no downloads, and no GUI.

> Status: **v0.1.0 — offline CLI MVP.** The `insar-prep prepare` workflow is
> implemented end to end. A one-file Windows exe can be built *locally* for
> testing, but no official release, installer, or GUI is published yet — those are
> intentionally deferred. See
> [`docs/release_readiness_v0_1_0.md`](docs/release_readiness_v0_1_0.md) for the
> full release-readiness review and the supported / not-supported feature lists.

## Requirements

- Python 3.11
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

This creates the virtual environment and installs `insar-prep` plus its dev
tools. After syncing, run the CLI via `uv run insar-prep ...`.

## Basic commands

```bash
uv run insar-prep --help
uv run insar-prep --version
uv run insar-prep prepare --help
```

## Minimal `prepare` example

The smallest useful workflow: parse a local ASF cart, run the scene consistency
check, and write the report.

```bash
uv run insar-prep prepare \
  --cart tests/fixtures/asf/urls.txt \
  --region-name shiliushubao_demo \
  --output-root ./workspace
```

## Full offline `prepare` example

Enable every optional module at once — orbit matching, DEM planning + conversion
planning, GACOS request planning, and GACOS import checking. Point `--orbit-dir`
and `--gacos-import-dir` at local folders you already have, and pass the
processing AOI via `--bbox WEST SOUTH EAST NORTH`.

```bash
uv run insar-prep prepare \
  --cart tests/fixtures/asf/urls.txt \
  --region-name shiliushubao_demo \
  --output-root ./workspace \
  --orbit-dir ./orbits \
  --dem-plan \
  --bbox 110.1 30.8 110.6 31.2 \
  --gacos-plan \
  --gacos-import-dir ./gacos_products
```

### Windows (PowerShell)

PowerShell uses a backtick (`` ` ``) for line continuation instead of `\`, and
**any path containing spaces must be quoted**:

```powershell
uv run insar-prep prepare `
  --cart tests/fixtures/asf/urls.txt `
  --region-name shiliushubao_demo `
  --output-root "C:\My Work\workspace" `
  --orbit-dir ".\orbits" `
  --dem-plan `
  --bbox 110.1 30.8 110.6 31.2 `
  --gacos-plan `
  --gacos-import-dir ".\gacos_products"
```

Both `\` and `/` path separators are accepted. The output directory and report
file names are always SARscape-safe (snake_case), so spaces in `--output-root`
or `--region-name` never leak into generated names.

## Where the report is written

Both reports are written, with SARscape-safe names, under:

```text
<output_root>/<region_safe_name>/07_reports/
  <region_safe_name>_data_preparation_report.json
  <region_safe_name>_data_preparation_report.md
```

The report consolidates each enabled module into its own section (Scene
consistency, Orbit matching, DEM planning, DEM conversion, GACOS request
planning, GACOS import check) plus an aggregated **Next actions** checklist and an
overall `ready` / `ready_with_warnings` / `blocked` status.

## What this tool does **not** do (by design)

The current offline MVP never performs any of the following:

- Download SAR data from ASF / ASF Vertex.
- Download DEMs from OpenTopography (or anywhere else).
- Submit, scrape, or automate the GACOS web service.
- Perform real DEM vertical-datum conversion (it only *plans* the steps; no
  GDAL / rasterio / pyproj, no geoid download, no `.tif` files are created).
- Provide a GUI.

It also never reads accounts, stores credentials, or moves / deletes / renames
your input files.

## SARscape naming constraints

Region names and generated paths are normalized to **SARscape-safe** names:

- lowercase letters and digits joined by single **underscores** (`_`);
- **no spaces, no hyphens (`-`), and no special characters** — e.g.
  `--region-name "Shiliushubao Area-1"` becomes `shiliushubao_area_1`;
- the SARscape-ready DEM filename must end with `_dem.tif`, i.e.
  `<region_safe_name>_dem.tif`.

## Project layout

```text
src/insar_prep/      # core package (importable as insar_prep)
  cli/               # command-line interface (`prepare` workflow)
  core/              # data models, naming, logging, errors, events
  processing/        # AOI handling
  providers/         # asf, orbit, dem, gacos (all offline/local)
  quality/           # scene consistency checks
  queue/             # offline task queue framework
  reporting/         # JSON + Markdown report backend
  sar_apps/          # SARscape adapter
tests/
  unit/              # unit tests
  e2e/               # end-to-end CLI regression
.github/workflows/   # CI (ruff + pytest)
```

See `DEVELOPMENT_MANUAL.md`, `CURSOR_OPUS_GUIDE.md`, and
`insar_prep_project_rules.mdc` for design, hard constraints, and the task roadmap.

## Packaging

No official release or installer is published. For local testing only, a one-file
Windows executable can be built with `scripts/build_windows_exe.ps1`, and a
self-contained smoke-test package can be assembled with
`scripts/make_windows_smoke_package.ps1` (both produce git-ignored artifacts that
are never committed). See:

- [`docs/packaging_readiness.md`](docs/packaging_readiness.md) — packaging
  readiness checklist, runtime-dependency risks (shapely/GEOS, pydantic-core), the
  PyInstaller command, and the build result.
- [`docs/windows_exe_smoke_test.md`](docs/windows_exe_smoke_test.md) — how to
  generate and run the local Windows smoke-test package.
- [`docs/release_readiness_v0_1_0.md`](docs/release_readiness_v0_1_0.md) — the
  v0.1.0 offline CLI MVP release-readiness review and checklist.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## License

MIT — see [LICENSE](LICENSE).
