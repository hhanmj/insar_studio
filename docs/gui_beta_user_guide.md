# GUI Beta — user guide

This guide explains how to install, launch, and use the **optional desktop GUI**
of `insar-prep`. It documents the GUI *as it actually behaves today*; it does not
describe planned features.

> The GUI is a **beta**. It drives the same data-preparation workflow as the CLI
> by calling the existing `insar_prep` core interfaces only. There is **no
> official GUI release, installer, or `.exe`** — you run it from source with `uv`.
> The offline workflow needs no network; **real ASF Sentinel-1 SLC download is an
> explicit opt-in** (the *Download* panel, behind the `download` extra and your
> NASA Earthdata login).

## 1. GUI Beta status

- The status is **GUI Beta**.
- The **offline `prepare` workflow is runnable end to end** from the GUI:
  Workspace → Project → Region → AOI → ASF cart → scene check → offline planning
  → reports.
- The GUI re-implements **no** business logic. Every step calls the same core
  functions the CLI uses (AOI import, ASF cart parsing, scene checks, orbit/DEM/
  GACOS planning, report writing).
- The GUI still **does not** support **real downloads** (ASF/SLC, orbit, DEM, or
  GACOS products).
- The GUI still **does not** perform **real DEM vertical-datum conversion** (DEM
  steps are *planned only*; no `.tif` is created).
- The GUI still **does not** support **Shapefile / KML / GeoPackage** AOI inputs
  (bounding box, GeoJSON, and WKT only; EPSG:4326 lon/lat).

## 2. Installation

The GUI is optional and is **not** installed by default. Install the base CLI,
then add the `gui` extra (which pulls in PySide6).

CLI only:

```bash
uv sync
```

CLI + GUI:

```bash
uv sync --extra gui
```

