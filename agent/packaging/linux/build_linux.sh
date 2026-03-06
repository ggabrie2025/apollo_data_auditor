#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Linux Build Script (PyInstaller)
# =============================================================================
#
# Prerequisites:
#     pip install pyinstaller
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

echo "=== Apollo Agent Build Script (PyInstaller - Linux) ==="
echo "Agent directory: $AGENT_DIR"

# Check PyInstaller
if ! python3 -m PyInstaller --version &>/dev/null; then
    echo "Error: PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf "$SCRIPT_DIR/dist" "$SCRIPT_DIR/build"

# Build with PyInstaller
echo ""
echo "Building with PyInstaller..."
cd "$AGENT_DIR/.."
python3 -m PyInstaller --onefile \
    --name apollo-agent \
    --distpath "$SCRIPT_DIR/dist" \
    --workpath "$SCRIPT_DIR/build" \
    --add-data "agent/ui/static:agent/ui/static" \
    --add-data "agent/config:agent/config" \
    --hidden-import asyncpg \
    --hidden-import aiomysql \
    --hidden-import motor \
    --hidden-import aioodbc \
    --hidden-import msal \
    --hidden-import aiohttp \
    --hidden-import pybloom_live \
    --hidden-import openpyxl \
    --hidden-import uvicorn \
    --hidden-import fastapi \
    --hidden-import httpx \
    --hidden-import pydantic \
    --hidden-import yaml \
    --hidden-import apollo_io_native \
    agent/main.py

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
