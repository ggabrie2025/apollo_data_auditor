#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Install Script (Linux)
# =============================================================================
#
# Usage:
#     curl -sSL https://aiia-tech.com/download/install.sh | bash
#
# Or locally:
#     bash install.sh [--api-key YOUR_KEY] [--hub-url URL] [--no-verify]
#
# Binaires officiels distribues exclusivement via aiia-tech.com
#
# Copyright: (c) 2025-2026 Gilles Gabriel <contact@aiia-tech.com>
# =============================================================================

set -e

DOWNLOAD_BASE="https://aiia-tech.com/download"
INSTALL_DIR="/opt/apollo-agent"
CONFIG_DIR="/etc/apollo"
LOG_DIR="/var/log/apollo"
OUTPUT_DIR="/var/lib/apollo/output"
SERVICE_NAME="apollo-agent"

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
echo "=== Apollo Agent Installer ==="
echo ""

# Check OS
OS=$(uname -s)
if [ "$OS" != "Linux" ]; then
    echo -e "${RED}Error: This installer supports Linux only.${NC}"
    echo "macOS / Windows: download from https://aiia-tech.com/download"
    exit 1
fi

TMP_DIR=$(mktemp -d)
trap "rm -rf '$TMP_DIR'" EXIT

# Download binary
echo "Downloading apollo-agent from aiia-tech.com..."
BINARY_URL="${DOWNLOAD_BASE}/apollo-agent"
SHA256_URL="${DOWNLOAD_BASE}/SHA256SUMS.txt"

curl -sSL --fail "$BINARY_URL" -o "$TMP_DIR/apollo-agent" || {
    echo -e "${RED}Error: Download failed. Check https://aiia-tech.com/download${NC}"
    exit 1
}
chmod +x "$TMP_DIR/apollo-agent"

# Verify SHA256 — mandatory unless --no-verify
if [ "$SKIP_VERIFY" -eq 1 ]; then
    echo -e "${YELLOW}Warning: Integrity check skipped (--no-verify). NOT recommended.${NC}"
else
    echo ""
    echo "Verifying binary integrity..."

    curl -sSL --fail "$SHA256_URL" -o "$TMP_DIR/SHA256SUMS.txt" || {
        echo -e "${RED}Error: Could not download SHA256SUMS.txt from ${SHA256_URL}${NC}"
        echo "Binary integrity cannot be verified. Aborting."
        echo "Contact: contact@aiia-tech.com"
        exit 1
    }

    EXPECTED=$(grep "apollo-agent$" "$TMP_DIR/SHA256SUMS.txt" | awk '{print $1}')
    ACTUAL=$(sha256sum "$TMP_DIR/apollo-agent" | awk '{print $1}')

    if [ -z "$EXPECTED" ]; then
        echo -e "${RED}Error: apollo-agent not found in SHA256SUMS.txt${NC}"
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

    echo -e "${GREEN}Integrity check passed (SHA256 OK) ✓${NC}"
fi

# Install
echo ""
echo "Installing..."

sudo mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$OUTPUT_DIR"
sudo cp "$TMP_DIR/apollo-agent" "$INSTALL_DIR/apollo-agent"
sudo chmod 755 "$INSTALL_DIR/apollo-agent"

# Write config if API key provided
if [ -n "$API_KEY" ]; then
    sudo tee "$CONFIG_DIR/config.json" > /dev/null << EOF
{
  "api_key": "${API_KEY}",
  "hub_url": "${HUB_URL}",
  "log_dir": "${LOG_DIR}",
  "output_dir": "${OUTPUT_DIR}"
}
EOF
    sudo chmod 600 "$CONFIG_DIR/config.json"
    echo "Config written to $CONFIG_DIR/config.json"
fi

# Symlink
sudo ln -sf "$INSTALL_DIR/apollo-agent" /usr/local/bin/apollo-agent

echo ""
echo -e "${GREEN}=== Installation complete ===${NC}"
echo ""
echo "Apollo Agent installed at $INSTALL_DIR/apollo-agent"
echo ""
echo "Quick start:"
echo "  apollo-agent --version"
echo "  apollo-agent --serve          # Launch UI on http://localhost:8052"
echo "  apollo-agent /path/to/scan    # CLI scan"
echo ""
if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}Note: No API key configured. Run with:${NC}"
    echo "  sudo bash -c 'echo {\"api_key\": \"YOUR_KEY\", \"hub_url\": \"${HUB_URL}\"} > $CONFIG_DIR/config.json && chmod 600 $CONFIG_DIR/config.json'"
    echo ""
fi
echo "Documentation: https://aiia-tech.com"
echo "Support: contact@aiia-tech.com"
