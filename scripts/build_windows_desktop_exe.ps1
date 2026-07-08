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
        keyring), and optionally the convert extra (rasterio/GDAL) + the bundled
        EGM96 geoid,
    so every panel (AOI / scenes / download plan / DEM convert / report) works in
    the frozen build. The build itself stays offline and downloads no SAR/DEM data.

    The smoke test runs the frozen exe with --selftest, which verifies the bundled
    web assets resolve and exercises the core end-to-end (workspace -> AOI ->
    scenes -> DEM plan/convert -> report) without a window or network, exiting 0.

.PARAMETER SkipUi
    Skip the `npm run build` step and reuse the existing ui\dist.

.PARAMETER ExternalDemComponent
    Build a lean desktop exe that excludes rasterio/GDAL. DEM ellipsoid
    conversion will then require the optional DEM/GDAL component.

.PARAMETER Egm2008GeoidNpz
    Optional EGM2008 geoid .npz file to bundle into the full desktop exe. This is
    used for release builds where DEM/GDAL is bundled instead of externalized.

.PARAMETER SkipSelfTest
    Skip launching the frozen exe with --selftest. Useful on local machines where
    Windows Application Control blocks freshly built test executables.

.PARAMETER BoundaryDir
    Optional local administrative boundary directory to bundle. It may contain
    either 中国_省/市/县.geojson or normalized china_province/city/county.geojson.

.NOTES
    Run from anywhere; resolves the repo root from its own location. Requires the
    `desktop`, `download`, and `convert` extras installed in the active env
    (uv sync --extra desktop --extra download --extra convert) plus Node/npm for
    the UI build.
#>

param(
    [switch]$SkipUi,
    [switch]$ExternalDemComponent,
    [switch]$SkipSelfTest,
    [string]$Egm2008GeoidNpz = "",
    [string]$BoundaryDir = ""
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

function Invoke-LocalCodeSign {
    param([Parameter(Mandatory = $true)][string]$Path)

    $subject = "CN=InSAR Assistant Local Test"
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -eq $subject } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate `
            -Type CodeSigningCert `
            -Subject $subject `
            -CertStoreLocation Cert:\CurrentUser\My `
            -KeyExportPolicy NonExportable `
            -KeyUsage DigitalSignature `
            -NotAfter (Get-Date).AddYears(3)
    }

    $tmpCert = Join-Path $env:TEMP "insar-assistant-local-test.cer"
    Export-Certificate -Cert $cert -FilePath $tmpCert -Force | Out-Null
    Import-Certificate -FilePath $tmpCert -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    Import-Certificate -FilePath $tmpCert -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
    $signed = Set-AuthenticodeSignature -FilePath $Path -Certificate $cert -HashAlgorithm SHA256
    if ($signed.Status -ne "Valid") {
        $verified = Get-AuthenticodeSignature -LiteralPath $Path
        if ($verified.Status -ne "Valid") {
            throw "Local code signing failed: $($verified.StatusMessage)"
        }
    }
    Write-Host "Local test code signature applied: $Path" -ForegroundColor Yellow
}

function Start-DesktopSelfTestProcess {
    param([Parameter(Mandatory = $true)][string]$Path)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Path
    $psi.Arguments = "--selftest"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.WaitForExit()
    return $proc
}

