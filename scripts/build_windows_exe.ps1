<#
.SYNOPSIS
    Build a one-file Windows executable for insar-prep with PyInstaller and
    smoke-test it (Task 022 packaging experiment).

.DESCRIPTION
    Offline only. Runs the quality gate, removes previous build artifacts, builds
    dist\insar-prep.exe, and runs exe smoke tests (including one offline `prepare`
    run). It never commits artifacts, builds an installer, creates a GUI, or
    touches the network. Build artifacts (build/, dist/, *.spec) are git-ignored.

.NOTES
    Run from anywhere; the script resolves the repo root from its own location.
#>

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Body
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Body
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
    uv run pyinstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name insar-prep `
        --paths src `
        --collect-all shapely `
        --collect-submodules pydantic `
        packaging/insar_prep_entry.py
}

$exe = Join-Path $RepoRoot "dist\insar-prep.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($sizeMb MB)" -ForegroundColor Green

Invoke-Step "exe --help" { & $exe --help | Out-Null }
Invoke-Step "exe --version" { & $exe --version }
Invoke-Step "exe prepare --help" { & $exe prepare --help | Out-Null }

Write-Host ""
Write-Host "== exe offline prepare smoke test ==" -ForegroundColor Cyan
$demo = Join-Path $env:TEMP "insar_exe_smoke"
if (Test-Path $demo) { Remove-Item -Recurse -Force $demo }
New-Item -ItemType Directory -Force -Path $demo | Out-Null
try {
    $cart = Join-Path $RepoRoot "tests\fixtures\asf\urls.txt"
    & $exe prepare --cart $cart --region-name smoke_demo --output-root $demo
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
}
finally {
    if (Test-Path $demo) { Remove-Item -Recurse -Force $demo }
}

Write-Host ""
Write-Host "== DONE: dist\insar-prep.exe built and smoke-tested ==" -ForegroundColor Green
