<#
.SYNOPSIS
    Build a one-file Windows **GUI** executable for insar-prep with PyInstaller
    and smoke-test it off-screen (Task 053 GUI packaging).

.DESCRIPTION
    Builds dist\insar-prep-gui.exe -- a windowed (no-console) PySide6 app whose
    entry point opens the desktop GUI. The build bundles PySide6 (incl. the Qt
    platform plugins) and the optional `download` extra (requests + certifi CA
    bundle + keyring) so the frozen GUI is capable of the real ASF SLC download
    and the real OpenTopography DEM download, and of storing credentials in the
    OS keyring. The build itself stays offline and downloads no SAR/DEM data,
    builds no installer, and commits nothing (build/, dist/, *.spec are
    git-ignored).

    Unlike the CLI exe (scripts\build_windows_exe.ps1), this build INCLUDES
    PySide6 -- the resulting exe is much larger (~150-250 MB) and first launch is
    slower (one-file unpacks to a temp dir).

    The smoke test runs the frozen exe with `--selftest`, which constructs the
    QApplication + main window using the off-screen Qt platform and exits 0,
    proving the frozen build imports and builds the UI without a real display or
    any network access.

.NOTES
    Run from anywhere; the script resolves the repo root from its own location.
    Requires the `gui` and `download` extras to be installed in the active env
    (uv sync --extra gui --extra download).
#>

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

Invoke-Step "PyInstaller GUI build" {
    # Bundle PySide6 (incl. Qt platform plugins) + the download extra. The entry
    # opens the desktop GUI; --windowed means no console window for end users.
    & $py -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name insar-prep-gui `
        --paths src `
        --collect-all PySide6 `
        --collect-all shapely `
        --collect-submodules pydantic `
        --collect-all requests `
        --collect-all certifi `
        --collect-all keyring `
        --copy-metadata keyring `
        packaging/insar_prep_gui_entry.py
}

$exe = Join-Path $RepoRoot "dist\insar-prep-gui.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($sizeMb MB)" -ForegroundColor Green

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
