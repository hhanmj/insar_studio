# Release readiness — v0.15.0

This document captures the **release-readiness** state of `insar-prep` as
**`v0.15.0`**. It records what changed since the v0.14.0 GUI Beta baseline so a
deliberate tag/release is a simple, traceable step. It does **not** itself cut a
GitHub Release, push a tag, or upload artifacts — those remain a maintainer
action (see §6).

It supersedes
[`release_readiness_v0_12_0_gui_beta.md`](release_readiness_v0_12_0_gui_beta.md).

## 1. Version status

- Version: **`0.15.0`** (bumped from `0.14.0`; see `pyproject.toml` and
  `insar_prep/__init__.py` → `__version__ = "0.15.0"`).
- `--version` prints `insar-prep 0.15.0`. `__version__` is a hard-coded literal,
  so it keeps working inside a frozen exe (no `importlib.metadata` lookup).
- Suggested tag (maintainer action, not in this change): `v0.15.0`. Existing tags
  `v0.1.0-offline-cli` and `v0.12.0-gui-beta` are retained.

## 2. What is new in v0.15.0

- **Real DEM vertical-datum conversion** (`convert-dem`, opt-in `convert` extra):
  orthometric (EGM96/EGM2008) → WGS84 ellipsoidal DEM by adding geoid undulation
  from a **bundled EGM96 15′ grid** (`insar_prep/data/egm96_15.npz`, ~3 MB,
  built by `scripts/build_geoid_npz.py` from the public-domain GeographicLib
  `egm96-15` grid). `RealDemConverter` reads the GeoTIFF in row blocks with
  `rasterio`, rejects projected CRS, preserves nodata, and atomically writes the
  SARscape-ready DEM. Already-ellipsoidal datasets are copied through.
- **GACOS product import** (`gacos-import`, stdlib only): extracts
  `.zip`/`.tar.gz` (with zip/tar-slip protection), organizes
  `YYYYMMDD.ztd`/`.ztd.rsc`/`.tif` products by date into the region layout, and
  integrity-checks each (`.ztd` size == `4 × WIDTH × FILE_LENGTH` from `.rsc`).
- **Packaging**: the geoid grid ships in the wheel and both exes
  (`--collect-data insar_prep`); the GUI exe also bundles `rasterio`/GDAL so it
  can convert. New Inno Setup installer
  (`packaging/insar_prep_gui_installer.iss` + `scripts/build_windows_installer.ps1`).

## 3. Completed capabilities (cumulative)

Offline core (`prepare`, `plan-asf-downloads`) — unchanged and still
network-free. Opt-in real I/O: ASF SLC download (`download-asf`, `download`
extra), OpenTopography DEM download (`download-dem`, `download` extra), DEM
vertical-datum conversion (`convert-dem`, `convert` extra), and GACOS product
import (`gacos-import`, stdlib). PySide6 GUI Beta (`gui` extra) drives the
offline loop plus the real ASF/DEM download panels. GitHub-Releases update check
(stdlib).

## 4. Explicit non-goals / limitations

- **Real GACOS download is impossible by design**: GACOS has no public download
  API (web form + email delivery only); automating its web form is out of scope.
  `gacos-import` covers only the organize/integrity-check half for products the
  user downloads themselves.
- The **lean CLI exe omits rasterio** (size); real `convert-dem` needs the GUI
  exe or a source install with `--extra convert`. `gacos-import` works in both
  exes.
- EGM2008 sources converted with the bundled **EGM96** grid are a sub-metre
  approximation (warned); supply `--geoid-grid` for an exact EGM2008 conversion.
- No coordinate reprojection in conversion (input DEM must be EPSG:4326 lon/lat,
  which is what OpenTopography returns).
- No code signing; no official GitHub Release/installer published yet.

## 5. Validation

Run from the repo root with the env synced (`uv sync --extra gui --extra
download --extra convert`).

- `uv run ruff check .` and `uv run ruff format --check .` — clean.
- `uv run pytest` — full suite green. The end-to-end GeoTIFF conversion tests run
  only when `rasterio` is installed (`importorskip`); CI without the `convert`
  extra skips them.
- Geoid grid sanity: global undulation extrema match the known EGM96 values
  (Indian Ocean low ≈ −107 m at 4.75 N/78.75 E; New Guinea high ≈ +85 m at
  8.25 S/147.25 E).
- Local exe builds: `scripts/build_windows_gui_exe.ps1` (GUI, bundles
  rasterio + geoid, off-screen self-test) and `scripts/build_windows_exe.ps1`
  (CLI, geoid bundled, help/offline smoke tests). Installer:
  `scripts/build_windows_installer.ps1` (needs Inno Setup 6).

## 6. Release steps (maintainer action)

1. Review/commit the v0.15.0 changes.
2. `git push origin main`.
3. Tag and push: `git tag v0.15.0 && git push origin v0.15.0` — this triggers
   `.github/workflows/release.yml`, which builds and smoke-tests the Windows exe
   and attaches it to the GitHub Release, after which `update-check` reports the
   new version to users.
4. (Optional) Build the installer locally with `scripts/build_windows_installer.ps1`
   and attach it to the same Release, or add an Inno Setup step to the workflow.
