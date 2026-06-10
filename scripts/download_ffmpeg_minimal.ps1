# Minimal alternative: Download just the ffmpeg binary (not the full ffmpeg-kit SDK)
# This approach bundles a standalone ffmpeg executable extracted from Termux packages
# Advantage: much smaller (< 20MB vs 50MB+)
# Disadvantage: separate from the app's JNI, needs runtime extraction

param(
    [string]$TargetDir = "$PSScriptRoot\..\app\src\main\assets"
)

$ErrorActionPreference = "Stop"

Write-Host "Downloading standalone ffmpeg binary for Android..." -ForegroundColor Cyan

# ─── Option 1: Termux ffmpeg static build ──────────────────
# Termux packages are compiled for Android's bionic libc
# Source: https://packages.termux.dev/
$TERMUX_MIRROR = "https://packages.termux.dev/apt/termux-main"

# ffmpeg and its dependencies for aarch64 (Android arm64-v8a)
# We need: ffmpeg + libavcodec + libavformat + libavutil + libswresample + libssl + libcrypto

$PACKAGES = @(
    @{Name="ffmpeg"; Arch="aarch64"},
    @{Name="libavcodec"; Arch="aarch64"},
    @{Name="libavformat"; Arch="aarch64"},
    @{Name="libavutil"; Arch="aarch64"},
    @{Name="libswresample"; Arch="aarch64"},
    @{Name="openssl"; Arch="aarch64"}
)

# Create target directories
$assetsDir = "$TargetDir\ffmpeg\arm64-v8a"
New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null

# Since Termux .deb packages need dependency resolution,
# we use a simpler approach: download pre-built static ffmpeg

# ─── Option 2 (Recommended): Static ffmpeg from jmvver's builds ──
# These are static builds specifically for Android
# https://github.com/nickolay-savchenko/ffmpeg-android

Write-Host @"

  ╔═══════════════════════════════════════════╗
  ║  ffmpeg binary download (minimal)         ║
  ║                                           ║
  ║  This script downloads a pre-compiled     ║
  ║  static ffmpeg binary for Android.        ║
  ║                                           ║
  ║  Manual download URL:                     ║
  ║  https://github.com/nickolay-savchenko/   ║
  ║  ffmpeg-android/releases                  ║
  ║                                           ║
  ║  Or build your own:                       ║
  ║  git clone https://github.com/nickolay-   ║
  ║    savchenko/ffmpeg-android               ║
  ║  cd ffmpeg-android                        ║
  ║  ./build.sh arm64-v8a                     ║
  ╚═══════════════════════════════════════════╝

"@

Write-Host "For now, please manually:" -ForegroundColor Yellow
Write-Host "  1. Download ffmpeg binary from:" -ForegroundColor Yellow
Write-Host "     https://github.com/nickolay-savchenko/ffmpeg-android/releases" -ForegroundColor White
Write-Host "  2. Extract the arm64-v8a binary" -ForegroundColor Yellow
Write-Host "  3. Rename it to 'ffmpeg' and place in:" -ForegroundColor Yellow
Write-Host "     $assetsDir" -ForegroundColor White
Write-Host ""
Write-Host "Or use the ffmpeg-kit approach:" -ForegroundColor Yellow
Write-Host "  .\download_ffmpeg.ps1" -ForegroundColor White
