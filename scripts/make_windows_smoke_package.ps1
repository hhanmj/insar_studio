<#
.SYNOPSIS
    Assemble a local Windows exe user smoke-test package for insar-prep
    (Task 023). Offline only.

.DESCRIPTION
    Copies the already-built dist\insar-prep.exe into
    smoke_package\insar_prep_windows_smoke\ together with small sample inputs
    (ASF URL cart, orbit EOFs, GACOS products), a user README, and a
    run_smoke_test.ps1 that exercises the offline `prepare` workflow.

    This never contacts the network, reads credentials, builds an installer,
    creates a GUI, or zips/uploads anything. The whole smoke_package\ tree is
    git-ignored and must never be committed.

.NOTES
    Prerequisite: run scripts\build_windows_exe.ps1 first to produce
    dist\insar-prep.exe. Run this script from anywhere; it resolves the repo
    root from its own location.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$exe = Join-Path $RepoRoot "dist\insar-prep.exe"
if (-not (Test-Path $exe)) {
    throw "dist\insar-prep.exe not found. Run scripts\build_windows_exe.ps1 first."
}

$pkgRoot = Join-Path $RepoRoot "smoke_package\insar_prep_windows_smoke"
if (Test-Path $pkgRoot) { Remove-Item -Recurse -Force $pkgRoot }

