# InSAR Data Preparation Assistant (`insar-prep`)

A SARscape-oriented InSAR **data preparation and quality-checking assistant** for
Sentinel-1 / InSAR beginners.

- It is **not** a full InSAR processing engine and does not replace SARscape,
  ISCE, MintPy, SNAP, or ASF Vertex.
- It is a **data preparation assistant** that runs *before* SARscape: it parses
  local ASF carts, checks scene consistency, matches local precise orbits, plans
  DEM and GACOS requests, checks already-downloaded GACOS products, and writes a
  beginner-friendly data-preparation report.
- The **offline core** (CLI `prepare` workflow and the optional PySide6 GUI Beta)
  runs locally with no network and no downloads. Real downloads are separate,
  explicit opt-ins behind the `download` extra.

> Current status: **v0.14.0 — GUI Beta.** The offline `insar-prep prepare` CLI
> workflow is implemented end to end, and an optional PySide6 **GUI Beta** drives
> the same offline closed loop (install it with `uv sync --extra gui`). Real
> Sentinel-1 SLC download (`download-asf --download-mode real`) and real DEM
> download from the OpenTopography Global DEM API (`download-dem --download-mode
> real`, plus the GUI "DEM Download" panel) are available as explicit opt-ins
> behind the `download` extra — each user supplies their **own** free
> OpenTopography API key (none is bundled). Real **GACOS** download and real DEM
> **vertical-datum conversion** are still **not** implemented (planning only), and
> there is **no** official GUI release, installer, or `.exe`. A one-file Windows
> CLI exe can be built *locally* for testing only. See
> [`docs/release_readiness_v0_12_0_gui_beta.md`](docs/release_readiness_v0_12_0_gui_beta.md)
> for the most recent readiness review, and
> [`docs/release_readiness_v0_1_0.md`](docs/release_readiness_v0_1_0.md) for the
> previous v0.1.0 offline CLI MVP baseline.

## Requirements

- Python 3.11
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

This creates the virtual environment and installs `insar-prep` plus its dev
tools. After syncing, run the CLI via `uv run insar-prep ...`.

The desktop GUI is optional and **not** installed by default. To include it,
add the `gui` extra (this pulls in PySide6):

```bash
uv sync --extra gui
```

