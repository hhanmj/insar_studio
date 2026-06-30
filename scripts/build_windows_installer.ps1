<#
.SYNOPSIS
    Compile the Windows installer for the insar-prep GUI with Inno Setup
    (Task 053 release packaging).

.DESCRIPTION
    Locates the Inno Setup compiler (iscc.exe), then compiles
    packaging\insar_prep_gui_installer.iss into
    dist\insar-prep-gui-<version>-setup.exe. The one-file GUI exe
    (dist\insar-prep-gui.exe) must already be built -- run
    scripts\build_windows_gui_exe.ps1 first.

    Inno Setup is NOT a Python dependency; install it once from
    https://jrsoftware.org/isdl.php (or `winget install JRSoftware.InnoSetup`).
    The compiled installer is git-ignored.

.PARAMETER Version
    Version string embedded in the installer (default: 2.1).

.NOTES
    Run from anywhere; the script resolves the repo root from its own location.
#>
param(
    [string]$Version = "2.1"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$guiExe = Join-Path $RepoRoot "dist\insar-prep-gui.exe"
if (-not (Test-Path $guiExe)) {
    throw "GUI exe not found: $guiExe`nBuild it first: scripts\build_windows_gui_exe.ps1"
}

# Find iscc.exe: PATH first, then the standard Inno Setup 6 install locations.
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($candidate in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if (-not $iscc) {
    throw "Inno Setup compiler (iscc.exe) not found. Install Inno Setup 6 from " +
        "https://jrsoftware.org/isdl.php (or 'winget install JRSoftware.InnoSetup') and retry."
}

Write-Host "Using Inno Setup compiler: $iscc" -ForegroundColor Cyan
$iss = Join-Path $RepoRoot "packaging\insar_prep_gui_installer.iss"
& $iscc "/DAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed (exit code $LASTEXITCODE)"
}

$setup = Join-Path $RepoRoot "dist\insar-prep-gui-$Version-setup.exe"
if (-not (Test-Path $setup)) { throw "Expected installer not found: $setup" }
$sizeMb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host "Built installer: $setup ($sizeMb MB)" -ForegroundColor Green