Requirements: Python 3.11 and [uv](https://docs.astral.sh/uv/). No account,
token, or network access is required to run the GUI.

## 3. Launch

```bash
uv run --extra gui insar-prep gui
```

To see the subcommand help without launching the window (this works even when
PySide6 is not installed):

```bash
uv run insar-prep gui --help
```

If PySide6 is missing, `insar-prep gui` does **not** crash with a traceback. It
prints a single clear line tagged with the `GUI001` error code and exits
non-zero:

```text
[GUI001] PySide6 is required for the GUI. Install with: uv sync --extra gui
```

Every other CLI command keeps working without PySide6.

## 4. GUI layout

The main window (title **INSAR Prep Assistant**) has four zones:

- **Left — Workspace / Project / Region tree.** Shows the current hierarchy. A
  Region is marked `[AOI set]` once an AOI is bound to it.
- **Centre — workflow panels** (scrollable, top to bottom): the workflow-step
  labels, then the **AOI**, **ASF cart import**, **scene table**, **scene check**,
  **offline planning (orbit / DEM / GACOS)**, and **Reports** panels.
- **Right — task queue + log summary** panel.
- **Bottom — warnings / errors status bar.** Starts at `Ready` and shows the
  result of the last action, including any coded error.

A **toolbar** at the top provides the *New Workspace*, *New Project*, and
*New Region* actions.

The workflow-step labels shown in the centre are: `Workspace`, `Project`,
`Region / AOI`, `ASF Cart`, `Scene Check`, `Orbit / DEM / GACOS Plan`, `Reports`.

## 5. Offline workflow

Run the steps in order. Each step reports success or a coded error in the bottom
status bar.

1. **Create a Workspace** — toolbar → *New Workspace*. Enter a workspace root
   (and optional name).
2. **Create a Project** — toolbar → *New Project*. Requires a workspace first,
   otherwise the status bar shows `GUI002`.
3. **Create a Region** — toolbar → *New Region*. Requires a project first
   (`GUI002`). Region names are normalized to a SARscape-safe (snake_case) name.
4. **Set the AOI** — in the **AOI** panel, pick exactly one source and apply:
   - **Manual bounding box**: West / South / East / North (degrees, EPSG:4326);
   - **GeoJSON file path** (`Polygon` / `MultiPolygon`, `Feature`, or
     `FeatureCollection`; multiple features are merged and their combined bounds
     used);
   - **WKT string** (`POLYGON` / `MULTIPOLYGON`).

   The three sources are mutually exclusive. Invalid input is reported as
   `AOI001`; with no Region selected the status bar shows `GUI002`. On success the
   tree marks the Region `[AOI set]`.
5. **Import an ASF cart** — in the **ASF cart import** panel, enter the path to a
   locally exported ASF cart (Vertex Python script, URL text, CSV, or GeoJSON)
   and import. Parsed scenes appear read-only in the **scene table** (scene id,
   platform, acquisition time, product, beam, polarization, URL status). A bad or
   unparseable cart is reported as `ASF001`; no Region selected → `GUI002`.
6. **Run the scene check** — in the **scene check** panel, optionally pick an
   expected polarization, then run. It shows the total scene count, the
   error/warning counts, and the issue list, and links the result to the bottom
   bar (error count, warning count, or `Ready`).
7. **Run offline planning** — in the **offline planning** panel:
   - **Orbit**: enter a local orbit (`.EOF`) directory and *Scan and match
     orbits*; shows matched / unmatched counts. A missing directory → `ORB001`.
   - **DEM**: choose dataset / provider / source & target vertical datum and
     *Build DEM plan*. This is **planned only** — it shows the computed raw /
     ellipsoid / SARscape-ready DEM paths and creates **no `.tif`** and performs
     **no real conversion**. With no AOI set → `AOI001`.
   - **GACOS**: *Build GACOS plan* from the scene dates (shows date / batch
     counts); optionally enter a local GACOS product directory to run the
     read-only import check (found / missing dates). With no scenes imported →
     `GAC001`.

   All planning steps require a current Region (`GUI002`).
8. **Generate reports** — in the **Reports** panel, enter an output root and
   *Generate reports*. With no Region selected → `GUI002`; with no output root →
   `GUI003`. If the scene check was not run yet, it is run automatically so the
   report always has a scene-consistency section.
9. **Confirm the five outputs.** The report set is written, with SARscape-safe
   names, under:

   ```text
   <output_root>/<region_safe_name>/07_reports/
     <region_safe_name>_data_preparation_report.json
     <region_safe_name>_data_preparation_report.md
     <region_safe_name>_data_preparation_report.html
     <region_safe_name>_manifest.csv
     <region_safe_name>_warnings.csv
   ```

   The Reports panel lists the exact output paths and the overall status
   (`ready` / `ready_with_warnings` / `blocked`).

This is the same five-file report set the CLI `prepare` command produces, written
by the same reporting backend.

## 6. Current limitations

By design, the GUI Beta does **not**:

- download real SLC data;
- download real orbit files;
- download real DEMs;
- perform real DEM vertical-datum conversion (DEM steps are planned only; no
  `.tif` is created);
- submit, scrape, or automate the GACOS web service;
- read or store credentials (no login, token, or account input);
- require any network access;
- accept Shapefile / KML / GeoPackage AOI inputs, or perform coordinate
  transforms (EPSG:4326 lon/lat only);
- ship as an official GUI release, installer, or `.exe`.

These boundaries match the CLI: the GUI is a front-end over the same offline
core, not a new capability layer. Real download support and real DEM conversion
remain intentionally deferred to separate, later, explicitly-authorized work.

## 7. See also

- [`gui_beta_smoke_test.md`](gui_beta_smoke_test.md) — pre-delivery / pre-demo
  smoke-test checklist for the GUI Beta.
- [`release_readiness_v0_1_0.md`](release_readiness_v0_1_0.md) — the v0.1.0
  offline CLI MVP release-readiness review.
- The repository `README.md` — project scope, the offline CLI workflow, and the
  desktop GUI (beta) summary.