Real ASF SLC download is also optional and **not** installed by default. To
enable it, add the `download` extra (this pulls in `requests`); see
[ASF Sentinel-1 SLC download](#asf-sentinel-1-slc-download):

```bash
uv sync --extra download
```

## Basic commands

```bash
uv run insar-prep --help
uv run insar-prep --version
uv run insar-prep prepare --help
uv run insar-prep update-check   # check GitHub for a newer release
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
Processing AOI via `--bbox`, `--aoi-geojson`, or `--aoi-wkt` (see
[Specifying the Processing AOI](#specifying-the-processing-aoi) below).

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

## Specifying the Processing AOI

The DEM and GACOS planning steps need a Processing AOI. Provide it with **exactly
one** of these mutually exclusive flags (passing more than one is rejected):

- `--bbox WEST SOUTH EAST NORTH` — explicit bounds, in degrees.
- `--aoi-geojson PATH` — a GeoJSON file holding a `Polygon`/`MultiPolygon`
  geometry, a `Feature`, or a `FeatureCollection` (multiple features are merged
  and their combined bounds are used).
- `--aoi-wkt "WKT"` — a WKT `POLYGON` or `MULTIPOLYGON` string.
- `--aoi-shp PATH` — an ESRI Shapefile (`.shp`); the `.shp` is read directly (the
  `.shx` index is not required) and all polygon rings are merged. A sidecar
  `.prj`, if present, must be WGS84 lon/lat — a projected or non-WGS84 CRS is
  rejected (no reprojection is performed).
- `--aoi-kml PATH` — a KML file (`.kml`); all `Polygon` geometries are merged.
- `--aoi-kmz PATH` — a zipped KML (`.kmz`); the `doc.kml` (or first `.kml`) entry
  inside the archive is parsed.
- `--aoi-file PATH` — any of the supported vector files above
  (`.geojson`/`.json`/`.shp`/`.kml`/`.kmz`), auto-detected by file extension.

```bash
uv run insar-prep prepare \
  --cart tests/fixtures/asf/urls.txt \
  --region-name shiliushubao_demo \
  --output-root ./workspace \
  --aoi-geojson ./aoi.geojson \
  --dem-plan \
  --gacos-plan
```

For file/string inputs the AOI's bounding box (its bounds) becomes the Processing
AOI; the existing per-product download buffers are then applied as before.
Shapefile interior rings (holes) are not preserved — each ring is treated as a
filled polygon — which never changes the AOI's bounds.

Constraints:

- Coordinates must be **WGS84 longitude/latitude (EPSG:4326)** only. A GeoJSON
  `crs` member or a shapefile `.prj` that is not EPSG:4326 is rejected, and no
  coordinate transforms are performed. KML/KMZ are WGS84 lon/lat by specification.
- Longitudes must be within `[-180, 180]` and latitudes within `[-90, 90]`.
- Only `Polygon` / `MultiPolygon` geometries are accepted (no points/lines, no
  `GeometryCollection`).
- Supported vector files: GeoJSON, ESRI Shapefile (`.shp`), KML (`.kml`), and
  KMZ (`.kmz`). `GeoPackage` inputs are **not** supported.
- No new dependencies are used: shapefiles are parsed with the standard-library
  `struct`, KML with `xml.etree`, and KMZ with `zipfile`, on top of `shapely`.

## Where the report is written

All outputs are written, with SARscape-safe names, under:

```text
<output_root>/<region_safe_name>/07_reports/
  <region_safe_name>_data_preparation_report.json
  <region_safe_name>_data_preparation_report.md
  <region_safe_name>_data_preparation_report.html
  <region_safe_name>_manifest.csv
  <region_safe_name>_warnings.csv
```

The report consolidates each enabled module into its own section (Scene
consistency, Orbit matching, DEM planning, DEM conversion, GACOS request
planning, GACOS import check) plus an aggregated **Next actions** checklist and an
overall `ready` / `ready_with_warnings` / `blocked` status.

The `.html` report is a **self-contained static page** for browsing the same
information in a web browser: it mirrors the JSON/Markdown report (summary cards
plus one section per module), inlines its own minimal CSS, and references **no**
external network, CSS/JS, or CDN resources. It is a read-only view, not a GUI, and
no official release/installer is implied.

The `manifest.csv` is a flat, row-based inventory of this `prepare` run, with the
fixed columns `section,item_type,item_id,item_name,status,path,value,notes`. It
lists the parsed scenes, each enabled module's plan/check results (orbit, DEM,
GACOS), and the generated report files; optional modules that were not run appear
as a single `SKIPPED` row. It is a preparation-run inventory, **not** a SARscape
project file, and it never implies any real download was performed.

The `warnings.csv` is a focused **problem summary** (not the full inventory), with
the fixed columns
`severity,section,item_type,item_id,item_name,code,message,path,action`. It lists
only the `WARNING`/`ERROR` issues found (e.g. duplicate scenes, missing URLs,
unmatched orbits, missing/empty GACOS products) plus an `action` hint for each;
when nothing is wrong it contains a single `INFO` "no warnings" summary row.

## What this tool does **not** do (by design)

The strictly offline commands (`prepare`, `plan-asf-downloads`) never touch the
network. Real downloads are separate, explicit opt-ins behind the `download`
extra. By design the tool never:

- Downloads SAR data from ASF / ASF Vertex as part of the offline core. (Real
  Sentinel-1 SLC download is available only as an explicit opt-in: the separate
  `download-asf --download-mode real` command, or the GUI "ASF SLC Download"
  panel, behind the optional `download` extra — see
  [ASF Sentinel-1 SLC download](#asf-sentinel-1-slc-download). The offline
  commands themselves still never touch the network.)
- Downloads DEMs as part of the offline core. (Real DEM download from the
  OpenTopography Global DEM API is available only as an explicit opt-in:
  `download-dem --download-mode real`, or the GUI "DEM Download" panel, behind the
  `download` extra — see [DEM download (OpenTopography)](#dem-download-opentopography).
  Each user supplies their own free API key; no key is bundled.)
- Submit, scrape, or automate the GACOS web service (GACOS is planning only).
- Perform real DEM vertical-datum conversion (it only *plans* the steps; no
  GDAL / rasterio / pyproj, no geoid download, no conversion `.tif` is created —
  the real download fetches the **raw** DEM only).

It also never reads accounts, stores credentials in a project file, or moves /
deletes / renames your input files.

### ASF downloads: offline dry-run planning

- The offline planner reads a local ASF cart and writes a download *plan*
  (JSON + CSV) listing the expected filenames and intended local paths —
  **without** downloading anything, contacting ASF/Earthdata, or reading
  credentials. No account is required:

```bash
uv run insar-prep plan-asf-downloads \
  --cart tests/fixtures/asf/urls.txt \
  --output-dir ./workspace
```

This writes, under the chosen output directory:

```text
<output-dir>/asf_download_plan/
  asf_download_plan.json
  asf_download_plan.csv
```

The CSV has the fixed header
`scene_id,platform,acquisition_datetime,product,beam,polarization,url_status,expected_filename,planned_path,status,credential_required,notes`.
Each scene is `PLANNED` (a download URL is present) or `MISSING_URL`, the
intended SLC path is recorded as `<output-dir>/02_slc/<expected_filename>` (never
created), and `credential_required` is always `yes`. URLs, query strings, and
tokens are **never** written to the plan. Pass `--require-urls` to make a missing
URL a non-zero exit (the plan is still written).

- The **credential-safe design** is documented in
  [`docs/asf_download_credential_design.md`](docs/asf_download_credential_design.md)
  (default `dry-run`, explicit opt-in for real download, strict log/report
  redaction, and credentials kept out of the repository).
- **Redaction is hardened**: logs, reports (JSON/Markdown/HTML), and CSVs are
  masked for tokens, passwords, API keys, `Authorization`/`Bearer`/`Cookie`
  headers, session ids, presigned-URL signatures, `.netrc` login/password lines,
  and `user:pass@host` URLs, while ordinary text and Windows paths are left intact.

### ASF Sentinel-1 SLC download

Real, credentialed Sentinel-1 SLC download is available via the separate
`download-asf` command. It is **off by default** (dry-run) and isolated from the
offline core so `prepare` / `plan-asf-downloads` / `gui` never gain a network
dependency.

1. **Install the optional extra** (adds `requests`; the offline core never needs it):

```bash
uv sync --extra download
```

2. **Provide NASA Earthdata Login credentials** *outside* the project, via either:
   - a user-managed `~/.netrc` (`~/_netrc` on Windows) with a
     `machine urs.earthdata.nasa.gov login <user> password <pass>` entry
     (default, `--credential-source netrc`), or
   - an `EARTHDATA_TOKEN` environment variable holding an EDL bearer token
     (`--credential-source env-token`).

   A password is **never** accepted as a command-line flag.

3. **Run the download** (default is a safe dry-run plan; add `--download-mode real`
   to actually fetch):

```bash
# dry-run (offline plan only, no network) — same plan as plan-asf-downloads:
uv run insar-prep download-asf --cart tests/fixtures/asf/urls.txt --output-dir ./workspace

# verify (fast network preflight: confirms credentials + ASF reachability
# without downloading the multi-GB SLCs):
uv run insar-prep download-asf \
  --cart tests/fixtures/asf/urls.txt \
  --output-dir ./workspace \
  --download-mode verify

# real download (needs the 'download' extra + Earthdata credentials):
uv run insar-prep download-asf \
  --cart tests/fixtures/asf/urls.txt \
  --output-dir ./workspace \
  --download-mode real
```

> **Tip — verify before a big run.** `--download-mode verify` sends one small
> `Range` request per scene to confirm the whole chain (credential resolution →
> Earthdata auth → ASF data pool → signed S3 redirect) works and the remote size
> matches the plan, **without** downloading the archives. Use it to validate
> credentials and connectivity in seconds before committing to a multi-GB
> download.

Real download streams each SLC to a `<name>.zip.part` temp file, verifies the
byte count against `Content-Length`, then **atomically renames** to the final
`<output-dir>/02_slc/<granule>.zip`; already-complete targets are skipped, so a
re-run is idempotent and resumable. Transient failures are retried with backoff
(`--max-retries`, default 3); the bearer token is kept only for Earthdata/ASF
hosts and **dropped before any signed S3 redirect**. A per-scene
`asf_download_plan/asf_download_results.csv` records the outcome of each scene
(credential-masked). Earthdata Login credentials live only in memory and are
never written to the repository, logs, reports, or CSVs.

## DEM download (OpenTopography)

Real DEM download from the [OpenTopography Global DEM
API](https://portal.opentopography.org/apidocs/) is available via the separate
`download-dem` command (and the GUI "DEM Download" panel). It is **off by
default** (dry-run) and isolated from the offline core so `prepare` /
`plan-asf-downloads` never gain a network dependency.

Each user supplies their **own** free OpenTopography API key. **No key is bundled
or shared** — the free key is rate limited (about 200 calls/24 h for academic
users, 50/24 h otherwise) and tied to your account, so a shared key would be
throttled or revoked. Commercial/for-profit use needs an Enterprise key.

1. **Install the optional extra** (adds `requests` + `keyring`; the offline core
   never needs it):

```bash
uv sync --extra download
```

2. **Get a free OpenTopography API key and store it** (interactive, no-echo; the
   key is saved in your OS keyring, never in a project file):

```bash
insar-prep dem-auth login     # prints the register -> request-key steps, then prompts
insar-prep dem-auth status    # shows whether a key is stored (set / none)
```

   To register: create a free account at
   <https://portal.opentopography.org/newUser>, log in, open the **myOpenTopo**
   dashboard, click **Get an API Key**, then **Request API Key**. Alternatively,
   set the `OPENTOPOGRAPHY_API_KEY` environment variable.

3. **Plan or download the DEM** for a Processing AOI (same AOI flags as
   `prepare`). Default is a safe offline dry-run; add `--download-mode real` to
   fetch:

```bash
# dry-run (offline plan only, no network):
insar-prep download-dem --region-name shiliushubao_demo --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 --dem-dataset COP30

# verify (fast preflight: a tiny sub-tile confirms the key + endpoint):
insar-prep download-dem --region-name shiliushubao_demo --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 --download-mode verify

# real download (needs the 'download' extra + an OpenTopography API key):
insar-prep download-dem --region-name shiliushubao_demo --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 --download-mode real
```

Real download streams the GeoTIFF to a `<name>.tif.part` temp file, verifies the
GeoTIFF magic bytes and (when present) the `Content-Length`, then **atomically
renames** to `<output-root>/<region>/04_dem/raw/<region>_<dataset>_raw.tif`;
an already-present DEM is skipped, so a re-run is idempotent. Transient failures
are retried with backoff (`--max-retries`); a rejected key (HTTP 401/403) maps to
`DEM005`. A credential-masked `dem_download/dem_download_results.csv` records the
outcome. Supported datasets map to OpenTopography `demtype`s: COP30, COP90,
SRTMGL1 (+ ellipsoidal), NASADEM, and AW3D30 (+ ellipsoidal); `USER_LOCAL` is not
downloadable. The downloaded DEM is the **raw** product — real vertical-datum
conversion to an ellipsoidal, SARscape-ready DEM is still planning-only.

## Update notifications

`insar-prep` checks the project's public GitHub Releases to let you know when a
newer version is available:

```bash
uv run insar-prep update-check
```

- **On demand:** `update-check` queries the latest release and reports whether
  you are up to date or a newer version exists (with a download link).
- **Automatic:** after a command that *already uses the network* (`download-asf
  --download-mode verify`/`real`, `auth status --test`), a one-line "update
  available" notice may be printed to stderr. This is **best-effort** (never
  blocks or fails a command), **throttled** (the network is queried at most once
  per 24 h, cached per user), and **opt-out** — set `INSAR_NO_UPDATE_CHECK=1` to
  disable it. The strictly offline commands (`prepare` / `plan-asf-downloads` /
  dry-run) never trigger it, so they keep touching no network.

The check uses only the Python standard library (no extra dependency, no
credentials), so it also works in the packaged `.exe`. It relies on the
maintainer publishing GitHub Releases: pushing a `v*` tag triggers
`.github/workflows/release.yml`, which builds the Windows one-file exe and
attaches it to the Release that the update check then reports.

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
  gui/               # optional PySide6 desktop GUI (beta skeleton; `gui` extra)
  core/              # data models, naming, logging, errors, events
  processing/        # AOI handling
  providers/         # asf, orbit, dem, gacos (offline planning; asf+dem add opt-in real download)
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

## Desktop GUI (beta)

A desktop GUI is available as an early **beta skeleton**. It is optional: the
offline CLI never needs it, and PySide6 is installed only via the `gui` extra.

```bash
uv sync --extra gui
uv run --extra gui insar-prep gui
```

If PySide6 is not installed, `insar-prep gui` exits with a clear, single-line
message (`PySide6 is required for the GUI. Install with: uv sync --extra gui`)
and a non-zero status; every other CLI command keeps working without PySide6.

The GUI shows the main-window layout — a Workspace / Project / Region tree, the
Region workflow steps, a task-queue / log panel, and a warnings/errors status
bar. From the toolbar you can create a **Workspace / Project / Region** (the
tree updates live; names are normalized with the same SARscape-safe naming as
the CLI, and precondition/input errors are shown in the status bar with an error
code). The centre **AOI panel** then defines the current Region's Processing AOI
from a bounding box, a GeoJSON file, a WKT string, an ESRI Shapefile (`.shp`), a
KML file (`.kml`), or a zipped KML (`.kmz`) — the sources are mutually exclusive;
it reuses the same core AOI importers as the CLI — EPSG:4326 lon/lat only,
GeoPackage unsupported, and no coordinate transforms — and the tree marks a
Region with `[AOI set]` once one is bound. An **ASF cart import**
panel parses a locally exported ASF cart (Vertex Python script, URL text, CSV, or
GeoJSON) with the same core parser as the CLI and lists the resulting scenes
(scene id, platform, acquisition time, product, beam, polarization, and URL
status) in a read-only table. A **scene consistency check** panel runs the same
core `check_scene_collection` over the imported scenes (with an optional expected
polarization) and shows the total, the error/warning counts, and the issue list;
the bottom warnings/errors bar reflects the result (error count, warning count,
or `Ready`). An **offline planning** panel then drives the same core planners as
the CLI for the current Region: it matches a local orbit (`.EOF`) directory
against the scenes (showing matched / unmatched counts), builds a DEM request +
conversion plan (dataset / provider / source & target vertical datum) marked
**planned only** — no `.tif` is created and no real conversion is performed — and
builds a GACOS request plan from the scene dates with an optional read-only
import check of a local GACOS product directory. Finally, a **Reports** panel
generates the same five-file set as the CLI — JSON, Markdown, HTML,
`manifest.csv` and `warnings.csv` — under a chosen output root, consolidating the
scene/orbit/DEM/GACOS results produced above; the output paths are listed and the
status bar reflects the overall result. This completes the offline beta loop
(Workspace → Project → Region → AOI → ASF cart → scene check → offline planning →
reports), which performs no network access.

Two **optional real-download panels** sit at the end of the workflow, mirroring
the CLI and behind the `download` extra: an **ASF SLC Download** panel (Earthdata
login dialog + dry-run / real, on a cancellable background thread) and a **DEM
Download (OpenTopography)** panel (dataset selector, dry-run / real, a cancellable
background thread, and a one-click *OpenTopography API Key* dialog that embeds the
register → request-key guidance and stores your own key in the OS keyring). Like
the CLI, the GUI does **not** implement real GACOS download or real DEM
vertical-datum conversion — those remain intentionally deferred. There is **no**
official GUI release, installer, or `.exe`; the GUI Beta runs from source via
`uv`.

For step-by-step install/launch/usage and a pre-delivery checklist, see:

- [`docs/gui_beta_user_guide.md`](docs/gui_beta_user_guide.md) — GUI Beta user
  guide (status, installation, launch, window layout, the offline workflow, and
  current limitations).
- [`docs/gui_beta_smoke_test.md`](docs/gui_beta_smoke_test.md) — GUI Beta
  smoke-test checklist (the automated quality gate plus a manual click-through of
  the offline closed loop).

## Packaging

No official release or installer is published. For local testing only, a one-file
Windows executable can be built with `scripts/build_windows_exe.ps1`, and a
self-contained smoke-test package can be assembled with
`scripts/make_windows_smoke_package.ps1` (both produce git-ignored artifacts that
are never committed). See:

- [`docs/getting_started_for_testers.md`](docs/getting_started_for_testers.md) —
  one-page quickstart for running the Windows `insar-prep.exe` (offline reports
  and real ASF SLC download with `auth login`).
- [`docs/packaging_readiness.md`](docs/packaging_readiness.md) — packaging
  readiness checklist, runtime-dependency risks (shapely/GEOS, pydantic-core), the
  PyInstaller command, and the build result.
- [`docs/windows_exe_smoke_test.md`](docs/windows_exe_smoke_test.md) — how to
  generate and run the local Windows smoke-test package.
- [`docs/release_readiness_v0_12_0_gui_beta.md`](docs/release_readiness_v0_12_0_gui_beta.md)
  — the current v0.12.0 GUI Beta release-readiness review and checklist.
- [`docs/release_readiness_v0_1_0.md`](docs/release_readiness_v0_1_0.md) — the
  previous v0.1.0 offline CLI MVP baseline release-readiness review (superseded).

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## License

MIT — see [LICENSE](LICENSE).
