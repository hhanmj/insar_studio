# Windows exe smoke-test package

## 1. Purpose

Provide a small, self-contained package so a Windows user can verify the offline
`insar-prep` workflow **without installing Python**. It exercises the one-file
executable end to end against tiny local sample inputs and confirms the JSON +
Markdown reports are produced.

This is **not** an official release, **not** an installer, and does **not** touch
the network. It is a local smoke-test convenience only.

## 2. Prerequisite

Task 022 must have produced the executable at `dist/insar-prep.exe`. If it is
missing, build it first:

```powershell
.\scripts\build_windows_exe.ps1
```

## 3. Generate the smoke package

From the repository root:

```powershell
.\scripts\make_windows_smoke_package.ps1
```

This creates (all git-ignored, never committed):

```text
smoke_package/
└── insar_prep_windows_smoke/
    ├── insar-prep.exe
    ├── README_SMOKE_TEST.md
    ├── run_smoke_test.ps1
    ├── input/
    │   ├── asf_urls.txt
    │   ├── aoi.geojson
    │   ├── orbits/
    │   │   ├── S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T235959.EOF
    │   │   └── S1B_OPER_AUX_POEORB_OPOD_20240114T120000_V20240113T000000_20240114T235959.EOF
    │   └── gacos/
    │       ├── 20240101.ztd
    │       ├── 20240101.ztd.rsc
    │       ├── 20240113.ztd
    │       └── 20240113.ztd.rsc
    └── output/
```

The orbit and GACOS sample dates (2024-01-01, 2024-01-13) match the two scenes in
`asf_urls.txt`. The EOF files are empty on purpose — the orbit matcher parses the
filename only — and the GACOS files contain tiny placeholder text. `aoi.geojson`
is an EPSG:4326 Polygon `Feature` whose bounds equal the demo `--bbox`
(110.1 30.8 110.6 31.2); it drives the `--aoi-geojson` smoke run.

## 4. Run the smoke test

```powershell
cd smoke_package\insar_prep_windows_smoke
.\run_smoke_test.ps1
```

The script runs the exe `--help`, `--version`, and `prepare --help` (asserting the
help advertises `--bbox`, `--aoi-geojson`, and `--aoi-wkt`), then the full offline
`prepare` workflow **three times** — once per AOI source (`--bbox`,
`--aoi-geojson`, `--aoi-wkt`) — each with orbit matching, DEM planning, GACOS
request planning, and GACOS import checking enabled.

## 5. Expected output

The script reports `SMOKE TEST PASSED` after confirming, for each of the three AOI
runs (output under `shiliushubao_demo_bbox`, `shiliushubao_demo_geojson`, and
`shiliushubao_demo_wkt`):

- the exe exits with code `0` for every command;
- `prepare --help` advertises `--bbox`, `--aoi-geojson`, and `--aoi-wkt`;
- the four report files exist in each `07_reports\` directory: the JSON and
  Markdown reports, `<safe_name>_manifest.csv`, and `<safe_name>_warnings.csv`;
- each run's stdout reports a `JSON:`, `Markdown:`, `Manifest:`, and `Warnings:`
  path;
- each manifest's first line is the fixed header
  `section,item_type,item_id,item_name,status,path,value,notes` and inventories
  every workflow section (`workflow`, `scene`, `orbit`, `dem`, `gacos`, `report`);
- each warnings' first line is the fixed header
  `severity,section,item_type,item_id,item_name,code,message,path,action`;
- no real DEM `.tif` was produced;
- the `input\gacos` files were not moved, deleted, or modified.

The `manifest.csv` is produced by the `prepare` workflow added in Task 026, the
`warnings.csv` problem summary by Task 028, and the `--aoi-geojson` / `--aoi-wkt`
AOI sources by Task 029; this smoke test (Task 030) verifies the rebuilt exe
carries all of them.

## 6. FAQ / troubleshooting

- **Windows Defender / SmartScreen warning**: the exe is unsigned, so Windows may
  warn on first launch. This is expected for a local test build; code signing is
  out of scope for the MVP.
- **First start is slow**: a `--onefile` exe unpacks to a temporary folder on each
  run, so the first invocation has extra startup latency.
- **Paths with spaces**: always quote them, e.g.
  `--output-root "C:\My Work\output"`.
- **Unsigned exe**: treat it as a local test artifact, not a distributable.
- **Credentials**: never place real tokens, API keys, or `.netrc` credentials in
  the package directory; the workflow is fully offline and needs none.

## 7. Scope

This package is a **local user smoke test only**. It is not a GitHub release, not
an installer, and not a signed distributable. Producing a real release is a
separate, future task. For the v0.1.0 release-readiness review and checklist, see
[`release_readiness_v0_1_0.md`](release_readiness_v0_1_0.md).
