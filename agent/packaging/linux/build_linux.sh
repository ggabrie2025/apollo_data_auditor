#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Linux Build Script (Nuitka)
# =============================================================================
#
# Prerequisites:
#     pip install nuitka ordered-set zstandard
#     sudo apt install patchelf  (for --onefile)
#
# Usage:
#     cd agent/packaging/linux
#     ./build_linux.sh
#
# Output:
#     dist/apollo-agent
#
# Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGING_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$(dirname "$PACKAGING_DIR")"

echo "=== Apollo Agent Build Script (Nuitka - Linux) ==="
echo "Agent directory: $AGENT_DIR"

# Check Nuitka
if ! python3 -m nuitka --version &>/dev/null; then
    echo "Error: Nuitka not found. Install with: pip install nuitka ordered-set zstandard"
    exit 1
fi

# Check patchelf (needed for --onefile on Linux)
if ! command -v patchelf &>/dev/null; then
    echo "Warning: patchelf not found. Install with: sudo apt install patchelf"
    echo "Falling back to --standalone mode (directory output)"
    ONEFILE=""
else
    ONEFILE="--onefile"
fi

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf "$SCRIPT_DIR/dist" "$SCRIPT_DIR/build"

# Build with Nuitka
echo ""
echo "Building with Nuitka (this may take 5-15 minutes on first build)..."
python3 -m nuitka \
    --standalone \
    $ONEFILE \
    --output-dir="$SCRIPT_DIR/dist" \
    --output-filename=apollo-agent \
    --include-data-files="$AGENT_DIR/config/exclusions.yaml=config/exclusions.yaml" \
    --include-data-files="$AGENT_DIR/VERSION=VERSION" \
    --include-data-dir="$AGENT_DIR/ui/static=agent/ui/static" \
    --include-module=yaml \
    --include-module=ldap3 \
    --include-module=requests \
    --include-module=asyncpg \
    --include-module=aiomysql \
    --include-module=pymongo \
    --include-module=motor \
    --include-module=pyodbc \
    --include-module=certifi \
    --include-module=apollo_io_native \
    --include-module=uvicorn \
    --include-module=fastapi \
    --include-module=pydantic \
    --include-module=dotenv \
    --include-module=starlette \
    --include-package=agent.core \
    --include-package=agent.models \
    --include-package=agent.observability \
    --include-package=agent.ui \
    --nofollow-import-to=tkinter \
    --nofollow-import-to=unittest \
    --nofollow-import-to=pydoc \
    "$AGENT_DIR/main.py"

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
    echo "  $SCRIPT_DIR/dist/apollo-agent --serve"
    echo "  $SCRIPT_DIR/dist/apollo-agent /path/to/scan --preview"
else
    echo ""
    echo "=== BUILD FAILED ==="
    exit 1
fi
