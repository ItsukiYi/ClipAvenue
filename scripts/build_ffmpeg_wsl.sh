#!/bin/bash
# ────────────────────────────────────────────────────────────
# Build static ffmpeg for Android in WSL2
#
# Usage (in WSL2 Ubuntu):
#   chmod +x build_ffmpeg_wsl.sh
#   ./build_ffmpeg_wsl.sh
#
# Output: ./build/arm64-v8a/ffmpeg  (~15-25MB static binary)
# Copy to: app/src/main/assets/ffmpeg/arm64-v8a/ffmpeg
#
# References:
#   https://github.com/nickolay-savchenko/ffmpeg-android
#   https://trac.ffmpeg.org/wiki/CompilationGuide/Android
# ────────────────────────────────────────────────────────────

set -e

# ─── Config ────────────────────────────────────────────────

API=24                           # Android 7.0 minimum
ARCH="arm64-v8a"
TRIPLET="aarch64-linux-android"
CPU="armv8-a"
OPTIMIZE_CFLAGS="-march=$CPU"

# Paths (adjust if needed)
NDK="${ANDROID_NDK_HOME:-$HOME/Android/Sdk/ndk/27.0.12077973}"
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64"
SYSROOT="$TOOLCHAIN/sysroot"
CC="$TOOLCHAIN/bin/${TRIPLET}${API}-clang"
CXX="$TOOLCHAIN/bin/${TRIPLET}${API}-clang++"
AR="$TOOLCHAIN/bin/llvm-ar"
RANLIB="$TOOLCHAIN/bin/llvm-ranlib"
STRIP="$TOOLCHAIN/bin/llvm-strip"

BUILD_DIR="$(pwd)/build/$ARCH"
OUT_DIR="$(pwd)/build/$ARCH/out"
FFMPEG_VERSION="${FFMPEG_VERSION:-7.0.2}"
FFMPEG_SRC="ffmpeg-$FFMPEG_VERSION"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════╗"
echo "║  Build static ffmpeg for Android ($ARCH)  ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Check NDK ─────────────────────────────────────────────

if [ ! -d "$TOOLCHAIN" ]; then
    echo -e "${RED}Error: Android NDK not found at $NDK${NC}"
    echo "Install via Android Studio SDK Manager, or:"
    echo "  export ANDROID_NDK_HOME=/path/to/ndk"
    exit 1
fi
echo -e "${GREEN}✓ NDK found: $NDK${NC}"

# ─── Download ffmpeg ───────────────────────────────────────

if [ ! -d "$FFMPEG_SRC" ]; then
    echo -e "${CYAN}Downloading ffmpeg $FFMPEG_VERSION...${NC}"
    wget -q --show-progress "https://ffmpeg.org/releases/$FFMPEG_SRC.tar.xz"
    tar xf "$FFMPEG_SRC.tar.xz"
    rm "$FFMPEG_SRC.tar.xz"
fi
echo -e "${GREEN}✓ ffmpeg source: $FFMPEG_SRC${NC}"

# ─── Build ─────────────────────────────────────────────────

cd "$FFMPEG_SRC"
mkdir -p "$OUT_DIR"

echo -e "${CYAN}Configuring...${NC}"

./configure \
    --prefix="$OUT_DIR" \
    --target-os=android \
    --arch="$ARCH" \
    --cpu="$CPU" \
    --cross-prefix="$TOOLCHAIN/bin/llvm-" \
    --cc="$CC" \
    --cxx="$CXX" \
    --ar="$AR" \
    --ranlib="$RANLIB" \
    --strip="$STRIP" \
    --sysroot="$SYSROOT" \
    --extra-cflags="$OPTIMIZE_CFLAGS -O3" \
    --extra-ldflags="-L$SYSROOT/usr/lib/$TRIPLET/$API" \
    --enable-cross-compile \
    --pkg-config=false \
    --disable-shared \
    --enable-static \
    --enable-small \
    `# Protocols (stream recording essentials)` \
    --enable-protocol=http \
    --enable-protocol=https \
    --enable-protocol=file \
    --enable-protocol=tcp \
    `# Demuxers/Muxers (FLV for B站 live)` \
    --enable-demuxer=flv \
    --enable-muxer=flv \
    --enable-demuxer=hls \
    `# Codecs (decode only, we do -c copy)` \
    --enable-decoder=h264 \
    --enable-decoder=aac \
    --enable-decoder=hevc \
    `# Filters (minimal)` \
    --disable-filters \
    --enable-filter=copy \
    --enable-filter=null \
    `# Disable everything else to minimize size` \
    --disable-doc \
    --disable-ffplay \
    --disable-ffprobe \
    --disable-avdevice \
    --disable-postproc \
    --disable-network \
    --enable-openssl \
    --disable-everything \
    --enable-muxer=flv \
    --enable-demuxer=flv \
    --enable-demuxer=hls \
    --enable-demuxer=mpegts \
    --enable-protocol=http \
    --enable-protocol=https \
    --enable-protocol=file \
    --enable-protocol=tcp \
    --enable-decoder=h264 \
    --enable-decoder=aac \
    --enable-decoder=hevc \
    --enable-bsf=aac_adtstoasc \
    --enable-bsf=h264_mp4toannexb \
    --enable-bsf=hevc_mp4toannexb

echo -e "${CYAN}Compiling (this takes ~5-15 min)...${NC}"
make -j$(nproc) 2>&1 | tail -5
make install 2>&1 | tail -3

# ─── Output ────────────────────────────────────────────────

BINARY="$OUT_DIR/bin/ffmpeg"
if [ -f "$BINARY" ]; then
    chmod +x "$BINARY"
    SIZE=$(du -h "$BINARY" | cut -f1)
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ffmpeg built successfully!            ║${NC}"
    echo -e "${GREEN}║  Size:  $SIZE                          ║${NC}"
    echo -e "${GREEN}║  Path:  $BINARY                        ║${NC}"
    echo -e "${GREEN}║                                        ║${NC}"
    echo -e "${GREEN}║  Next step:                            ║${NC}"
    echo -e "${GREEN}║  Copy to: app/src/main/assets/ffmpeg/  ║${NC}"
    echo -e "${GREEN}║           arm64-v8a/ffmpeg             ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}Build failed: ffmpeg binary not found${NC}"
    exit 1
fi
