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

> Current status: **v0.16.0.** The offline `insar-prep prepare` CLI workflow is
> implemented end to end, and an optional PySide6 **GUI** drives the same offline
> closed loop (install it with `uv sync --extra gui`) and now offers a runtime
> **English / 中文 language switch** (the *Language* menu). Real Sentinel-1 SLC
> download (`download-asf --download-mode real`) and real DEM download from the
> OpenTopography Global DEM API (`download-dem --download-mode real`, plus the
> GUI "DEM Download" panel) are available as explicit opt-ins behind the
> `download` extra — each user supplies their **own** free OpenTopography API key
> (none is bundled). Real **DEM vertical-datum conversion** (`convert-dem`,
> orthometric → WGS84 ellipsoid via a bundled EGM96 geoid grid, behind the
> optional `convert` extra) and **GACOS product import** (`gacos-import`) are also
> available. **New in v0.16.0:** real **GACOS request submission and result
> download** (`gacos-request` / `gacos-download`, plus the GUI "GACOS Download"
> panel, behind the `download` extra). GACOS has **no public download API**, so
> the client automates the two steps the service permits — submitting the web
> request form and fetching the **emailed** result archive — and the email link
> itself is pasted in by the user (no mailbox scraping, no browser automation).
> A one-file Windows CLI/GUI exe and an Inno Setup installer can be built
> *locally* (see [Packaging](#packaging)) and are published by the tag-triggered
> release workflow. See
> [`docs/release_readiness_v0_16_0.md`](docs/release_readiness_v0_16_0.md) for the
> latest readiness review.

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

Real DEM **vertical-datum conversion** (`convert-dem`) is optional too. To enable
it, add the `convert` extra (this pulls in `rasterio`); see
[DEM vertical-datum conversion](#dem-vertical-datum-conversion-convert-dem):

```bash
uv sync --extra convert
```

## Basic commands

```bash
uv run insar-prep --help
uv run insar-prep --version
uv run insar-prep prepare --help
uv run insar-prep convert-dem --help   # real DEM vertical-datum conversion (convert extra)
uv run insar-prep gacos-import --help  # organize manually downloaded GACOS products
uv run insar-prep gacos-request --help # submit a real GACOS request (download extra)
uv run insar-prep gacos-download --help # fetch the emailed GACOS result (download extra)
uv run insar-prep update-check         # check GitHub for a newer release
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
- Scrape a mailbox, drive a browser, or bypass the GACOS request limits. GACOS
  has **no public download API**, so the optional real client
  (`gacos-request` / `gacos-download`, behind the `download` extra) only does what
  the service allows: it **submits the web request form** and **fetches the
  emailed result archive** (the email link is pasted in by the user). The offline
  core still only *plans* the request, and `gacos-import` *organizes and
  integrity-checks* products you fetched by hand — see
  [GACOS request and download](#gacos-request-and-download-gacos-request--gacos-download).
- Perform real DEM vertical-datum conversion **as part of the offline core**. The
  offline core only *plans* the conversion. Real conversion is now available as an
  explicit opt-in — the separate `convert-dem` command behind the `convert` extra
  (`rasterio` + the bundled EGM96 geoid) — see
  [DEM vertical-datum conversion](#dem-vertical-datum-conversion-convert-dem). The
  offline commands themselves still use no GDAL/rasterio.

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

## DEM vertical-datum conversion (`convert-dem`)

SARscape expects a DEM referenced to the **WGS84 ellipsoid**, but most global
DEMs are **orthometric** (COP30/COP90 use EGM2008; SRTMGL1/NASADEM/AW3D30 use
EGM96). `convert-dem` performs the real conversion by adding the geoid undulation
`N` to every pixel (`h_ellipsoid = H_orthometric + N`) using a **bundled EGM96
15-arc-minute geoid grid**, then writes the SARscape-ready `<region>_dem.tif`.
Datasets that are already ellipsoidal (`SRTMGL1_E`/`AW3D30_E`) are copied through
unchanged.

It is opt-in behind the `convert` extra (which pulls in `rasterio`); the offline
core never needs it. `--plan-only` prints the planned steps without rasterio.

```bash
uv sync --extra convert

# convert an already-downloaded raw DEM (from download-dem) to SARscape-ready:
uv run insar-prep convert-dem \
  --region-name shiliushubao_demo \
  --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 \
  --dem-dataset COP30
```

The source vertical datum is inferred from `--dem-dataset` (override with
`--source-vertical-datum`). Because only the EGM96 grid is bundled, converting an
**EGM2008** source (COP30/COP90) with it is a sub-metre **approximation** and is
flagged with a warning; supply your own EGM2008 grid via `--geoid-grid PATH` (a
`.npz` built with `scripts/build_geoid_npz.py`) for an exact conversion. The
output lands at `<output-root>/<region>/06_sarscape_ready/<region>_dem.tif`, the
intermediate ellipsoidal DEM under `04_dem/ellipsoid/`, and a results CSV under
`<output-root>/dem_convert/`. The bundled EGM96 grid is derived from the
public-domain GeographicLib `egm96-15` grid (see `THIRD_PARTY_REFERENCES.md`).

> **Note on the exe.** The one-file **GUI** exe bundles rasterio and can convert;
> the lean **CLI** exe omits rasterio (to stay small) and will ask you to install
> the `convert` extra. Run `convert-dem` from a source checkout for the CLI path.

## GACOS product import (`gacos-import`)

GACOS (the Generic Atmospheric Correction Online Service) has **no public
download API** — you request a region/date list through its web form and receive
the products by email. This tool therefore never downloads GACOS for you. What it
*does* do is take the products you downloaded **manually** and bring them into the
region layout: `gacos-import` extracts `.zip`/`.tar.gz` archives, copies the
`YYYYMMDD.ztd` / `YYYYMMDD.ztd.rsc` / `YYYYMMDD.tif` products into the region's
GACOS directory under canonical names, and **integrity-checks** each date (the
`.ztd` byte size must equal `4 × WIDTH × FILE_LENGTH` from its `.rsc`, plus file
pairing and emptiness checks). It uses only the standard library and never
contacts GACOS, drives a browser, or stores credentials.

```bash
uv run insar-prep gacos-import \
  --region-name shiliushubao_demo \
  --output-root ./workspace \
  --source ./downloads/gacos_products.tar.gz \
  --source ./more_gacos/ \
  --cart tests/fixtures/asf/urls.txt   # optional: check coverage vs scene dates
```

Products land under `<output-root>/<region>/05_atmosphere/gacos/requests/`. Pass
`--cart` to compare the imported dates against an ASF cart's acquisition dates
(missing dates are reported as errors). Add `--move` to move (instead of copy)
loose source files.

## GACOS request and download (`gacos-request` / `gacos-download`)

GACOS has **no public download API**: a product is obtained by submitting a
web-request form and then downloading the archive GACOS **emails** you. The
optional client automates both ends of that — it is **off by default** and behind
the `download` extra, and never scrapes a mailbox, drives a browser, or stores a
password.

1. **Install the optional extra** (adds `requests` + `keyring`):

```bash
uv sync --extra download
```

2. **Store the email** GACOS should deliver to (optional; you can also pass
   `--email` or set `GACOS_EMAIL`):

```bash
insar-prep gacos-auth login      # stores your GACOS email in the OS keyring
insar-prep gacos-auth status     # shows the (masked) stored email
```

3. **Submit the request** for a Processing AOI and a date list (from an ASF cart
   or `--dates`). The default is a safe offline **dry-run preview**; add
   `--submit` to actually POST the form (in ≤20-date batches):

```bash
# dry-run (offline preview only, no network):
insar-prep gacos-request --region-name shiliushubao_demo --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 --cart tests/fixtures/asf/urls.txt --time 18:30

# real submission (needs the 'download' extra + your GACOS email):
insar-prep gacos-request --region-name shiliushubao_demo --output-root ./workspace \
  --bbox 110.1 30.8 110.6 31.2 --cart tests/fixtures/asf/urls.txt --time 18:30 --submit
```

   GACOS then emails you a download link per job (this can take minutes to hours).

4. **Download the emailed result** and import it in one step (extract → organize
   → integrity-check into the region's GACOS directory, reusing the same importer
   as `gacos-import`):

```bash
insar-prep gacos-download --region-name shiliushubao_demo --output-root ./workspace \
  --url "http://www.gacos.net/data/...your-link..." \
  --cart tests/fixtures/asf/urls.txt   # optional coverage check
```

Pass `--url` more than once (or `--url-file links.txt`) to fetch several jobs.
Choose the product format with `--output-format geotiff|binary` on the request
(GeoTIFF is the default and smaller). The same flow is available from the GUI
"GACOS Download" panel (submit + fetch on a background thread, plus a *GACOS
Email* dialog). The download submission/fetch are the only GACOS network calls;
the offline `prepare` / planning commands never touch GACOS.

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
  data/              # bundled EGM96 geoid grid (egm96_15.npz) for DEM conversion
  processing/        # AOI handling
  providers/         # asf, orbit, dem, gacos (offline planning; asf+dem real download; dem convert; gacos import)
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

Three **optional real-download panels** sit at the end of the workflow, mirroring
the CLI and behind the `download` extra: an **ASF SLC Download** panel (Earthdata
login dialog + dry-run / real, on a cancellable background thread), a **DEM
Download (OpenTopography)** panel (dataset selector, dry-run / real, a cancellable
background thread, and a one-click *OpenTopography API Key* dialog), and a
**GACOS Download** panel (submit the real request and fetch the emailed result on
a background thread, with a one-click *GACOS Email* dialog). The GUI also exposes
a **Language** menu to switch between **English** and **中文** at runtime (the
choice is remembered across launches). A one-file Windows GUI `.exe` and an Inno
Setup **installer** can be built locally (see [Packaging](#packaging)) and are
published by the release workflow.

For step-by-step install/launch/usage and a pre-delivery checklist, see:

- [`docs/gui_beta_user_guide.md`](docs/gui_beta_user_guide.md) — GUI Beta user
  guide (status, installation, launch, window layout, the offline workflow, and
  current limitations).
- [`docs/gui_beta_smoke_test.md`](docs/gui_beta_smoke_test.md) — GUI Beta
  smoke-test checklist (the automated quality gate plus a manual click-through of
  the offline closed loop).

## Packaging

No official release or installer is published yet. For local testing only, a
one-file Windows **CLI** executable can be built with
`scripts/build_windows_exe.ps1`, a one-file **GUI** executable (bundling PySide6,
the `download` extra, and the `convert` extra's rasterio + the EGM96 geoid) with
`scripts/build_windows_gui_exe.ps1`, and a self-contained smoke-test package with
`scripts/make_windows_smoke_package.ps1`. A standard Windows **installer** for the
GUI exe can then be compiled from `packaging/insar_prep_gui_installer.iss` with
`scripts/build_windows_installer.ps1` (requires [Inno Setup
6](https://jrsoftware.org/isdl.php); not bundled). All of these produce
git-ignored artifacts that are never committed. See:

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
