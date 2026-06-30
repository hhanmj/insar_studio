<#
.SYNOPSIS
    Build the optional DEM/GDAL runtime component zip.

.DESCRIPTION
    Packages rasterio/GDAL, numpy, and the small Python dependencies required by
    the DEM ellipsoid/SARscape conversion path into an external component.  The
    desktop app can download and activate this component on demand instead of
    bundling GDAL inside the main exe.

.PARAMETER Version
    Component version. Defaults to the project version from pyproject.toml.

.PARAMETER OutputDir
    Directory for the zip, manifest and checksums. Defaults to dist\components.

.PARAMETER ReleaseBaseUrl
    Base URL used in components-manifest.json. Defaults to the matching GitHub
    Release tag URL.
#>

param(
    [string]$Version = "",
    [string]$OutputDir = "",
    [string]$ReleaseBaseUrl = ""
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

function Copy-ComponentPath {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required component source not found: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if (-not $Version) {
    $Version = (& $py -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "dist\components"
}
if (-not $ReleaseBaseUrl) {
    $ReleaseBaseUrl = "https://github.com/hhanmj/insar_studio/releases/download/v$Version"
}

$sitePackages = (& $py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
if (-not (Test-Path $sitePackages)) {
    throw "site-packages not found: $sitePackages"
}

$componentId = "dem-gdal"
$archiveName = "insar-dem-gdal-$Version-win64.zip"
$archivePath = Join-Path $OutputDir $archiveName
$stageRoot = Join-Path $RepoRoot "build\dem-gdal-component"
$stageSite = Join-Path $stageRoot "site-packages"

Write-Host "Repo root: $RepoRoot"
Write-Host "Python site-packages: $sitePackages"
Write-Host "Component version: $Version"

Invoke-Step "Clean component stage" {
    if (Test-Path $stageRoot) { Remove-Item -Recurse -Force $stageRoot }
    New-Item -ItemType Directory -Force -Path $stageSite | Out-Null
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    Remove-Item -Force $archivePath -ErrorAction SilentlyContinue
}

$packages = @(
    "affine",
    "affine-*.dist-info",
    "attrs",
    "attrs-*.dist-info",
    "certifi",
    "certifi-*.dist-info",
    "click",
    "click-*.dist-info",
    "click_plugins",
    "click_plugins-*.dist-info",
    "cligj",
    "cligj-*.dist-info",
    "numpy",
    "numpy-*.dist-info",
    "numpy.libs",
    "pyparsing",
    "pyparsing-*.dist-info",
    "rasterio",
    "rasterio-*.dist-info",
    "rasterio.libs"
)

Invoke-Step "Copy DEM/GDAL runtime files" {
    foreach ($pattern in $packages) {
        $matches = Get-ChildItem -Path $sitePackages -Filter $pattern -Force -ErrorAction SilentlyContinue
        if (-not $matches) {
            if ($pattern -like "*.dist-info") { continue }
            throw "Required package not found in site-packages: $pattern"
        }
        foreach ($item in $matches) {
            Copy-ComponentPath -Source $item.FullName -Destination $stageSite
        }
    }
}

Invoke-Step "Trim component cache/test files" {
    Get-ChildItem -Path $stageRoot -Recurse -Force -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $stageRoot -Recurse -Force -Include "*.pyc", "*.pyo" |
        Remove-Item -Force -ErrorAction SilentlyContinue
    foreach ($relative in @(
            "site-packages\rasterio\rio",
            "site-packages\numpy\tests",
            "site-packages\numpy\testing\tests")) {
        $target = Join-Path $stageRoot $relative
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    }
    $componentInfo = @{
        id = $componentId
        name = "DEM Advanced Conversion Component"
        version = $Version
        entry = "site-packages"
        description = "GDAL/rasterio/numpy runtime for DEM ellipsoid conversion and SARscape *_dem export."
        built_at = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    }
    Write-Utf8NoBom -Path (Join-Path $stageRoot "component.json") -Content ($componentInfo | ConvertTo-Json -Depth 4)
}

Invoke-Step "Archive DEM/GDAL component" {
    Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal -Force
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
$sizeMb = [math]::Round((Get-Item $archivePath).Length / 1MB, 1)
$componentUrl = "$ReleaseBaseUrl/$archiveName"
$manifestPath = Join-Path $OutputDir "components-manifest.json"
$checksumPath = Join-Path $OutputDir "SHA256SUMS-components.txt"

$manifestComponent = [ordered]@{
    id = $componentId
    name = "DEM Advanced Conversion Component"
    version = $Version
    size_mb = $sizeMb
    url = $componentUrl
    sha256 = $hash
    entry = "site-packages"
    description = "On-demand GDAL/rasterio/numpy runtime for local DEM ellipsoid conversion and SARscape DEM export."
}
$manifest = [ordered]@{
    version = 1
    components = @($manifestComponent)
}
Write-Utf8NoBom -Path $manifestPath -Content ($manifest | ConvertTo-Json -Depth 6)
$checksumLine = $hash + [char]32 + [char]32 + $archiveName
$checksumLine | Set-Content -Encoding ASCII $checksumPath

Write-Host ""
Write-Host "Built component: $archivePath ($sizeMb MB)" -ForegroundColor Green
Write-Host "Manifest: $manifestPath" -ForegroundColor Green
Write-Host "SHA256: $hash" -ForegroundColor Green
