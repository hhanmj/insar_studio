# Packaging readiness (Task 021)

This document records whether `insar-prep` is ready to be packaged into a
standalone Windows executable, and what the next packaging task (Task 022) should
do. **No executable is built in this task** — this is a readiness checklist only.
PyInstaller is **not** installed, **not** run, and **not** added as a dependency
here.

## 1. Current packaging status

- Stage: **offline CLI MVP**, version `0.1.0` (unchanged by this task).
- The full `insar-prep prepare` workflow runs offline and is covered by unit +
  end-to-end tests (`uv run pytest`).
- No `build/`, `dist/`, `*.spec`, `*.manifest`, or `*.exe` artifacts are produced
  or committed.

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

## 7. PyInstaller candidate command for Task 022

The simplest candidate (do **not** run in Task 021):

```bash
uv run pyinstaller --onefile --name insar-prep src/insar_prep/cli/main.py
```

Recommended, more robust candidate for Task 022 (also not run here):

```bash
uv run --with pyinstaller pyinstaller --onefile --name insar-prep \
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
- [ ] (Task 022) Add `packaging/insar_prep_entry.py` and build with PyInstaller.
- [ ] (Task 022) Runtime smoke test of the exe on a clean Windows machine.
