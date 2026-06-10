<#
.SYNOPSIS
  Download ffmpeg binary from Termux package repository
  and extract it for bundling in the Android APK.

.DESCRIPTION
  Termux packages are actively maintained and compiled for Android's
  bionic libc on aarch64. This script:
  1. Fetches the Termux package index
  2. Downloads the ffmpeg .deb for aarch64
  3. Extracts the ffmpeg binary and all required .so dependencies
  4. Places them in assets/ for APK bundling

  At runtime, FFmpegHelper.kt extracts the binary + libs to the
  app's internal storage and sets up LD_LIBRARY_PATH.

.OUTPUT
  assets/ffmpeg/arm64-v8a/
    ├── ffmpeg          (executable)
    └── lib/            (shared libraries)
        ├── libavcodec.so
        ├── libavformat.so
        ...
#>

param(
    [string]$TargetDir = "$PSScriptRoot\..\app\src\main\assets\ffmpeg"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$abi = "arm64-v8a"
$arch = "aarch64"   # Termux name for arm64
$assetsDir = "$TargetDir\$abi"

# Termux package repository
$TERMUX_REPO = "https://packages.termux.dev/apt/termux-main"
$PACKAGES_URL = "$TERMUX_REPO/dists/stable/main/binary-$arch/Packages"

$tempDir = "$env:TEMP\biliup-ffmpeg-deb"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
New-Item -ItemType Directory -Force -Path "$assetsDir\lib" | Out-Null

Write-Host @"

  ╔═══════════════════════════════════════════╗
  ║  biliup-android: ffmpeg from Termux       ║
  ║  Source: packages.termux.dev               ║
  ╚═══════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# ─── Step 1: Fetch package index ────────────────────────────

Write-Host "[1/4] Fetching Termux package index..." -ForegroundColor Cyan

$packagesFile = "$tempDir\Packages"
try {
    Invoke-WebRequest -Uri $PACKAGES_URL -OutFile $packagesFile -TimeoutSec 30
} catch {
    Write-Host "  ERROR: Cannot fetch package index: $_" -ForegroundColor Red
    Write-Host "  Please copy ffmpeg from your phone's Termux instead:" -ForegroundColor Yellow
    Write-Host "    In Termux: cp `$(which ffmpeg) /sdcard/ffmpeg" -ForegroundColor White
    Write-Host "    Then copy to: $assetsDir\ffmpeg" -ForegroundColor White
    exit 1
}

# Parse the Packages file (Debian control format)
$packages = Get-Content $packagesFile -Raw
$entries = $packages -split "(?=\nPackage:)" | Where-Object { $_.Trim() -ne "" }

function Get-Field($entry, $field) {
    if ($entry -match "$field:\s*(.+)" ) {
        return $Matches[1].Trim()
    }
    return $null
}

# Find ffmpeg entry
$ffmpegEntry = $entries | Where-Object { (Get-Field $_ "Package") -eq "ffmpeg" } | Select-Object -First 1
if (-not $ffmpegEntry) {
    Write-Host "  ERROR: ffmpeg not found in Termux repo" -ForegroundColor Red
    exit 1
}

$ffmpegVersion = Get-Field $ffmpegEntry "Version"
$ffmpegFilename = Get-Field $ffmpegEntry "Filename"
$ffmpegDepends = Get-Field $ffmpegEntry "Depends"

Write-Host "  ffmpeg version: $ffmpegVersion" -ForegroundColor Green

# ─── Step 2: Collect .so dependencies ───────────────────────

# Dependencies we need (ffmpeg's shared libraries)
# These are libav*.so which ffmpeg links to
$SO_PACKAGES = @(
    "libavcodec",
    "libavformat",
    "libavutil",
    "libswresample",
    "libswscale",
    "libavfilter",
    "libavdevice",
    "libpostproc"
)

$allDebUrls = @()
$allDebUrls += "$TERMUX_REPO/$ffmpegFilename"

# Parse Depends field to find dependent packages
if ($ffmpegDepends) {
    $deps = $ffmpegDepends -split "," | ForEach-Object { ($_ -split "\|")[0].Trim() -replace "\s*\(.*\)", "" }
    foreach ($dep in $deps) {
        if ($dep -in $SO_PACKAGES) {
            $depEntry = $entries | Where-Object { (Get-Field $_ "Package") -eq $dep } | Select-Object -First 1
            if ($depEntry) {
                $depFile = Get-Field $depEntry "Filename"
                if ($depFile) {
                    $allDebUrls += "$TERMUX_REPO/$depFile"
                }
            }
        }
    }
}

Write-Host "  Found $($allDebUrls.Count) packages to download" -ForegroundColor Green

# ─── Step 3: Download .deb files ────────────────────────────

Write-Host "[2/4] Downloading packages..." -ForegroundColor Cyan

$debFiles = @()
foreach ($url in $allDebUrls) {
    $filename = Split-Path $url -Leaf
    $outFile = "$tempDir\$filename"

    if (-not (Test-Path $outFile)) {
        $pkgName = $filename -replace "_.*", ""
        Write-Host "  Downloading $pkgName..." -ForegroundColor Gray
        try {
            Invoke-WebRequest -Uri $url -OutFile $outFile -TimeoutSec 60
            $size = [math]::Round((Get-Item $outFile).Length / 1KB, 1)
            Write-Host "    $pkgName: ${size}KB" -ForegroundColor DarkGray
        } catch {
            Write-Host "    WARN: failed to download $filename" -ForegroundColor Yellow
            continue
        }
    }
    $debFiles += $outFile
}

# ─── Step 4: Extract binary + .so files ─────────────────────

Write-Host "[3/4] Extracting..." -ForegroundColor Cyan

# Use 7zip if available, otherwise try .NET extraction
$use7z = Get-Command 7z -ErrorAction SilentlyContinue

foreach ($deb in $debFiles) {
    $pkgName = (Split-Path $deb -Leaf) -replace "_.*", ""
    $extractDir = "$tempDir\extract\$pkgName"
    Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

    try {
        if ($use7z) {
            # .deb is ar archive → contains data.tar.xz
            & 7z x $deb -o"$extractDir" -y | Out-Null
            $dataTar = Get-ChildItem "$extractDir" -Filter "data.tar*" | Select-Object -First 1
            if ($dataTar) {
                & 7z x $dataTar.FullName -o"$extractDir\data" -y | Out-Null
            }
        } else {
            # Fallback: use .NET ZipFile won't work for .deb
            # Try expanding the .deb as a raw archive
            # .deb format: !<arch> header + ar archive
            # Simpler: just try extracting with Expand-Archive for .tar.xz part
            $null = New-Item -ItemType Directory -Force -Path "$extractDir\data"
            # Extract using a simple approach for ar format
            $bytes = [System.IO.File]::ReadAllBytes($deb)
            $text = [System.Text.Encoding]::ASCII.GetString($bytes)

            # Find data.tar.xz in the ar archive
            $dataIdx = $text.IndexOf("data.tar.xz")
            if ($dataIdx -gt 0) {
                # This is fragile, just warn the user
                Write-Host "    WARN: 7z not found, cannot extract .deb. Install 7-Zip." -ForegroundColor Yellow
                continue
            }
        }
    } catch {
        Write-Host "    WARN: extraction failed for $pkgName" -ForegroundColor Yellow
        continue
    }

    # Copy binary / .so to assets
    $dataDir = "$extractDir\data"
    if (-not (Test-Path $dataDir)) { continue }

    # Find ffmpeg binary
    $bin = Get-ChildItem "$dataDir" -Recurse -Filter "ffmpeg" -File | Where-Object {
        $_.FullName -match "bin"
    } | Select-Object -First 1
    if ($bin) {
        Copy-Item $bin.FullName "$assetsDir\ffmpeg" -Force
        Write-Host "  ✓ ffmpeg binary" -ForegroundColor Green
    }

    # Find .so files
    $soFiles = Get-ChildItem "$dataDir" -Recurse -Filter "*.so*" -File
    foreach ($so in $soFiles) {
        $name = $so.Name -replace "\.\d+$", ""  # strip version suffix
        Copy-Item $so.FullName "$assetsDir\lib\$name" -Force
        Write-Host "  ✓ $name" -ForegroundColor DarkGreen
    }
}

# ─── Verify ────────────────────────────────────────────────

Write-Host "[4/4] Verifying..." -ForegroundColor Cyan

$ffmpegBin = "$assetsDir\ffmpeg"
$libCount = (Get-ChildItem "$assetsDir\lib" -Filter "*.so*" -ErrorAction SilentlyContinue).Count

if (Test-Path $ffmpegBin) {
    $sizeMB = [math]::Round((Get-Item $ffmpegBin).Length / 1MB, 1)
    Write-Host "  ✓ ffmpeg: ${sizeMB}MB" -ForegroundColor Green
} else {
    Write-Host "  ✗ ffmpeg binary missing!" -ForegroundColor Red
}

Write-Host "  Libraries: $libCount .so files" -ForegroundColor $(if ($libCount -gt 0) { "Green" } else { "Yellow" })

if ($libCount -eq 0) {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "  ║  .deb extraction may need 7-Zip installed.  ║" -ForegroundColor Yellow
    Write-Host "  ║                                              ║" -ForegroundColor Yellow
    Write-Host "  ║  EASIEST METHOD (2 min):                     ║" -ForegroundColor Yellow
    Write-Host "  ║  1. On your phone, open Termux               ║" -ForegroundColor Yellow
    Write-Host "  ║  2. Run: pkg install ffmpeg                  ║" -ForegroundColor Yellow
    Write-Host "  ║  3. Run: cp `$(which ffmpeg) /sdcard/ffmpeg  ║" -ForegroundColor Yellow
    Write-Host "  ║  4. Copy /sdcard/ffmpeg to:                  ║" -ForegroundColor Yellow
    Write-Host "  ║     $assetsDir\ffmpeg                        ║" -ForegroundColor Yellow
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Yellow
}

# ─── Cleanup ───────────────────────────────────────────────

Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "  Done! Next: Build APK in Android Studio" -ForegroundColor Cyan
Write-Host "  ffmpeg will be auto-bundled from assets/" -ForegroundColor Cyan
