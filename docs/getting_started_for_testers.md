# Getting started (for testers)

A one-page guide for trying the **`insar-prep`** Windows executable. No Python
install is needed — you run a single `insar-prep.exe`.

> `insar-prep` is an **offline InSAR data-preparation assistant**: it parses a
> local ASF cart, checks Sentinel-1 scene consistency, plans orbit/DEM/GACOS
> inputs, and writes a beginner-friendly report. It is **not** a processing
> engine and does not replace SARscape/ISCE/MintPy/SNAP.

There are two things you can test:

- **Track A — Offline (no account needed).** `prepare` reports and download
  *planning*. Never touches the network.
- **Track B — Real download (needs a free NASA Earthdata account).** Actually
  fetch Sentinel-1 SLC `.zip` files from ASF.

## 0. Check the exe runs

Open PowerShell in the folder that contains `insar-prep.exe` and run:

```powershell
.\insar-prep.exe --version
.\insar-prep.exe --help
```

You should see a version line (e.g. `insar-prep 0.12.0`) and the list of
commands: `prepare`, `plan-asf-downloads`, `download-asf`, `auth`, `gui`.

## Track A — Offline (no account)

You need a **local ASF cart** file (exported from ASF Vertex: a Python script,
a URL `.txt`, a `.csv`, or a `.geojson`).

1. **Write a data-preparation report** (the core feature):

```powershell
.\insar-prep.exe prepare `
  --cart .\my_cart.txt `
  --region-name "My Test Area" `
  --output-root .\workspace
```

This writes five files under
`workspace\<region_safe_name>\07_reports\` — `..._data_preparation_report.json`,
`.md`, `.html`, `..._manifest.csv`, and `..._warnings.csv`. Open the `.html` in a
browser for the friendliest view.

2. **Preview the downloads (dry-run, still offline):**

```powershell
.\insar-prep.exe download-asf --cart .\my_cart.txt --output-dir .\workspace
```

This writes `workspace\asf_download_plan\asf_download_plan.{json,csv}` listing the
expected SLC filenames. It downloads nothing and needs no account.

## Track B — Real download (needs Earthdata)

1. **Create a free account** at <https://urs.earthdata.nasa.gov/users/new> (one
   time). A personal **token** can be generated at
   <https://urs.earthdata.nasa.gov/profile>.

2. **Store your credentials once** (saved in the Windows Credential Manager — the
   OS keyring — never in a project file):

```powershell
.\insar-prep.exe auth login
```

It prompts you to paste a token (recommended) **or** enter a username/password.
The password is never echoed and never accepted as a command-line flag.

> Running from source with the `gui` extra? You can instead use the GUI's
> **Earthdata Login** dialog (token field + a button that opens the token page).

3. **Confirm it's stored** (and optionally test it live against Earthdata):

```powershell
.\insar-prep.exe auth status
.\insar-prep.exe auth status --test
```

`status` prints `token`, `login:<user>`, or `none`. `--test` makes one real
authenticated request.

4. **Download for real:**

```powershell
.\insar-prep.exe download-asf `
  --cart .\my_cart.txt `
  --output-dir .\workspace `
  --download-mode real
```

By default `--credential-source auto` finds your stored credentials
(keyring → `$EARTHDATA_TOKEN` → `~/.netrc`). SLCs land under
`workspace\02_slc\<granule>.zip`. Re-running is **safe and resumable**:
already-complete files are skipped, and an interrupted file is continued.

## Where things land

```text
workspace\
  <region_safe_name>\07_reports\   # prepare reports (json/md/html/csv)
  asf_download_plan\               # plan json/csv (+ results.csv after real)
  02_slc\                          # downloaded SLC .zip (real mode only)
```

## Troubleshooting

| You see | Meaning | Fix |
| --- | --- | --- |
| `[DL004] ... is not set` / `no Earthdata credentials` | No credentials found | Run `auth login`, or set `$EARTHDATA_TOKEN`, or add `~/.netrc` |
| `[DL004] ... 'download' extra` | (from-source only) network deps missing | Use the exe, or `uv sync --extra download` |
| `[DL005] ...` | Network/transport error | Check the connection and re-run (it resumes) |
| `[GUI001] PySide6 is required` | The exe is CLI-only | Use the CLI, or run the GUI from source with `--extra gui` |
| Exit code `2` | Bad input / missing arg | Re-check `--cart` path and required flags |

## Safety

- Credentials live only in the **OS keyring** and in memory; they are **never**
  written to the workspace, reports, CSVs, logs, or tracebacks (all output is
  credential-masked). Remove them anytime with `.\insar-prep.exe auth logout`.
- Track A and the `prepare`/`plan-asf-downloads`/`gui` commands make **no**
  network access at all.

## What to report back

When something looks wrong, please include: the exact command, the printed error
line (with its `[CODE]`), the exit code, and your OS — but **never** paste your
token or password.

See also: [`README.md`](../README.md),
[`gui_beta_user_guide.md`](gui_beta_user_guide.md).
