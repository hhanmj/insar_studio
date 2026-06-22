# GUI Beta — smoke test

A short, repeatable checklist to verify the **GUI Beta** before a delivery or a
demo. It covers both the automated quality gate and a manual click-through of the
offline workflow. Everything here is **offline**: no account, token, or network
access is needed, and nothing is downloaded.

For how to install, launch, and use the GUI, see
[`gui_beta_user_guide.md`](gui_beta_user_guide.md).

## 1. Purpose

Confirm, before showing the GUI to anyone, that:

- the package and the optional `gui` extra install and import cleanly;
- the full automated test suite and the lint/format gate pass;
- the GUI launches and the offline closed loop (Workspace → Project → Region →
  AOI → ASF cart → scene check → offline planning → reports) runs to the
  five-file report set;
- no real download, no network access, and no data files (`.zip` / `.SAFE` /
  `.tif`) are produced.

## 2. Preconditions

- Python 3.11 and [uv](https://docs.astral.sh/uv/) available.
- A clean checkout of this repository.
- A desktop session (a display) for the manual GUI step. The automated tests run
  headless and need no display.
- Offline sample inputs already in the repo:
  - ASF cart: `tests/fixtures/asf/urls.txt`
  - Orbit `.EOF` files: `tests/fixtures/orbits/`
  - GACOS products (optional import check): `tests/fixtures/gacos/`

## 3. Verify the CLI + GUI extra (automated)

Run from the repository root. None of these touch the network beyond `uv sync`
resolving already-declared packages.

```bash
uv sync --extra gui
uv run insar-prep --help
uv run insar-prep --version
uv run insar-prep gui --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Expected:

- `insar-prep --version` prints `insar-prep 0.1.0`.
- `insar-prep gui --help` shows the GUI subcommand help (it works even without
  PySide6 installed).
- `pytest` passes, including the offscreen GUI tests (they run, not skip, once the
  `gui` extra is installed).
- `ruff check` and `ruff format --check` report no problems.

> If you want to confirm the missing-extra path, run `uv run insar-prep gui` in an
> environment **without** PySide6: it must print
> `[GUI001] PySide6 is required for the GUI. Install with: uv sync --extra gui`
> and exit non-zero (no traceback).

## 4. Manual GUI smoke-test steps

Launch the GUI:

```bash
uv run --extra gui insar-prep gui
```

Then click through the workflow (the bottom status bar reports each result):

1. **New Workspace** — toolbar; enter a workspace root. The tree shows the
   workspace.
2. **New Project** — toolbar; enter a name. The tree shows the project.
3. **New Region** — toolbar; enter a name. The tree shows the region.
4. **Set AOI** — AOI panel; pick **Bounding box** and enter, e.g.,
   `West 110.1`, `South 30.8`, `East 110.6`, `North 31.2`; apply. The tree marks
   the region `[AOI set]`. (Optionally repeat with a GeoJSON path or a WKT string
   instead.)
5. **Import ASF cart** — ASF cart panel; enter `tests/fixtures/asf/urls.txt` and
   import. The scene table fills with the parsed scenes; the status bar reports
   the imported scene count.
6. **Run scene check** — scene check panel; run. The panel shows totals and the
   issue list; the bottom bar shows the error/warning count or `Ready`.
7. **Offline planning** — planning panel:
   - **Orbit**: enter `tests/fixtures/orbits/` and *Scan and match orbits*; the
     panel shows matched / unmatched counts.
   - **DEM**: keep the defaults (COP30 / OpenTopography / EGM2008 →
     WGS84_ELLIPSOID) and *Build DEM plan*; the panel shows **PLANNED ONLY** and
     the raw / ellipsoid / SARscape-ready DEM paths. No `.tif` is created.
   - **GACOS**: *Build GACOS plan*; the panel shows the date / batch counts.
     Optionally enter `tests/fixtures/gacos/` to also run the read-only import
     check (found / missing dates).
8. **Generate reports** — Reports panel; enter an output root (e.g. a temporary
   folder) and *Generate reports*. The panel lists the output paths and the
   overall status.

## 5. Expected outputs

After the manual run, the report set exists under the chosen output root:

```text
<output_root>/<region_safe_name>/07_reports/
  <region_safe_name>_data_preparation_report.json
  <region_safe_name>_data_preparation_report.md
  <region_safe_name>_data_preparation_report.html
  <region_safe_name>_manifest.csv
  <region_safe_name>_warnings.csv
```

- All five files are present.
- File and directory names are SARscape-safe (lowercase, digits, underscores;
  no spaces or hyphens), even if the region name contained spaces/hyphens.
- The HTML report opens in a browser as a self-contained static page (no external
  CSS/JS/CDN, no network).

## 6. What should **not** happen

During any of the steps above, none of the following may occur:

- no `.zip` is created anywhere;
- no `.SAFE` directory is created anywhere;
- no `.tif` (DEM) is created anywhere;
- no network connection is made (no ASF/Earthdata/OpenTopography/GACOS contact);
- no credential / token / password prompt or read;
- no uncaught crash or traceback in the terminal.

The DEM and GACOS steps are **plans only**: they compute paths and date batches
but never download or convert anything.

## 7. Troubleshooting

- **`[GUI001] PySide6 is required ...`** — the `gui` extra is not installed.
  Install it with `uv sync --extra gui`, then relaunch with
  `uv run --extra gui insar-prep gui`.
- **The window does not appear / display errors on a headless machine** — the GUI
  needs a real desktop session. For automated verification without a display, rely
  on the test suite, which runs Qt in `offscreen` mode.
- **GUI tests are skipped** — the offscreen GUI tests skip when PySide6 is not
  installed. Run `uv sync --extra gui` first so they execute instead of skipping.
- **Paths with spaces** — always quote paths that contain spaces (especially on
  Windows PowerShell), e.g. `--output-root "C:\My Work\workspace"`. Generated
  output names stay SARscape-safe regardless.
- **PowerShell line continuation** — PowerShell uses a backtick (`` ` ``) for line
  continuation, not the `\` used in bash examples.
