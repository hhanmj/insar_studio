<#
.SYNOPSIS
    Build the InSAR Studio desktop Windows installer with Inno Setup.

.DESCRIPTION
    Wraps dist\insar-prep-desktop.exe into a per-user installer with Start Menu
    entry, optional desktop shortcut, uninstall entry, and the app icon.

.PARAMETER Version
    Version string embedded in the installer.
#>
param(
    [string]$Version = "2.0.0"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$desktopExe = Join-Path $RepoRoot "dist\insar-prep-desktop.exe"
if (-not (Test-Path $desktopExe)) {
    throw "Desktop exe not found: $desktopExe`nBuild it first: scripts\build_windows_desktop_exe.ps1"
}

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($candidate in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if (-not $iscc) {
    throw "Inno Setup compiler (iscc.exe) not found. Install Inno Setup 6, then retry this script."
}

Write-Host "Using Inno Setup compiler: $iscc" -ForegroundColor Cyan
$iss = Join-Path $RepoRoot "packaging\insar_studio_desktop_installer.iss"
& $iscc "/DAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed (exit code $LASTEXITCODE)"
}

$setup = Join-Path $RepoRoot "dist\insar-studio-$Version-setup.exe"
if (-not (Test-Path $setup)) { throw "Expected installer not found: $setup" }
$sizeMb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host "Built installer: $setup ($sizeMb MB)" -ForegroundColor Green