function Invoke-DesktopSelfTest {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        return Start-DesktopSelfTestProcess -Path $Path
    } catch {
        $message = $_.Exception.Message
        if ($message -notmatch "Application Control policy") {
            throw
        }
        Write-Host "Windows blocked the freshly built unsigned exe; applying local test signature..." -ForegroundColor Yellow
        Invoke-LocalCodeSign -Path $Path
        return Start-DesktopSelfTestProcess -Path $Path
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "Repo root: $RepoRoot"
if ($ExternalDemComponent) {
    Write-Host "DEM/GDAL will be externalized into the optional component." -ForegroundColor Yellow
}

# 1. Build the web frontend (ui\dist) unless explicitly skipped.
$uiDist = Join-Path $RepoRoot "ui\dist\index.html"
if (-not $SkipUi) {
    Invoke-Step "Build web UI (vite)" {
        Push-Location (Join-Path $RepoRoot "ui")
        try { & npm run build } finally { Pop-Location }
    }
}
if (-not (Test-Path $uiDist)) { throw "ui\dist not found ($uiDist); run without -SkipUi" }

$stagedEgm2008GeoidNpz = ""
if (-not [string]::IsNullOrWhiteSpace($Egm2008GeoidNpz)) {
    if (-not (Test-Path -LiteralPath $Egm2008GeoidNpz)) {
        throw "EGM2008 geoid grid not found: $Egm2008GeoidNpz"
    }
    $egm2008Source = (Resolve-Path -LiteralPath $Egm2008GeoidNpz).Path
    $stagedEgm2008GeoidNpz = Join-Path $env:TEMP ("insar-egm2008-" + [guid]::NewGuid().ToString("N") + ".npz")
    Copy-Item -LiteralPath $egm2008Source -Destination $stagedEgm2008GeoidNpz -Force
    $Egm2008GeoidNpz = $stagedEgm2008GeoidNpz
}

$boundaryDirName = "$([char]0x8FB9)$([char]0x754C)"
$chinaName = "$([char]0x4E2D)$([char]0x56FD)"
$provinceName = "$([char]0x7701)"
$cityName = "$([char]0x5E02)"
$countyName = "$([char]0x53BF)"
$boundaryCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($BoundaryDir)) {
    $boundaryCandidates += $BoundaryDir
}
$boundaryCandidates += @(
    (Join-Path $RepoRoot $boundaryDirName),
    (Join-Path (Split-Path $RepoRoot -Parent) $boundaryDirName),
    (Join-Path $RepoRoot "src\insar_prep\desktop\boundaries")
)
$boundarySource = $null
foreach ($candidateRaw in $boundaryCandidates) {
    if ([string]::IsNullOrWhiteSpace([string]$candidateRaw)) { continue }
    try {
        $candidate = (Resolve-Path -LiteralPath $candidateRaw -ErrorAction Stop).Path
    } catch {
        $candidate = [string]$candidateRaw
    }
    if (Test-Path -LiteralPath $candidate -PathType Container) {
        $boundarySource = $candidate
        break
    }
}
$boundaryStage = Join-Path $RepoRoot ".build_boundaries"
if ($boundarySource) {
    Write-Host "Using local boundary directory: $boundarySource" -ForegroundColor Green
} else {
    Write-Host "Local boundary directory not found; building without bundled offline administrative boundaries." -ForegroundColor Yellow
    Write-Host "Tried: $($boundaryCandidates -join '; ')" -ForegroundColor DarkYellow
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
    @{ Sources = @("$chinaName`_$provinceName.geojson", "china_province.geojson"); Target = "china_province.geojson" },
    @{ Sources = @("$chinaName`_$cityName.geojson", "china_city.geojson"); Target = "china_city.geojson" },
    @{ Sources = @("$chinaName`_$countyName.geojson", "china_county.geojson"); Target = "china_county.geojson" }
)
$copiedBoundaryCount = 0
if ($boundarySource -and (Test-Path -LiteralPath $boundarySource)) {
    foreach ($item in $boundaryCopies) {
        $src = $null
        foreach ($sourceName in $item.Sources) {
            $candidate = Join-Path $boundarySource $sourceName
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $src = $candidate
                break
            }
        }
        $dst = Join-Path $boundaryStage $item.Target
        if (-not $src) {
            Write-Host "Boundary file not found; skipping target $($item.Target). Expected one of: $($item.Sources -join ', ')" -ForegroundColor Yellow
            continue
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copiedBoundaryCount += 1
    }
}
if ($copiedBoundaryCount -eq 0) {
    Write-Host "No offline administrative boundary files were bundled. The app can still run; boundary data may be supplied by cache or future online sources." -ForegroundColor Yellow
}

