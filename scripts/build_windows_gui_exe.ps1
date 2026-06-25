<#
.SYNOPSIS
    Build a one-file Windows **GUI** executable for insar-prep with PyInstaller
    and smoke-test it off-screen (Task 053 GUI packaging).

.DESCRIPTION
    Builds dist\insar-prep-gui.exe -- a windowed (no-console) PySide6 app whose
    entry point opens the desktop GUI.     The build bundles PySide6 (incl. the Qt
    platform plugins), the optional `download` extra (requests + certifi CA
    bundle + keyring), and the optional `convert` extra (rasterio + GDAL) plus the
    bundled EGM96 geoid grid, so the frozen GUI is capable of the real ASF SLC
    download, the real OpenTopography DEM download, the real DEM vertical-datum
    conversion, and of storing credentials in the OS keyring. The build itself
    stays offline and downloads no SAR/DEM data, builds no installer, and commits
    nothing (build/, dist/, *.spec are git-ignored).

    Unlike the CLI exe (scripts\build_windows_exe.ps1), this build INCLUDES
    PySide6, so the exe is larger and first launch is slower (one-file unpacks to
    a temp dir). Size depends on the -WithMap switch:
      * default (slim)   ~80-130 MB -- no QtWebEngine; the interactive map AOI
                         picker is disabled (it degrades gracefully) but manual
                         W/S/E/N entry and all file-based AOI sources still work.
      * -WithMap         ~250-300 MB -- bundles the Qt WebEngine / Chromium
                         runtime so the embedded Leaflet map picker works.

    The smoke test runs the frozen exe with `--selftest`, which constructs the
    QApplication + main window using the off-screen Qt platform and exits 0,
    proving the frozen build imports and builds the UI without a real display or
    any network access.

.PARAMETER WithMap
    Bundle the interactive map AOI picker (Leaflet in QtWebEngine). This pulls in
    the Qt WebEngine / Chromium runtime (~120-160 MB) and roughly triples the exe
    size, so it is OFF by default. Without it the slim build omits WebEngine and
    the GUI degrades gracefully (the "Pick on map" button is disabled).

.NOTES
    Run from anywhere; the script resolves the repo root from its own location.
    Requires the `gui`, `download`, and `convert` extras to be installed in the
    active env (uv sync --extra gui --extra download --extra convert).
#>

param(
    [switch]$WithMap
)

$ErrorActionPreference = "Stop"

function Invoke-Native {
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

Write-Host ""
Write-Host "== Clean previous GUI build artifacts ==" -ForegroundColor Cyan
foreach ($dir in @("build", "dist")) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
Get-ChildItem -Path $RepoRoot -Filter "insar-prep-gui.spec" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force

# Call PyInstaller through the venv interpreter directly (not `uv run`, which
# re-syncs the project and can fail if Scripts\insar-prep.exe is momentarily
# locked by another process / antivirus on Windows).
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# Assemble the PyInstaller arguments. The biggest size lever is how much of Qt we
# bundle:
#   * slim (default): do NOT --collect-all PySide6. PyInstaller's per-module
#     PySide6 hooks then bundle only the Qt modules actually imported at module
#     scope (QtCore / QtGui / QtWidgets). The map picker imports QtWebEngine
#     lazily (via importlib), so static analysis never sees it; we additionally
#     hard-exclude the WebEngine / QML / and other heavy optional stacks so
#     nothing drags the Chromium runtime (~120-160 MB) back in.
#   * -WithMap: --collect-all PySide6 to guarantee QtWebEngine plus its QML /
#     Quick / Positioning dependencies are present so the Leaflet map picker runs.
$pyArgs = @(
    "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "insar-prep-gui",
    "--paths", "src"
)

if ($WithMap) {
    Write-Host "Map mode: ON  -- bundling QtWebEngine (large exe)" -ForegroundColor Yellow
    $pyArgs += @("--collect-all", "PySide6")
}
else {
    Write-Host "Map mode: OFF -- slim build, interactive map disabled" -ForegroundColor Yellow
    # No --collect-all PySide6: the hooks pull only imported Qt modules. Then
    # hard-exclude the heavy optional stacks so none get dragged back in.
    $excludeQt = @(
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQml",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtDesigner",
        "PySide6.QtUiTools",
        "PySide6.QtTest",
        "PySide6.QtSql",
        "PySide6.QtNetworkAuth",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtScxml",
        "PySide6.QtTextToSpeech"
    )
    foreach ($mod in $excludeQt) { $pyArgs += @("--exclude-module", $mod) }
}

# Common collections shared by both modes: the download extra (requests / certifi
# / keyring), the convert extra (rasterio + GDAL data/drivers, needed for the real
# DEM vertical-datum conversion), shapely, pydantic submodules, the package data,
# and the keyring metadata.
$pyArgs += @(
    "--collect-all", "shapely",
    "--collect-submodules", "pydantic",
    "--collect-all", "requests",
    "--collect-all", "certifi",
    "--collect-all", "keyring",
    "--collect-all", "rasterio",
    "--collect-data", "insar_prep",
    "--copy-metadata", "keyring",
    "packaging/insar_prep_gui_entry.py"
)

Invoke-Step "PyInstaller GUI build" {
    & $py @pyArgs
}

$exe = Join-Path $RepoRoot "dist\insar-prep-gui.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$mapMode = if ($WithMap) { "with interactive map (QtWebEngine)" } else { "slim, no interactive map" }
Write-Host "Built: $exe ($sizeMb MB) -- $mapMode" -ForegroundColor Green

Write-Host ""
Write-Host "== GUI exe off-screen self-test ==" -ForegroundColor Cyan
# A windowed (GUI-subsystem) exe is launched with Start-Process -Wait so the
# shell waits for it and we can read the exit code. --selftest builds the app +
# main window off-screen and exits 0 (no real window, no event loop, no network).
$env:QT_QPA_PLATFORM = "offscreen"
$proc = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru -NoNewWindow
if ($proc.ExitCode -ne 0) {
    throw "GUI exe self-test failed (exit code $($proc.ExitCode))"
}
Write-Host "GUI exe self-test OK (off-screen app + main window built, exit 0)" -ForegroundColor Green

Write-Host ""
Write-Host "== DONE: dist\insar-prep-gui.exe built and smoke-tested ==" -ForegroundColor Green
