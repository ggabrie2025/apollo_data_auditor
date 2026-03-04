#!/bin/bash
# =============================================================================
# Apollo Agent V1.3 - macOS Build Script
# =============================================================================
#
# Usage:
#     cd agent/packaging
#     ./build_macos.sh
#
# Prerequisites:
#     pip install pyinstaller
#
# Output:
#     dist/apollo-agent       (CLI binary)
#     dist/Apollo Agent.app   (macOS app bundle)
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Apollo Agent Build Script ==="
echo "Agent directory: $AGENT_DIR"
echo ""

# Check PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Check UPX (optional, for compression)
if command -v upx &> /dev/null; then
    echo "UPX found - binaries will be compressed"
else
    echo "UPX not found - binaries will not be compressed (optional)"
fi

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf "$SCRIPT_DIR/build" "$SCRIPT_DIR/dist"

# Run PyInstaller
echo ""
echo "Running PyInstaller..."
cd "$SCRIPT_DIR"
pyinstaller apollo_agent.spec --clean --noconfirm

# Check output
if [ -f "$SCRIPT_DIR/dist/apollo-agent" ]; then
    SIZE=$(du -h "$SCRIPT_DIR/dist/apollo-agent" | cut -f1)
    echo ""
    echo "=== BUILD SUCCESS ==="
    echo "Binary: $SCRIPT_DIR/dist/apollo-agent"
    echo "Size: $SIZE"
    echo ""
    echo "Test with:"
    echo "  $SCRIPT_DIR/dist/apollo-agent --version"
    echo "  $SCRIPT_DIR/dist/apollo-agent /path/to/scan --preview"
else
    echo ""
    echo "=== BUILD FAILED ==="
    exit 1
fi

# Check for .app bundle
if [ -d "$SCRIPT_DIR/dist/Apollo Agent.app" ]; then
    APP_SIZE=$(du -sh "$SCRIPT_DIR/dist/Apollo Agent.app" | cut -f1)
    echo "macOS App: $SCRIPT_DIR/dist/Apollo Agent.app"
    echo "App Size: $APP_SIZE"
fi
