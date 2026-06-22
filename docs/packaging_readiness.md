# Packaging readiness

This document records whether `insar-prep` is ready to be packaged into a
standalone Windows executable and the result of the first packaging experiment.
The readiness checklist was written in Task 021; the actual PyInstaller build was
performed in Task 022 (see "Task 022 build result" below).

## 1. Current packaging status

- Stage: **offline CLI MVP**, version `0.1.0` (unchanged by packaging work).
- The full `insar-prep prepare` workflow runs offline and is covered by unit +
  end-to-end tests (`uv run pytest`).
- As of Task 022, a working one-file Windows exe can be built locally via
  `scripts/build_windows_exe.ps1`. Build artifacts (`build/`, `dist/`, `*.spec`,
  `*.manifest`, `*.exe`) are git-ignored and are never committed.
- For the overall release-readiness review (supported / not-supported feature
  lists, release checklist, and tag suggestion) see
  [`release_readiness_v0_1_0.md`](release_readiness_v0_1_0.md). No official
  release or installer is published.

## 2. CLI entry point

- Console script (stable): `pyproject.toml` → `[project.scripts]`
  `insar-prep = "insar_prep.cli.main:main"`.
- `insar_prep.cli.main:main(argv=None) -> int` is a plain function that returns a
  process exit code; `main.py` also guards
  `if __name__ == "__main__": raise SystemExit(main())`.
- Verified usable: `insar-prep --help`, `insar-prep --version`, and
  `insar-prep prepare --help` all exit 0.
- `__version__` is a hard-coded literal in `insar_prep/__init__.py`
  (`__version__ = "0.1.0"`). It does **not** use `importlib.metadata`, so
  `--version` keeps working inside a frozen exe (no package metadata required).

## 3. Runtime dependencies

Declared in `pyproject.toml`:

- `pydantic>=2` — pydantic v2 ships a compiled extension (`pydantic_core`).
- `shapely>=2` — wraps the native **GEOS** library and pulls in **numpy**.

`numpy` is therefore a transitive runtime dependency (via shapely). The package
itself imports only `pydantic` and `shapely` plus the standard library; a repo
scan found **no** `importlib`, `pkg_resources`, `__file__`-relative resource
loading, dynamic `__import__`, or data-file access in `src/insar_prep`.

## 4. Files that must NOT be bundled

- `tests/` (including `tests/fixtures/` and `tests/e2e/`) — test data only.
- `参考项目/` — third-party study code (already ruff-excluded and git-ignored).
- `.env`, `.netrc`, `*.key`, `*.token`, and any credentials.
- `*.SAFE`, `*.zip`, `*.tif`, and DEM/SLC data.
- Development docs are optional and not required at runtime.

The CLI loads **no** templates or data files, so nothing inside the package needs
to be added via PyInstaller `--add-data`.

## 5. Files that may be generated at runtime

All under the user-supplied `--output-root` (never inside the exe):

- `<output_root>/<region_safe_name>/07_reports/<region_safe_name>_data_preparation_report.json`
- the matching `.md` report.
- the matching `.html` report (a self-contained static page added in Task 031;
  inline CSS, no external network/CSS/JS/CDN).
- `<output_root>/<region_safe_name>/07_reports/<region_safe_name>_manifest.csv`
  (the flat prepare-run manifest added in Task 026).
- `<output_root>/<region_safe_name>/07_reports/<region_safe_name>_warnings.csv`
  (the prepare-run problem summary added in Task 028).
- `<output-dir>/asf_download_plan/asf_download_plan.json` and `.csv` from the
  `plan-asf-downloads` dry-run planner (Task 033): a download *plan* only, with
  no `.zip`/`.SAFE` ever created and no network/credentials used. The Windows
  smoke test (Task 036) exercises this subcommand in the frozen exe.

File logging (`app.log` / `task.log` / `events.jsonl` / `errors.log`) is written
**only** when `configure_region_logging` / `configure_global_logging` is called;
the `prepare` CLI does not call them, so no log directory is created implicitly.

## 6. Windows path considerations

- The CLI accepts paths as strings and normalizes them via `pathlib.Path`, so
  both `\` and `/` separators work.
- Paths containing spaces must be quoted by the shell, e.g.
  `--output-root "C:\My Work\workspace"`.
- An end-to-end test (`test_prepare_workflow_handles_output_root_with_spaces`)
  exercises an `--output-root` that contains a space, fully offline.
- Report directory and file names are SARscape-safe (snake_case), so they avoid
  spaces and special characters regardless of the human-readable `--region-name`.

## 7. PyInstaller command

The simplest candidate (kept for reference; not the one used):

```bash
uv run pyinstaller --onefile --name insar-prep src/insar_prep/cli/main.py
```

The command actually used by `scripts/build_windows_exe.ps1` in Task 022 (builds
successfully — see section 10):

```bash
uv run pyinstaller --clean --noconfirm --onefile --name insar-prep \
  --paths src \
  --collect-all shapely \
  --collect-submodules pydantic \
  packaging/insar_prep_entry.py
