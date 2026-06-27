<#
.SYNOPSIS
    Build a one-file Windows **desktop** executable for the modern web UI (the
    React frontend hosted in a native WebView2 window via pywebview) and
    smoke-test it off-screen.

.DESCRIPTION
    Builds dist\insar-prep-desktop.exe -- a windowed (no-console) pywebview app
    that loads the bundled ui\dist web frontend and drives the existing in-process
    Python core (insar_prep). The build bundles:
      * the built web UI (ui\dist -> insar_prep\desktop\web),
      * pywebview + pythonnet/clr_loader (the WebView2 backend) + bottle/proxy_tools,
      * shapely (AOI geometry), pydantic, the download extra (requests/certifi/
        keyring) and the convert extra (rasterio/GDAL) + the bundled EGM96 geoid,
    so every panel (AOI / scenes / download plan / DEM convert / report) works in
    the frozen build. The build itself stays offline and downloads no SAR/DEM data.

    The smoke test runs the frozen exe with --selftest, which verifies the bundled
    web assets resolve and exercises the core end-to-end (workspace -> AOI ->
    scenes -> DEM plan/convert -> report) without a window or network, exiting 0.

.PARAMETER SkipUi
    Skip the `npm run build` step and reuse the existing ui\dist.

.NOTES
    Run from anywhere; resolves the repo root from its own location. Requires the
    `desktop`, `download`, and `convert` extras installed in the active env
    (uv sync --extra desktop --extra download --extra convert) plus Node/npm for
    the UI build.
#>

param(
    [switch]$SkipUi
)

$ErrorActionPreference = "Stop"

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Body)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Body } finally { $ErrorActionPreference = $previous }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Body
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Invoke-Native $Body
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)" }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "Repo root: $RepoRoot"

# 1. Build the web frontend (ui\dist) unless explicitly skipped.
$uiDist = Join-Path $RepoRoot "ui\dist\index.html"
if (-not $SkipUi) {
    Invoke-Step "Build web UI (vite)" {
        Push-Location (Join-Path $RepoRoot "ui")
        try { & npm run build } finally { Pop-Location }
    }
}
if (-not (Test-Path $uiDist)) { throw "ui\dist not found ($uiDist); run without -SkipUi" }

$boundaryDirName = "$([char]0x8FB9)$([char]0x754C)"
$chinaName = "$([char]0x4E2D)$([char]0x56FD)"
$provinceName = "$([char]0x7701)"
$cityName = "$([char]0x5E02)"
$countyName = "$([char]0x53BF)"
$boundarySource = Join-Path $RepoRoot $boundaryDirName
$boundaryStage = Join-Path $RepoRoot ".build_boundaries"
if (-not (Test-Path $boundarySource)) {
    throw "Local boundary directory not found: $boundarySource"
}

# 2. Clean previous desktop build artifacts (leave other dist\ files in place).
Write-Host ""
Write-Host "== Clean previous desktop build artifacts ==" -ForegroundColor Cyan
if (Test-Path (Join-Path $RepoRoot "build")) { Remove-Item -Recurse -Force (Join-Path $RepoRoot "build") }
if (Test-Path $boundaryStage) { Remove-Item -Recurse -Force $boundaryStage }
Get-ChildItem -Path $RepoRoot -Filter "insar-prep-desktop.spec" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force
Remove-Item -Force (Join-Path $RepoRoot "dist\insar-prep-desktop.exe") -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $boundaryStage | Out-Null
$boundaryCopies = @(
    @{ Source = "$chinaName`_$provinceName.geojson"; Target = "china_province.geojson" },
    @{ Source = "$chinaName`_$cityName.geojson"; Target = "china_city.geojson" },
    @{ Source = "$chinaName`_$countyName.geojson"; Target = "china_county.geojson" }
)
foreach ($item in $boundaryCopies) {
    $src = Join-Path $boundarySource $item.Source
    $dst = Join-Path $boundaryStage $item.Target
    if (-not (Test-Path $src)) { throw "Boundary file not found: $src" }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

# Call PyInstaller through the venv interpreter directly.
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$pyArgs = @(
    "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "insar-prep-desktop",
    "--paths", "src",
    # Bundle the built web frontend so the WebView loads it from file:// offline.
    "--add-data", "ui/dist;insar_prep/desktop/web",
    # Bundle local administrative boundaries for offline province/city/county AOI.
    "--add-data", ".build_boundaries;insar_prep/desktop/boundaries",
    # pywebview + its WebView2 backend (pythonnet / clr_loader) + http helpers.
    "--collect-all", "webview",
    "--collect-all", "pythonnet",
    "--collect-all", "clr_loader",
    "--collect-all", "bottle",
    "--collect-all", "proxy_tools",
    "--hidden-import", "clr",
    # Core + optional extras the panels exercise (AOI geometry, download, convert).
    "--collect-all", "shapely",
    "--collect-submodules", "pydantic",
    "--collect-all", "requests",
    "--collect-all", "certifi",
    "--collect-all", "keyring",
    "--collect-all", "rasterio",
    "--collect-data", "insar_prep",
    "--copy-metadata", "keyring",
    "packaging/insar_prep_desktop_entry.py"
)

Invoke-Step "PyInstaller desktop build" {
    & $py @pyArgs
}

$exe = Join-Path $RepoRoot "dist\insar-prep-desktop.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($sizeMb MB)" -ForegroundColor Green

Write-Host ""
Write-Host "== Desktop exe off-screen self-test ==" -ForegroundColor Cyan
$log = Join-Path $env:TEMP "insar_desktop_selftest.log"
Remove-Item -Force $log -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru -NoNewWindow
if ($proc.ExitCode -ne 0) {
    if (Test-Path $log) {
        Write-Host "--- selftest log ---" -ForegroundColor Red
        Get-Content $log | Write-Host
    }
    throw "Desktop exe self-test failed (exit code $($proc.ExitCode))"
}
Write-Host "Desktop exe self-test OK (core exercised end-to-end, exit 0)" -ForegroundColor Green
Remove-Item -Recurse -Force $boundaryStage -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "== DONE: dist\insar-prep-desktop.exe built and smoke-tested ==" -ForegroundColor Green
