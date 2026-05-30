#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/setup_third_party.sh [--force]

Downloads libtorch + Pdfium into third_party/ and copies Pdfium's shared
library into the confusion-matrix binaries directory.

Environment overrides:
  LIBTORCH_URL        Custom download URL for libtorch
  LIBTORCH_SHA256     Expected SHA256 checksum for libtorch archive
  PDFIUM_URL          Custom download URL for Pdfium
  PDFIUM_SHA256       Expected SHA256 checksum for Pdfium archive

Use --force to re-download and overwrite existing artifacts.
USAGE
}

FORCE_DOWNLOAD=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -f|--force)
      FORCE_DOWNLOAD=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ROOT="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_PARTY="$ROOT/third_party"
BIN_DIR="$ROOT/src/backend/services/processing/layers/02-watermarking/confusion-matrix-layer/binaries"
LIBTORCH_DIR="$THIRD_PARTY/libtorch"

mkdir -p "$THIRD_PARTY" "$BIN_DIR"

log() {
  printf '[setup] %s\n' "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' not found in PATH" >&2
    exit 1
  fi
}

need_cmd curl
need_cmd unzip
need_cmd tar

OS_NAME="$(uname -s)"
ARCH="$(uname -m)"

case "$OS_NAME" in
  Linux)
    PLATFORM_KEY="linux"
    DEFAULT_LIBTORCH_URL="https://download.pytorch.org/libtorch/cpu/libtorch-cxx11-abi-shared-with-deps-2.1.0%2Bcpu.zip"
    LIBTORCH_SENTINEL="$LIBTORCH_DIR/lib/libtorch.so"
    DEFAULT_PDFIUM_URL="https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/6666/pdfium-linux-x64.tgz"
    PDFIUM_LIB_NAME="libpdfium.so"
    ;;
  Darwin)
    PLATFORM_KEY="mac"
    if [ "$ARCH" = "arm64" ]; then
      DEFAULT_LIBTORCH_URL="https://download.pytorch.org/libtorch/cpu/libtorch-macos-arm64-2.1.0.zip"
      DEFAULT_PDFIUM_URL="https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/6666/pdfium-mac-arm64.tgz"
    else
      DEFAULT_LIBTORCH_URL="https://download.pytorch.org/libtorch/cpu/libtorch-macos-2.1.0.zip"
      DEFAULT_PDFIUM_URL="https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/6666/pdfium-mac-x64.tgz"
    fi
    LIBTORCH_SENTINEL="$LIBTORCH_DIR/lib/libtorch.dylib"
    PDFIUM_LIB_NAME="libpdfium.dylib"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM_KEY="windows"
    DEFAULT_LIBTORCH_URL="https://download.pytorch.org/libtorch/cu121/libtorch-win-shared-with-deps-2.3.0.zip"
    LIBTORCH_SENTINEL="$LIBTORCH_DIR/lib/torch_cpu.dll"
    DEFAULT_PDFIUM_URL="https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/6666/pdfium-win-x64.tgz"
    PDFIUM_LIB_NAME="pdfium.dll"
    ;;
  *)
    echo "Unsupported platform: $OS_NAME" >&2
    exit 1
    ;;
esac

PDFIUM_SENTINEL="$BIN_DIR/$PDFIUM_LIB_NAME"
PDFIUM_WORK_DIR="$THIRD_PARTY/pdfium-$PLATFORM_KEY"

LIBTORCH_URL="${LIBTORCH_URL:-$DEFAULT_LIBTORCH_URL}"
PDFIUM_URL="${PDFIUM_URL:-$DEFAULT_PDFIUM_URL}"

libtorch_filename=$(basename "${LIBTORCH_URL%%\?*}")
pdfium_filename=$(basename "${PDFIUM_URL%%\?*}")
LIBTORCH_ARCHIVE="$THIRD_PARTY/$libtorch_filename"
PDFIUM_ARCHIVE="$THIRD_PARTY/$pdfium_filename"

maybe_verify() {
  local expected="$1"
  local file="$2"

  if [ -z "$expected" ]; then
    return
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    echo "$expected  $file" | sha256sum --check -
  elif command -v shasum >/dev/null 2>&1; then
    echo "$expected  $file" | shasum -a 256 --check -
  else
    log "Checksum tools unavailable; skipping verification for $(basename "$file")"
  fi
}

download_file() {
  local url="$1"
  local dest="$2"

  if [ "$FORCE_DOWNLOAD" -eq 0 ] && [ -f "$dest" ]; then
    log "Using cached $(basename "$dest")"
    return
  fi

  log "Downloading $(basename "$dest")"
  rm -f "$dest"
  local tmp="${dest}.part"
  curl -L --fail --progress-bar "$url" -o "$tmp"
  mv "$tmp" "$dest"
}

install_libtorch() {
  if [ "$FORCE_DOWNLOAD" -eq 0 ] && [ -f "$LIBTORCH_SENTINEL" ]; then
    log "libtorch already installed at $LIBTORCH_DIR"
    return
  fi

  download_file "$LIBTORCH_URL" "$LIBTORCH_ARCHIVE"
  maybe_verify "${LIBTORCH_SHA256:-}" "$LIBTORCH_ARCHIVE"
  log "Extracting libtorch..."
  rm -rf "$LIBTORCH_DIR"
  unzip -q "$LIBTORCH_ARCHIVE" -d "$THIRD_PARTY"
}

install_pdfium() {
  if [ "$FORCE_DOWNLOAD" -eq 0 ] && [ -f "$PDFIUM_SENTINEL" ]; then
    log "Pdfium already available at $PDFIUM_SENTINEL"
    return
  fi

  download_file "$PDFIUM_URL" "$PDFIUM_ARCHIVE"
  maybe_verify "${PDFIUM_SHA256:-}" "$PDFIUM_ARCHIVE"
  log "Extracting Pdfium..."
  rm -rf "$PDFIUM_WORK_DIR"
  mkdir -p "$PDFIUM_WORK_DIR"
  tar -xzf "$PDFIUM_ARCHIVE" -C "$PDFIUM_WORK_DIR"
  local source="$PDFIUM_WORK_DIR/bin/$PDFIUM_LIB_NAME"
  if [ ! -f "$source" ]; then
    echo "Pdfium archive did not contain $PDFIUM_LIB_NAME" >&2
    exit 1
  fi
  cp "$source" "$PDFIUM_SENTINEL"
  log "Pdfium library placed at $PDFIUM_SENTINEL"
}

install_libtorch
install_pdfium

cat <<EOF
[setup] Native dependencies ready.
[setup] Pdfium shared library copied to $PDFIUM_SENTINEL.
[setup] Export LIBTORCH=$LIBTORCH_DIR (or set it in your .env) so the Rust layer can locate libtorch.
EOF