```

Rationale for the changes:

- **Dedicated entry script** (`packaging/insar_prep_entry.py`, to be created in
  Task 022) of the form
  `from insar_prep.cli.main import main` then `raise SystemExit(main())`.
  Freezing a module that lives *inside* a package as a top-level script can cause
  double-import / relative-path edge cases; a thin external entry avoids them.
- `--paths src` ensures the src-layout package `insar_prep` is importable during
  analysis.
- `--collect-all shapely` collects the bundled **GEOS** native libraries (and
  numpy data) that shapely needs at runtime.
- `--collect-submodules pydantic` (or `--collect-all pydantic`) helps ensure the
  `pydantic_core` binary is collected.
- `uv run --with pyinstaller ...` keeps PyInstaller out of the project's declared
  dependencies (install it only for the build).

## 8. Known risks

1. **shapely / GEOS**: the native GEOS DLL must be bundled, otherwise the exe
   fails when importing `insar_prep.processing.aoi`. Mitigate with
   `--collect-all shapely` and a runtime smoke test of a `--bbox` command.
2. **pydantic_core**: pydantic v2's compiled core must be present; verify with a
   `--version` + `prepare` smoke run on a machine without Python installed.
3. **numpy** (via shapely): increases exe size and may pull OpenBLAS DLLs; verify
   there are no missing-DLL errors.
4. **`--onefile` startup cost**: one-file exes unpack to a temp directory on each
   run; `--onedir` is an alternative to evaluate for faster startup.
5. **Antivirus / SmartScreen**: unsigned exes may be flagged; code signing is out
   of scope for the MVP.

## 9. Pre-packaging checklist

- [x] Stable console entry point (`insar_prep.cli.main:main`).
- [x] `--help` / `--version` / `prepare --help` all exit 0.
- [x] `__version__` is a literal (no `importlib.metadata` at runtime).
- [x] No dynamic imports or bundled data files in `src/insar_prep`.
- [x] `uv run pytest`, `ruff check`, and `ruff format --check` all pass.
- [x] `.gitignore` excludes `build/`, `dist/`, `*.spec`, `*.manifest`, `*.exe`.
- [x] Windows path-with-spaces handling covered by a test.
- [x] (Task 022) Added `packaging/insar_prep_entry.py` + `scripts/build_windows_exe.ps1`; PyInstaller build succeeds.
- [x] (Task 022) exe `--help` / `--version` / `prepare --help` + offline `prepare` smoke test pass on the build machine.
- [ ] (Task 022+) Runtime smoke test of the exe on a clean Windows machine (no Python installed).

## 10. Task 022 build result

Built with `scripts/build_windows_exe.ps1` (PyInstaller 6.21.0, Python 3.11.15,
Windows):

- Output: `dist/insar-prep.exe`, one-file, **~28 MB**.
- exe smoke tests pass: `--help`, `--version` (`insar-prep 0.1.0`),
  `prepare --help`, and an offline `prepare` run that wrote both the JSON and
  Markdown reports with no network and no `.tif`.
- PyInstaller used the contrib **shapely** hook (bundling the `shapely.libs` GEOS
  DLLs) and the **numpy** hook (`numpy.libs`), and the **pydantic** hook
  (collecting `pydantic_core`). No missing-DLL errors at runtime.
- Artifacts (`build/`, `dist/`, `insar-prep.spec`) are git-ignored; `git status`
  shows none of them tracked.

Observations / follow-ups:

- `--collect-all shapely` also drags in `shapely.tests`, inflating size. The
  contrib `hook-shapely` already collects the GEOS binaries, so a leaner build can
  drop `--collect-all shapely` (rely on the hook) or use `--collect-binaries
  shapely`; worth measuring later.
- Harmless `WARNING: Hidden import "tzdata" not found` — the app uses stdlib UTC
  only, so no IANA tz database is required.
- A `--onedir` build (vs `--onefile`) starts faster and avoids per-run temp
  extraction; evaluate if startup latency matters.
- Build ran from an elevated shell (PyInstaller prints a deprecation notice);
  prefer a non-admin terminal for future builds.

## 11. Task 027 rebuild + manifest verification

Rebuilt `dist/insar-prep.exe` from the current code (which includes the Task 026
`manifest.csv`) with `scripts/build_windows_exe.ps1` and re-ran the smoke package:

- The rebuilt one-file exe is **~28 MB**; `--help`, `--version`
  (`insar-prep 0.1.0`), and `prepare --help` all exit 0.
- The build's offline `prepare` smoke run now also prints the `Manifest:` path,
  confirming the frozen exe carries the manifest output.
- `scripts/make_windows_smoke_package.ps1` was extended so the generated
  `run_smoke_test.ps1` additionally asserts: the `prepare` stdout contains
  `Manifest:`; `<region>_manifest.csv` exists in `07_reports`; the manifest's
  first line is the fixed header
  `section,item_type,item_id,item_name,status,path,value,notes`; and the manifest
  inventories the `workflow`, `scene`, `orbit`, `dem`, `gacos`, and `report`
  sections — alongside the existing no-`.tif` and untouched-GACOS-inputs checks.
- Still offline only; no installer, signing, upload, or release. Build artifacts
  (`build/`, `dist/`, `*.spec`, `*.exe`) and `smoke_package/` remain git-ignored
  and were not committed.

## 12. Task 030 rebuild + AOI import smoke verification

Rebuilt `dist/insar-prep.exe` from the current code (which includes the Task 029
`--aoi-geojson` / `--aoi-wkt` AOI import) with `scripts/build_windows_exe.ps1` and
re-ran the extended smoke package:

- The rebuilt one-file exe is **~28 MB**; `--help`, `--version`
  (`insar-prep 0.1.0`), and `prepare --help` all exit 0, and `prepare --help` now
  advertises the mutually exclusive `--bbox | --aoi-geojson | --aoi-wkt` group.
- `scripts/make_windows_smoke_package.ps1` now also writes an EPSG:4326 Polygon
  `input/aoi.geojson` sample, and the generated `run_smoke_test.ps1` runs the full
  offline `prepare` workflow **three times** — once per AOI source (`--bbox`,
  `--aoi-geojson`, `--aoi-wkt`) — asserting for each run the four report files
  (JSON, Markdown, `manifest.csv`, `warnings.csv`), the fixed manifest/warnings
  headers, the manifest section coverage, and a `JSON:`/`Markdown:`/`Manifest:`/
  `Warnings:` stdout line, plus the shared no-`.tif` and untouched-GACOS-inputs
  checks. `SMOKE TEST PASSED` on this machine.
- Still offline only; no installer, signing, upload, or release. Build artifacts
  (`build/`, `dist/`, `*.spec`, `*.exe`) and `smoke_package/` remain git-ignored
  and were not committed.

## 13. Desktop GUI beta (Tasks 037-043) and packaging scope

The optional PySide6 desktop GUI (`insar-prep gui`) completes its offline beta
loop in Task 043: Workspace -> Project -> Region -> AOI (bbox / GeoJSON / WKT) ->
ASF cart import -> scene consistency check -> offline orbit / DEM / GACOS planning
-> five-file report generation (JSON, Markdown, HTML, `manifest.csv`,
`warnings.csv`). The GUI calls the existing core interfaces only; it performs no
downloads, no network access, and no real DEM vertical-datum conversion.

Packaging scope and constraints:

- **PySide6 is an optional extra**, declared as `[project.optional-dependencies]`
  `gui` in `pyproject.toml` and installed with `uv sync --extra gui`. It is **not**
  a runtime dependency of the offline CLI, and the current PyInstaller build
  (`scripts/build_windows_exe.ps1`) freezes the **CLI only** -- PySide6 is not
  bundled. Freezing the GUI (a much larger Qt bundle) is intentionally out of
  scope for the `v0.1.0-offline-cli` line.
- The Windows smoke package (`scripts/make_windows_smoke_package.ps1`) still
  exercises the **frozen CLI exe** only and is intentionally left unchanged: the
  GUI is not part of that artifact, so adding GUI steps there would be misleading.
- The GUI is covered instead by offscreen PySide6 unit tests
  (`tests/unit/test_gui_*.py`) and an end-to-end beta workflow smoke test
  (`tests/e2e/test_gui_beta_workflow.py`) that runs with the network blocked and
  asserts the five report files are produced with no `.tif` / `.zip` / `.SAFE`
  data created. These run as part of `uv run pytest` (the GUI tests skip
  automatically when the `gui` extra is not installed).
- No GUI build artifacts are produced or committed; the version stays `0.1.0` and
  the `v0.1.0-offline-cli` tag is unchanged.
