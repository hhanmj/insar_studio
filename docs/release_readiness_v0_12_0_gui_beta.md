# Release readiness — v0.12.0 (GUI Beta)

This document captures the **release-readiness** state of `insar-prep` as
**`v0.12.0 GUI Beta`**. It is a version / documentation / test alignment review
only: it does **not** cut a GitHub Release, build or upload an executable, create
a tag, or change any business logic. Its purpose is to record a traceable
**GUI Beta baseline** so a future, deliberate tag/release is a simple step.

It supersedes the [`release_readiness_v0_1_0.md`](release_readiness_v0_1_0.md)
review (the previous v0.1.0 offline CLI MVP baseline), which is retained.

## 1. Version status

- Version: **`0.12.0`** (bumped from `0.1.0`; see `pyproject.toml` and
  `insar_prep/__init__.py` → `__version__ = "0.12.0"`).
- Status: **GUI Beta**.
- `--version` prints `insar-prep 0.12.0` (verified via `uv run insar-prep
  --version`). `__version__` is a hard-coded literal, so `--version` keeps working
  inside a frozen exe (no `importlib.metadata` lookup at runtime).
- Tag to be created later (Task 046, **not** in this task): `v0.12.0-gui-beta`.
- The previous baseline tag suggestion `v0.1.0-offline-cli` is retained and is
  **not** moved or deleted.

## 2. Completed capabilities

All capabilities below are offline and covered by the unit + end-to-end test
suite.

- **Offline CLI `prepare` workflow**: one command wires the whole offline pipeline
  (ASF cart parse → scene check → optional orbit/DEM/GACOS planning → reports).
- **Five-file report set**: JSON, Markdown, self-contained HTML, `manifest.csv`,
  and `warnings.csv`, written under `<output_root>/<region_safe_name>/07_reports/`
  with SARscape-safe names, credential-masked.
- **AOI input**: manual bounding box, GeoJSON, and WKT (EPSG:4326 lon/lat only).
- **ASF cart import**: Vertex Python scripts (regex-only, never executed), URL
  text, CSV, and GeoJSON → Sentinel-1 SLC scenes (deduplicated).
- **Scene consistency check**: duplicates, product/beam/polarization mismatches,
  mixed platforms, missing URL/source, and coverage notes.
- **Orbit / DEM / GACOS offline planning** (planning only): local orbit `.EOF`
  matching (POEORB > MOEORB > RESORB), DEM request + vertical-datum conversion
  *plans* (no `.tif`, no real conversion), and GACOS request batches + read-only
  product import check.
- **PySide6 GUI Beta** (optional `gui` extra): the same offline closed loop driven
  from the desktop — Workspace → Project → Region → AOI → ASF cart → scene check →
  offline planning → reports — calling the existing core interfaces only.
- **GUI Beta documentation**: [`gui_beta_user_guide.md`](gui_beta_user_guide.md)
  and [`gui_beta_smoke_test.md`](gui_beta_smoke_test.md).
- **PyInstaller one-file CLI exe** was smoke-tested earlier (dev-only,
  git-ignored). The **GUI is not packaged as an exe.**

## 3. Explicit non-goals / limitations

The GUI Beta baseline intentionally never performs any of the following:

- no real ASF / Sentinel-1 SLC download;
- no real Sentinel-1 orbit download;
- no real DEM download (no OpenTopography or other DEM API call);
- no real DEM vertical-datum (geoid) conversion;
- no GACOS auto submission / scraping / download;
- no Shapefile / KML / GeoPackage AOI inputs, and no coordinate transforms;
- no credential handling (no login, token, or account input);
- no GUI exe release;
- no GitHub Release, installer, signing, or artifact upload;
- no network access of any kind.

## 4. Validation checklist

Run from the repository root with the project virtual environment synced. None of
these commands touch the network beyond `uv sync` resolving declared packages.

```bash
uv sync
uv sync --extra gui
uv run insar-prep --version          # expect: insar-prep 0.12.0
uv run insar-prep --help
uv run insar-prep gui --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 5. Repository hygiene

All of these must return **no output** (nothing of the kind is tracked):

```bash
git ls-files "*.exe" "*.zip" "*.tif" "*.SAFE" "*.spec"
git ls-files "build/*" "dist/*" "smoke_package/*"
git ls-files ".env" "*.env" ".netrc" "*.key" "*.token"
```

- No exe / zip / tif / SAFE / spec artifacts.
- No `build/`, `dist/`, or `smoke_package/` contents.
- No credentials / secrets.

## 6. Tag plan

- **This task does not create a tag.**
- A future task (**Task 046**) will create an annotated tag for this baseline:

  ```bash
  git tag -a v0.12.0-gui-beta -m "v0.12.0 GUI Beta"
  git push origin v0.12.0-gui-beta
  ```

- The earlier `v0.1.0-offline-cli` baseline tag suggestion is retained and is not
  moved or deleted.
