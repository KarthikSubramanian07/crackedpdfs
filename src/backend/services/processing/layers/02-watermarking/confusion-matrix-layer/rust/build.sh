#!/bin/bash
set -e

echo "🔨 Building Rust confusion matrix layer..."

# Detect platform
PLATFORM=$(uname -s)
ARCH=$(uname -m)

# Set library extension
if [ "$PLATFORM" = "Linux" ]; then
    LIB_EXT="so"
    PDFIUM_LIB="libpdfium.so"
elif [ "$PLATFORM" = "Darwin" ]; then
    LIB_EXT="dylib"
    PDFIUM_LIB="libpdfium.dylib"
elif [ "$PLATFORM" = "MINGW"* ] || [ "$PLATFORM" = "MSYS"* ] || [ "$PLATFORM" = "CYGWIN"* ]; then
    LIB_EXT="dll"
    PDFIUM_LIB="pdfium.dll"
else
    echo "❌ Unsupported platform: $PLATFORM"
    exit 1
fi

# Build in release mode
cargo build --release

# Create binaries directory
mkdir -p ../binaries

# Copy compiled binary
if [ "$PLATFORM" = "MINGW"* ] || [ "$PLATFORM" = "MSYS"* ] || [ "$PLATFORM" = "CYGWIN"* ]; then
    cp target/release/noise_stuffy_layer.exe ../binaries/
    echo "✅ Binary: ../binaries/noise_stuffy_layer.exe"
else
    cp target/release/noise_stuffy_layer ../binaries/
    echo "✅ Binary: ../binaries/noise_stuffy_layer"
fi

# Copy shared library if exists
if [ -f "target/release/libnoise_stuffy_layer.$LIB_EXT" ]; then
    cp "target/release/libnoise_stuffy_layer.$LIB_EXT" ../binaries/
    echo "✅ Library: ../binaries/libnoise_stuffy_layer.$LIB_EXT"
fi

echo ""
echo "📦 Build complete!"
echo ""
echo "⚠️  IMPORTANT: You must provide Pdfium library manually:"
echo "   - Download from: https://github.com/bblanchon/pdfium-binaries/releases"
echo "   - Place $PDFIUM_LIB in ../binaries/ directory"
echo "   - Set PDFIUM_DYNAMIC_LIB_PATH environment variable if needed"
echo ""
echo "🧠 VGG16 weights will auto-download on first run from:"
echo "   https://github.com/LaurentMazare/tch-rs/releases/download/mw/vgg16.ot"
