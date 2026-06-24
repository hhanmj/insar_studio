<#
.SYNOPSIS
    Build a one-file Windows executable for insar-prep with PyInstaller and
    smoke-test it (Task 022 packaging experiment).

.DESCRIPTION
    Runs the quality gate, removes previous build artifacts, builds
    dist\insar-prep.exe, and runs exe smoke tests (offline `prepare`,
    `plan-asf-downloads`, and `download-asf` dry-run). The build bundles the
    optional `download` extra (requests + certifi CA bundle + keyring) so the
    frozen exe is *capable* of `download-asf --download-mode real` and of storing
    Earthdata credentials via `auth` / the GUI dialog in the OS keyring; the build
    and all smoke tests themselves stay offline and never
    download SAR data, build an installer, create a GUI, commit artifacts, or
    touch the network. Build artifacts (build/, dist/, *.spec) are git-ignored.

    The bundled EGM96 geoid grid is included (--collect-data insar_prep) and the
    gacos-import command works in this exe, but real DEM vertical-datum conversion
    (convert-dem) needs rasterio/GDAL, which this lean CLI exe deliberately omits;
    use the GUI exe (build_windows_gui_exe.ps1) or a source install with
    `uv sync --extra convert` for real conversion.

.NOTES
    Run from anywhere; the script resolves the repo root from its own location.
#>

$ErrorActionPreference = "Stop"

function Invoke-Native {
    <#
        Run a native command (uv, PyInstaller, the exe) and decide success solely
        by its process exit code. Native tools may print warnings/deprecations to
        stderr without failing (e.g. PyInstaller's "running as admin" deprecation);
        under $ErrorActionPreference = "Stop" Windows PowerShell turns that stderr
        into a terminating NativeCommandError and would abort an otherwise-
        successful build. Relax the preference to "Continue" only while the command
        runs so warnings stay visible but never fail the step; the caller still
        checks $LASTEXITCODE, and the global "Stop" preference keeps cmdlet errors
        (Remove-Item, New-Item, ...) fatal everywhere else.
    #>
    param([Parameter(Mandatory = $true)][scriptblock]$Body)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Body
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Body
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Invoke-Native $Body
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (exit code $LASTEXITCODE)"
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "Repo root: $RepoRoot"

Invoke-Step "pytest" { uv run pytest }
Invoke-Step "ruff check" { uv run ruff check . }
Invoke-Step "ruff format --check" { uv run ruff format --check . }

Write-Host ""
Write-Host "== Clean previous build artifacts ==" -ForegroundColor Cyan
foreach ($dir in @("build", "dist")) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
Get-ChildItem -Path $RepoRoot -Filter "*.spec" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force

Invoke-Step "PyInstaller build" {
    # Exclude the GUI toolkit: the frozen exe is the CLI tool (the GUI runs from
    # source). Without these excludes, building on a machine that *does* have the
    # optional `gui` extra installed would bundle PySide6 and roughly double the
    # exe size.
    uv run pyinstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name insar-prep `
        --paths src `
        --collect-all shapely `
        --collect-submodules pydantic `
        --collect-all requests `
        --collect-all certifi `
        --collect-all keyring `
        --collect-data insar_prep `
        --copy-metadata keyring `
        --exclude-module PySide6 `
        --exclude-module PySide2 `
        --exclude-module shiboken6 `
        packaging/insar_prep_entry.py
}

$exe = Join-Path $RepoRoot "dist\insar-prep.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($sizeMb MB)" -ForegroundColor Green

Invoke-Step "exe --help" { & $exe --help | Out-Null }
Invoke-Step "exe --version" { & $exe --version }
Invoke-Step "exe prepare --help" { & $exe prepare --help | Out-Null }
Invoke-Step "exe plan-asf-downloads --help" { & $exe plan-asf-downloads --help | Out-Null }
Invoke-Step "exe download-asf --help" { & $exe download-asf --help | Out-Null }
Invoke-Step "exe convert-dem --help" { & $exe convert-dem --help | Out-Null }
Invoke-Step "exe gacos-import --help" { & $exe gacos-import --help | Out-Null }
Invoke-Step "exe gacos-request --help" { & $exe gacos-request --help | Out-Null }
Invoke-Step "exe gacos-download --help" { & $exe gacos-download --help | Out-Null }

Write-Host ""
Write-Host "== exe offline prepare smoke test ==" -ForegroundColor Cyan
$demo = Join-Path $env:TEMP "insar_exe_smoke"
if (Test-Path $demo) { Remove-Item -Recurse -Force $demo }
New-Item -ItemType Directory -Force -Path $demo | Out-Null
try {
    $cart = Join-Path $RepoRoot "tests\fixtures\asf\urls.txt"
    Invoke-Native { & $exe prepare --cart $cart --region-name smoke_demo --output-root $demo }
    if ($LASTEXITCODE -ne 0) { throw "exe prepare failed (exit $LASTEXITCODE)" }
    $reportDir = Join-Path $demo "smoke_demo\07_reports"
    $json = Join-Path $reportDir "smoke_demo_data_preparation_report.json"
    $md = Join-Path $reportDir "smoke_demo_data_preparation_report.md"
    if (-not (Test-Path $json)) { throw "JSON report not generated: $json" }
    if (-not (Test-Path $md)) { throw "Markdown report not generated: $md" }
    if ((Get-ChildItem -Path $demo -Recurse -Filter "*.tif" -ErrorAction SilentlyContinue)) {
        throw "Unexpected .tif produced by offline smoke test"
    }
    Write-Host "Offline prepare smoke test OK: $json" -ForegroundColor Green

    # download-asf dry-run: offline plan only, no network, no SLC archives.
    Invoke-Native { & $exe download-asf --cart $cart --output-dir $demo }
    if ($LASTEXITCODE -ne 0) { throw "exe download-asf dry-run failed (exit $LASTEXITCODE)" }
    $planJson = Join-Path $demo "asf_download_plan\asf_download_plan.json"
    if (-not (Test-Path $planJson)) { throw "download-asf plan not generated: $planJson" }
    if ((Get-ChildItem -Path $demo -Recurse -Filter "*.zip" -ErrorAction SilentlyContinue)) {
        throw "Unexpected .zip produced by offline download-asf dry-run"
    }
    Write-Host "Offline download-asf dry-run smoke test OK: $planJson" -ForegroundColor Green
}
finally {
    if (Test-Path $demo) { Remove-Item -Recurse -Force $demo }
}

Write-Host ""
Write-Host "== DONE: dist\insar-prep.exe built and smoke-tested ==" -ForegroundColor Green