$inputDir = Join-Path $pkgRoot "input"
$orbitsDir = Join-Path $inputDir "orbits"
$gacosDir = Join-Path $inputDir "gacos"
$outputDir = Join-Path $pkgRoot "output"
foreach ($dir in @($pkgRoot, $inputDir, $orbitsDir, $gacosDir, $outputDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

Write-Host "Copying exe..." -ForegroundColor Cyan
Copy-Item $exe (Join-Path $pkgRoot "insar-prep.exe")

Write-Host "Writing sample inputs..." -ForegroundColor Cyan
# ASF URL cart: two scenes whose dates match the orbit + GACOS samples below.
$cart = @'
# ASF Vertex export - download URLs (one per line)
https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20240101T100000_20240101T100027_052000_064ABC_1234.zip
https://datapool.asf.alaska.edu/SLC/SB/S1B_IW_SLC__1SDV_20240113T100000_20240113T100027_052100_064DEF_5678.zip
'@
# WriteAllText emits UTF-8 without a BOM so the cart's first comment line parses
# cleanly (Set-Content -Encoding utf8 would prepend a BOM on Windows PowerShell).
[System.IO.File]::WriteAllText((Join-Path $inputDir "asf_urls.txt"), $cart)

# Orbit EOFs: empty files are fine; the matcher parses the filename only.
$orbitNames = @(
    "S1A_OPER_AUX_POEORB_OPOD_20240102T120000_V20240101T000000_20240102T235959.EOF",
    "S1B_OPER_AUX_POEORB_OPOD_20240114T120000_V20240113T000000_20240114T235959.EOF"
)
foreach ($name in $orbitNames) {
    New-Item -ItemType File -Force -Path (Join-Path $orbitsDir $name) | Out-Null
}

# GACOS products: tiny non-empty placeholder text; contents are never parsed.
foreach ($stamp in @("20240101", "20240113")) {
    "placeholder ztd; contents are never parsed" |
        Set-Content -Path (Join-Path $gacosDir "$stamp.ztd") -Encoding utf8
    "WIDTH 10" |
        Set-Content -Path (Join-Path $gacosDir "$stamp.ztd.rsc") -Encoding utf8
}

Write-Host "Writing README_SMOKE_TEST.md..." -ForegroundColor Cyan
$readme = @'
# insar-prep - Windows exe smoke test

This is a **local user smoke-test package** - not an official release and not an
installer. It lets you verify the offline `insar-prep` workflow on Windows
**without installing Python**.

## Contents

- `insar-prep.exe`           - the one-file CLI (no Python required)
- `run_smoke_test.ps1`       - runs the exe and checks the output
- `input\asf_urls.txt`       - sample ASF download-URL cart (2 scenes)
- `input\orbits\*.EOF`       - sample Sentinel-1 orbit files (filenames only)
- `input\gacos\*.ztd[.rsc]`  - sample GACOS products (placeholder text)
- `output\`                  - where reports are written

## How to run

Open PowerShell in this folder and run:

```powershell
.\run_smoke_test.ps1
```

Or run the CLI manually:

```powershell
.\insar-prep.exe --help
.\insar-prep.exe --version
.\insar-prep.exe prepare `
  --cart .\input\asf_urls.txt `
  --region-name "Shiliushubao Demo" `
  --output-root .\output `
  --orbit-dir .\input\orbits `
  --dem-plan `
  --bbox 110.1 30.8 110.6 31.2 `
  --gacos-plan `
  --gacos-import-dir .\input\gacos
```

## Expected output

```text
output\shiliushubao_demo\07_reports\shiliushubao_demo_data_preparation_report.json
output\shiliushubao_demo\07_reports\shiliushubao_demo_data_preparation_report.md
output\shiliushubao_demo\07_reports\shiliushubao_demo_manifest.csv
output\shiliushubao_demo\07_reports\shiliushubao_demo_warnings.csv
```

The `manifest.csv` is a flat inventory of this run, with the fixed header
`section,item_type,item_id,item_name,status,path,value,notes` and rows for the
workflow, scenes, orbit/DEM/GACOS modules, and the generated report files. The
`warnings.csv` summarizes only the problems (WARNING/ERROR), with the fixed
header `severity,section,item_type,item_id,item_name,code,message,path,action`;
when nothing is wrong it contains a single INFO "no warnings" summary row.

The run is fully offline: it never downloads data; contacts ASF, OpenTopography,
or GACOS; creates a real DEM `.tif`; or moves/deletes your input files.

## Notes / FAQ

- **Windows Defender / SmartScreen**: the exe is unsigned, so Windows may warn on
  first run. That is expected for a local test build.
- **First start is slow**: a one-file exe unpacks to a temp folder on first run.
- **Paths with spaces** must be quoted, e.g. `--output-root "C:\My Work\out"`.
- **Do not** put real tokens, API keys, or credentials in this folder.
'@
$readme | Set-Content -Path (Join-Path $pkgRoot "README_SMOKE_TEST.md") -Encoding utf8

Write-Host "Writing run_smoke_test.ps1..." -ForegroundColor Cyan
$runner = @'
# Offline smoke test for the insar-prep Windows exe.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$exe = Join-Path $PSScriptRoot "insar-prep.exe"
if (-not (Test-Path $exe)) { throw "insar-prep.exe not found next to this script" }

function Invoke-Checked([string]$Name, [scriptblock]$Body) {
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)" }
    Write-Host "[OK] $Name" -ForegroundColor Green
}

Invoke-Checked "exe --help" { & $exe --help | Out-Null }
Invoke-Checked "exe --version" { & $exe --version }
Invoke-Checked "exe prepare --help" { & $exe prepare --help | Out-Null }

$gacos = Join-Path $PSScriptRoot "input\gacos"
$before = Get-ChildItem $gacos | ForEach-Object { "$($_.Name):$($_.Length)" } | Sort-Object

# Capture stdout so we can assert the printed report paths (incl. Manifest).
$prepareOut = & $exe prepare `
  --cart .\input\asf_urls.txt `
  --region-name "Shiliushubao Demo" `
  --output-root .\output `
  --orbit-dir .\input\orbits `
  --dem-plan `
  --bbox 110.1 30.8 110.6 31.2 `
  --gacos-plan `
  --gacos-import-dir .\input\gacos 2>&1
if ($LASTEXITCODE -ne 0) { throw "exe prepare (full offline workflow) failed (exit $LASTEXITCODE)" }
$prepareText = ($prepareOut | Out-String)
Write-Host "[OK] exe prepare (full offline workflow)" -ForegroundColor Green

if ($prepareText -notmatch "Manifest:") { throw "stdout did not report a Manifest path" }
Write-Host "[OK] stdout reports a Manifest path" -ForegroundColor Green

if ($prepareText -notmatch "Warnings:") { throw "stdout did not report a Warnings path" }
Write-Host "[OK] stdout reports a Warnings path" -ForegroundColor Green

$reportDir = Join-Path $PSScriptRoot "output\shiliushubao_demo\07_reports"
$json = Join-Path $reportDir "shiliushubao_demo_data_preparation_report.json"
$md = Join-Path $reportDir "shiliushubao_demo_data_preparation_report.md"
$manifest = Join-Path $reportDir "shiliushubao_demo_manifest.csv"
$warnings = Join-Path $reportDir "shiliushubao_demo_warnings.csv"
foreach ($file in @($json, $md, $manifest, $warnings)) {
    if (-not (Test-Path $file)) { throw "Report file missing: $file" }
}
Write-Host "[OK] JSON + Markdown + manifest + warnings reports present" -ForegroundColor Green

# The manifest header is a fixed contract; do not let it drift.
$expectedHeader = "section,item_type,item_id,item_name,status,path,value,notes"
$header = Get-Content $manifest -TotalCount 1
if ($header -ne $expectedHeader) { throw "Unexpected manifest header: $header" }
Write-Host "[OK] manifest header is the fixed 8-column contract" -ForegroundColor Green

# Every workflow section must be inventoried (each is the first CSV column).
$manifestText = Get-Content $manifest -Raw
foreach ($section in @("workflow", "scene", "orbit", "dem", "gacos", "report")) {
    if ($manifestText -notmatch "(?m)^$section,") { throw "manifest missing section: $section" }
}
Write-Host "[OK] manifest covers workflow/scene/orbit/dem/gacos/report" -ForegroundColor Green

# warnings.csv is the problem summary; its header is a fixed contract too.
$expectedWarningsHeader = "severity,section,item_type,item_id,item_name,code,message,path,action"
$warningsHeader = Get-Content $warnings -TotalCount 1
if ($warningsHeader -ne $expectedWarningsHeader) {
    throw "Unexpected warnings header: $warningsHeader"
}
Write-Host "[OK] warnings header is the fixed 9-column contract" -ForegroundColor Green

if (Get-ChildItem -Path $PSScriptRoot -Recurse -Filter *.tif -ErrorAction SilentlyContinue) {
    throw "Unexpected .tif produced by the offline smoke test"
}
Write-Host "[OK] no .tif produced" -ForegroundColor Green

$after = Get-ChildItem $gacos | ForEach-Object { "$($_.Name):$($_.Length)" } | Sort-Object
if (Compare-Object $before $after) { throw "GACOS input files were modified" }
Write-Host "[OK] GACOS input files unchanged" -ForegroundColor Green

Write-Host ""
Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
'@
$runner | Set-Content -Path (Join-Path $pkgRoot "run_smoke_test.ps1") -Encoding utf8

Write-Host ""
Write-Host "Smoke package created at:" -ForegroundColor Green
Write-Host "  $pkgRoot"
Write-Host "Run it with:"
Write-Host "  cd `"$pkgRoot`"; .\run_smoke_test.ps1"
