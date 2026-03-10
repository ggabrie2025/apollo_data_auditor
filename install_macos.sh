#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Install Script (macOS)
# =============================================================================
#
# Usage:
#     curl -sSL https://aiia-tech.com/download/install_macos.sh | bash
#
# Or locally (recommended — audit before running):
#     curl -O https://aiia-tech.com/download/install_macos.sh
#     bash install_macos.sh [--api-key YOUR_KEY] [--no-verify]
#
# ARCHITECTURE : binaire natif arm64 (Apple Silicon M1/M2/M3/M4).
#
# Binaires officiels distribues exclusivement via aiia-tech.com
#
# Copyright: (c) 2025-2026 Gilles Gabriel <contact@aiia-tech.com>
# =============================================================================

set -e

DOWNLOAD_BASE="${DOWNLOAD_BASE:-https://aiia-tech.com/download}"
BINARY_NAME="apollo-agent-macos"
INSTALL_PATH="/usr/local/bin/apollo-agent"
CONFIG_DIR="$HOME/.apollo"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

API_KEY=""
HUB_URL="https://apollo-cloud-api-production.up.railway.app"
SKIP_VERIFY=0

# Parse args
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --api-key) API_KEY="$2"; shift ;;
        --hub-url) HUB_URL="$2"; shift ;;
        --no-verify) SKIP_VERIFY=1 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

echo ""
echo "=== Apollo Agent Installer (macOS) ==="
echo ""

# Check OS
if [ "$(uname -s)" != "Darwin" ]; then
    echo -e "${RED}Error: This installer supports macOS only.${NC}"
    echo "Linux : curl -sSL https://aiia-tech.com/download/install.sh | bash"
    echo "Windows : see https://aiia-tech.com/download/install_windows.ps1"
    exit 1
fi

# Architecture info
ARCH=$(uname -m)
echo "Architecture : $ARCH"

TMP_DIR=$(mktemp -d)
trap "rm -rf '$TMP_DIR'" EXIT

# Download binary
echo ""
echo "Downloading $BINARY_NAME from aiia-tech.com..."
curl -sSL --fail "${DOWNLOAD_BASE}/${BINARY_NAME}" -o "$TMP_DIR/apollo-agent" || {
    echo -e "${RED}Error: Download failed. Check https://aiia-tech.com/download${NC}"
    exit 1
}
chmod +x "$TMP_DIR/apollo-agent"

# SHA256 verification
if [ "$SKIP_VERIFY" -eq 1 ]; then
    echo -e "${YELLOW}Warning: Integrity check skipped (--no-verify). NOT recommended.${NC}"
else
    echo ""
    echo "Verifying binary integrity..."

    curl -sSL --fail "${DOWNLOAD_BASE}/SHA256SUMS.txt" -o "$TMP_DIR/SHA256SUMS.txt" || {
        echo -e "${RED}Error: Could not download SHA256SUMS.txt from ${DOWNLOAD_BASE}/SHA256SUMS.txt${NC}"
        echo "Binary integrity cannot be verified. Aborting."
        echo "Contact: contact@aiia-tech.com"
        exit 1
    }

    EXPECTED=$(grep "apollo-agent-macos" "$TMP_DIR/SHA256SUMS.txt" | awk '{print $1}')
    ACTUAL=$(shasum -a 256 "$TMP_DIR/apollo-agent" | awk '{print $1}')

    if [ -z "$EXPECTED" ]; then
        echo -e "${RED}Error: apollo-agent-macos not found in SHA256SUMS.txt${NC}"
        echo "Binary integrity cannot be verified. Aborting."
        echo "Contact: contact@aiia-tech.com"
        exit 1
    fi

    if [ "$EXPECTED" != "$ACTUAL" ]; then
        echo ""
        echo -e "${RED}======================================================${NC}"
        echo -e "${RED}  BINARY INTEGRITY CHECK FAILED                      ${NC}"
        echo -e "${RED}  Do not execute this binary.                         ${NC}"
        echo -e "${RED}  Contact: contact@aiia-tech.com                      ${NC}"
        echo -e "${RED}======================================================${NC}"
        echo ""
        echo "  Expected: $EXPECTED"
        echo "  Actual:   $ACTUAL"
        echo ""
        exit 1
    fi

    echo -e "${GREEN}Integrity check passed (SHA256 OK)${NC}"
fi

# Remove Gatekeeper quarantine flag
echo ""
echo "Removing Gatekeeper quarantine flag..."
xattr -dr com.apple.quarantine "$TMP_DIR/apollo-agent" 2>/dev/null || true

# Install
echo "Installing to $INSTALL_PATH..."
sudo mkdir -p "$(dirname "$INSTALL_PATH")"
sudo cp "$TMP_DIR/apollo-agent" "$INSTALL_PATH"
sudo chmod 755 "$INSTALL_PATH"

# Write config if API key provided
if [ -n "$API_KEY" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/config.json" << EOF
{
  "api_key": "${API_KEY}",
  "hub_url": "${HUB_URL}"
}
EOF
    chmod 600 "$CONFIG_DIR/config.json"
    echo "Config written to $CONFIG_DIR/config.json"
fi

echo ""
echo -e "${GREEN}=== Installation complete ===${NC}"
echo ""
echo "Apollo Agent installed at $INSTALL_PATH"
echo ""
echo "Quick start:"
echo "  apollo-agent --version"
echo "  apollo-agent --serve          # Launch UI on http://localhost:8052"
echo "  apollo-agent /path/to/scan    # CLI scan"
echo ""
if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}Note: No API key configured. Edit $CONFIG_DIR/config.json${NC}"
    echo ""
fi
echo "Documentation: https://aiia-tech.com"
echo "Support: contact@aiia-tech.com"