# Call PyInstaller through the requested interpreter, then the venv interpreter.
$py = ""
if (-not [string]::IsNullOrWhiteSpace($env:INSAR_BUILD_PYTHON)) {
    $py = $env:INSAR_BUILD_PYTHON
}
if (-not $py -or -not (Test-Path -LiteralPath $py)) {
    $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
$extraPyInstallerArgs = @()

if (Test-Path -LiteralPath $py) {
    $pythonRoot = Split-Path -Parent (Resolve-Path -LiteralPath $py).Path
    $condaLibraryBin = Join-Path $pythonRoot "Library\bin"
    $pythonDlls = Join-Path $pythonRoot "DLLs"
    $pathPrefix = @($condaLibraryBin, $pythonDlls, $pythonRoot) |
        Where-Object { Test-Path -LiteralPath $_ }
    if ($pathPrefix.Count -gt 0) {
        $env:PATH = "$($pathPrefix -join ';');$env:PATH"
    }
    if (Test-Path -LiteralPath $condaLibraryBin) {
        $condaDlls = @(
            "libssl-3-x64.dll",
            "libcrypto-3-x64.dll",
            "libbz2.dll",
            "liblzma.dll",
            "ffi-8.dll",
            "libexpat.dll",
            "sqlite3.dll",
            "yaml.dll"
        )
        if (-not $ExternalDemComponent) {
            $condaDlls += @(
                "archive.dll",
                "blosc.dll",
                "charset.dll",
                "deflate.dll",
                "freexl.dll",
                "gdal.dll",
                "geos.dll",
                "geos_c.dll",
                "geotiff.dll",
                "iconv.dll",
                "jpeg8.dll",
                "Lerc.dll",
                "libcurl.dll",
                "liblz4.dll",
                "libminizip.dll",
                "libpng16.dll",
                "libsharpyuv.dll",
                "libssh2.dll",
                "libwebp.dll",
                "libxml2.dll",
                "MSVCP140.dll",
                "openjp2.dll",
                "pcre2-8.dll",
                "proj_9.dll",
                "snappy.dll",
                "spatialite.dll",
                "tiff.dll",
                "ucrtbase.dll",
                "VCRUNTIME140.dll",
                "VCRUNTIME140_1.dll",
                "xerces-c_3_2.dll",
                "zlib.dll",
                "zstd.dll",
                "lcms2.dll",
                "libwebpdemux.dll",
                "libwebpmux.dll"
            )
        }
        foreach ($dllName in $condaDlls | Sort-Object -Unique) {
            $dllPath = Join-Path $condaLibraryBin $dllName
            if (Test-Path -LiteralPath $dllPath) {
                $extraPyInstallerArgs += @("--add-binary", "$dllPath;.")
            }
        }
        if (-not $ExternalDemComponent) {
            $gdalData = Join-Path $pythonRoot "Library\share\gdal"
            $projData = Join-Path $pythonRoot "Library\share\proj"
            if (Test-Path -LiteralPath $gdalData) {
                $env:GDAL_DATA = $gdalData
                $extraPyInstallerArgs += @("--add-data", "$gdalData;gdal_data")
            }
            if (Test-Path -LiteralPath $projData) {
                $env:PROJ_LIB = $projData
                $env:PROJ_DATA = $projData
                $extraPyInstallerArgs += @("--add-data", "$projData;proj_data")
            }
        }
    }
}

$pyArgs = @(
    "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "insar-prep-desktop",
    "--icon", "packaging/app_icon.ico",
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
    "--collect-all", "asf_search",
    "--hidden-import", "socks",
    "--collect-all", "certifi",
    "--collect-all", "keyring",
    "--collect-data", "insar_prep",
    "--copy-metadata", "keyring",
    "--copy-metadata", "asf-search",
    # Keep the release app lean: these are pulled in by package hooks/tests but
    # are not used by the desktop runtime.
    "--exclude-module", "pytest",
    "--exclude-module", "py",
    "--exclude-module", "pygments",
    "--exclude-module", "IPython",
    "--exclude-module", "matplotlib",
    "--exclude-module", "pandas",
    "--exclude-module", "scipy",
    "--exclude-module", "dask",
    "--exclude-module", "pyarrow",
    "--exclude-module", "xarray",
    "--exclude-module", "zarr",
    "--exclude-module", "h5py",
    "--exclude-module", "openpyxl",
    "--exclude-module", "numexpr",
    "--exclude-module", "shapely.tests",
    "packaging/insar_prep_desktop_entry.py"
)

if ($extraPyInstallerArgs.Count -gt 0) {
    $entry = $pyArgs[-1]
    $pyArgs = $pyArgs[0..($pyArgs.Length - 2)] + $extraPyInstallerArgs + @($entry)
}

if ($ExternalDemComponent) {
    $entry = $pyArgs[-1]
    $pyArgs = $pyArgs[0..($pyArgs.Length - 2)] + @(
        "--exclude-module", "rasterio",
        "--exclude-module", "rasterio.rio"
    ) + @($entry)
} else {
    $entry = $pyArgs[-1]
    $pyArgs = $pyArgs[0..($pyArgs.Length - 2)] + @(
        "--collect-all", "rasterio",
        "--collect-all", "pyproj",
        "--exclude-module", "rasterio.rio"
    ) + @($entry)
    if (-not [string]::IsNullOrWhiteSpace($Egm2008GeoidNpz)) {
        if (-not (Test-Path -LiteralPath $Egm2008GeoidNpz)) {
            throw "EGM2008 geoid grid not found: $Egm2008GeoidNpz"
        }
        $egm2008Resolved = (Resolve-Path -LiteralPath $Egm2008GeoidNpz).Path
        $entry = $pyArgs[-1]
        $pyArgs = $pyArgs[0..($pyArgs.Length - 2)] + @(
            "--add-data", "$egm2008Resolved;insar_prep/data"
        ) + @($entry)
        Write-Host "Bundling EGM2008 geoid grid into the full desktop exe: $egm2008Resolved" -ForegroundColor Green
    }
}

Invoke-Step "PyInstaller desktop build" {
    & $py @pyArgs
}

$exe = Join-Path $RepoRoot "dist\insar-prep-desktop.exe"
if (-not (Test-Path $exe)) { throw "Expected exe not found: $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($sizeMb MB)" -ForegroundColor Green

if ($SkipSelfTest) {
    Write-Host ""
    Write-Host "== Desktop exe off-screen self-test skipped ==" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "== Desktop exe off-screen self-test ==" -ForegroundColor Cyan
    $log = Join-Path $env:TEMP "insar_desktop_selftest.log"
    Remove-Item -Force $log -ErrorAction SilentlyContinue
    $previousSkipRasterioSelftest = $env:INSAR_SELFTEST_SKIP_RASTERIO
    if ($ExternalDemComponent) {
        $env:INSAR_SELFTEST_SKIP_RASTERIO = "1"
    }
    try {
        $proc = Invoke-DesktopSelfTest -Path $exe
    } finally {
        if ($null -eq $previousSkipRasterioSelftest) {
            Remove-Item Env:\INSAR_SELFTEST_SKIP_RASTERIO -ErrorAction SilentlyContinue
        } else {
            $env:INSAR_SELFTEST_SKIP_RASTERIO = $previousSkipRasterioSelftest
        }
    }
    if ($proc.ExitCode -ne 0) {
        if (Test-Path $log) {
            Write-Host "--- selftest log ---" -ForegroundColor Red
            Get-Content $log | Write-Host
        }
        throw "Desktop exe self-test failed (exit code $($proc.ExitCode))"
    }
    Write-Host "Desktop exe self-test OK (core exercised end-to-end, exit 0)" -ForegroundColor Green
}
Remove-Item -Recurse -Force $boundaryStage -ErrorAction SilentlyContinue
if ($stagedEgm2008GeoidNpz) {
    Remove-Item -Force $stagedEgm2008GeoidNpz -ErrorAction SilentlyContinue
}

Write-Host ""
if ($SkipSelfTest) {
    Write-Host "== DONE: dist\insar-prep-desktop.exe built (self-test skipped) ==" -ForegroundColor Green
} else {
    Write-Host "== DONE: dist\insar-prep-desktop.exe built and smoke-tested ==" -ForegroundColor Green
}
