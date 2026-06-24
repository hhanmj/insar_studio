# Release readiness — v0.16.0

This document captures the **release-readiness** state of `insar-prep` as
**`v0.16.0`**. It records what changed since v0.15.0 so a deliberate tag/release
is a simple, traceable step. It does **not** itself cut a GitHub Release, push a
tag, or upload artifacts — those remain a maintainer action (see §6).

It supersedes
[`release_readiness_v0_15_0.md`](release_readiness_v0_15_0.md).

## 1. Version status

- Version: **`0.16.0`** (bumped from `0.15.0`; see `pyproject.toml` and
  `insar_prep/__init__.py` → `__version__ = "0.16.0"`).
- `--version` prints `insar-prep 0.16.0`. `__version__` is a hard-coded literal,
  so it keeps working inside a frozen exe.
- Suggested tag (maintainer action, not in this change): `v0.16.0`. Existing tags
  `v0.1.0-offline-cli`, `v0.12.0-gui-beta` are retained.

## 2. What is new in v0.16.0

- **Real GACOS request + download** (`gacos-request` / `gacos-download` +
  GUI panel, opt-in `download` extra). GACOS has no API, so the client automates
  the two steps the service permits: it `POST`s the web request form
  (`http://www.gacos.net/M/action_page.php`, fields N/S/W/E/H/M/date/type/email)
  in ≤20-date batches, and fetches the **emailed** result archive (http/https/ftp,
  `.part` + atomic rename) then extracts / organizes / integrity-checks it via the
  existing importer. The email link is pasted in by the user (no mailbox scraping,
  no browser automation, no stored password). `gacos-auth` stores the delivery
  email in the OS keyring. New error codes `GAC003`/`GAC004`.
- **Runtime language switch** (English / 中文): a dependency-free `i18n` layer and
  a GUI *Language* menu that retranslates the whole window live; the choice is
  persisted per user and restored on launch.
- **Packaging**: `release.yml` now also compiles the Inno Setup **installer**
  (`insar-prep-gui-<version>-setup.exe`) and publishes it next to the CLI and GUI
  exes.

## 3. Completed capabilities (cumulative)

Offline core (`prepare`, `plan-asf-downloads`) — unchanged and still
network-free. Opt-in real I/O: ASF SLC download (`download-asf`), OpenTopography
DEM download (`download-dem`), DEM vertical-datum conversion (`convert-dem`,
`convert` extra), GACOS product import (`gacos-import`, stdlib), and **GACOS
request/download** (`gacos-request`/`gacos-download`, `download` extra). PySide6
GUI drives the offline loop plus the real ASF/DEM/GACOS panels and an English/中文
language switch. GitHub-Releases update check (stdlib).

## 4. Explicit non-goals / limitations

- **GACOS still has no API**: the request is submitted and the emailed archive is
  fetched programmatically, but the result link arrives by **email** and is pasted
  in by the user. The client never scrapes a mailbox or drives a browser.
- The **lean CLI exe omits rasterio** (size); real `convert-dem` needs the GUI
  exe or a source install with `--extra convert`. `gacos-request`/`gacos-download`
  need the `download` extra (so they work from the GUI exe or a source install,
  not the lean CLI exe).
- EGM2008 sources converted with the bundled **EGM96** grid are a sub-metre
  approximation (warned); supply `--geoid-grid` for an exact EGM2008 conversion.
- No code signing.

## 5. Validation

Run from the repo root with the env synced (`uv sync --extra gui --extra
download --extra convert`).

- `uv run ruff check .` and `uv run ruff format --check .` — clean.
- `uv run pytest` — full suite green (GACOS request/download, the i18n layer, and
  the GUI language switch are covered with injected fakes / banned sockets; the
  GeoTIFF conversion tests run only when `rasterio` is installed).
- Local exe builds: `scripts/build_windows_exe.ps1` (CLI; smoke-tests the new
  `gacos-request`/`gacos-download` help) and `scripts/build_windows_gui_exe.ps1`
  (GUI; off-screen self-test builds the window incl. the GACOS panel + Language
  menu). Installer: `scripts/build_windows_installer.ps1` (needs Inno Setup 6).

## 6. Release steps (maintainer action)

1. Review/commit the v0.16.0 changes.
2. `git push origin main`.
3. Tag and push: `git tag v0.16.0 && git push origin v0.16.0` — this triggers
   `.github/workflows/release.yml`, which builds and smoke-tests the Windows CLI
   and GUI exes, compiles the Inno Setup installer, and attaches all three to the
   GitHub Release, after which `update-check` reports the new version to users.
