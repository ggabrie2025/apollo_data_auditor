#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Install Script (Linux) — UI-Friendly
# =============================================================================
#
# Usage:
#     curl -sSL https://aiia-tech.com/download/install.sh | bash
#
# Or locally:
#     bash install.sh [--api-key YOUR_KEY] [--hub-url URL] [--no-verify] [--no-launch]
#
# ZERO sudo — installe dans ~/.apollo/bin/ (home directory).
# Apres installation, lance automatiquement l'UI agent et ouvre le navigateur.
#
# Binaires officiels distribues exclusivement via aiia-tech.com
#
# Copyright: (c) 2025-2026 Gilles Gabriel <contact@aiia-tech.com>
# =============================================================================

set -e

DOWNLOAD_BASE="${DOWNLOAD_BASE:-https://aiia-tech.com/download}"
INSTALL_DIR="$HOME/.apollo/bin"
INSTALL_PATH="$INSTALL_DIR/apollo-agent"
CONFIG_DIR="$HOME/.apollo"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

API_KEY=""
HUB_URL="https://apollo-cloud-api-production.up.railway.app"
SKIP_VERIFY=0
NO_LAUNCH=0

# Parse args
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --api-key) API_KEY="$2"; shift ;;
        --hub-url) HUB_URL="$2"; shift ;;
        --no-verify) SKIP_VERIFY=1 ;;
        --no-launch) NO_LAUNCH=1 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

echo ""
echo -e "${CYAN}=== Apollo Agent Installer (Linux) ===${NC}"
echo ""

# Check OS
OS=$(uname -s)
if [ "$OS" != "Linux" ]; then
    echo -e "${RED}Error: This installer supports Linux only.${NC}"
    echo "macOS : curl -sSL https://aiia-tech.com/download/install_macos.sh | bash"
    echo "Windows : see https://aiia-tech.com/download/install_windows.ps1"
    exit 1
fi

# Architecture info
ARCH=$(uname -m)
echo "  Architecture : $ARCH"

TMP_DIR=$(mktemp -d)
trap "rm -rf '$TMP_DIR'" EXIT

# Download binary
echo ""
echo "  Downloading apollo-agent from aiia-tech.com..."
BINARY_URL="${DOWNLOAD_BASE}/apollo-agent"
SHA256_URL="${DOWNLOAD_BASE}/SHA256SUMS.txt"

curl -sSL --fail "$BINARY_URL" -o "$TMP_DIR/apollo-agent" || {
    echo -e "${RED}Error: Download failed. Check https://aiia-tech.com/download${NC}"
    exit 1
}
chmod +x "$TMP_DIR/apollo-agent"

# Verify SHA256 — mandatory unless --no-verify
if [ "$SKIP_VERIFY" -eq 1 ]; then
    echo -e "${YELLOW}  Warning: Integrity check skipped (--no-verify). NOT recommended.${NC}"
else
    echo ""
    echo "  Verifying binary integrity..."

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

    echo -e "${GREEN}  Integrity check passed (SHA256 OK)${NC}"
fi

# Install to ~/.apollo/bin/ (NO sudo required)
echo ""
echo "  Installing to $INSTALL_PATH..."
mkdir -p "$INSTALL_DIR"
cp "$TMP_DIR/apollo-agent" "$INSTALL_PATH"
chmod 755 "$INSTALL_PATH"

# Add to PATH if not already there
SHELL_RC=""
if [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.profile" ]; then
    SHELL_RC="$HOME/.profile"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q '\.apollo/bin' "$SHELL_RC" 2>/dev/null; then
        echo '' >> "$SHELL_RC"
        echo '# Apollo Agent' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.apollo/bin:$PATH"' >> "$SHELL_RC"
        echo -e "  ${GREEN}PATH updated in $(basename "$SHELL_RC")${NC}"
    fi
fi

# Export PATH for current session
export PATH="$INSTALL_DIR:$PATH"

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
    echo "  Config written to $CONFIG_DIR/config.json"
fi

echo ""
echo -e "${GREEN}=== Installation complete ===${NC}"
echo ""
echo "  Apollo Agent installed at $INSTALL_PATH"
echo ""

# Auto-launch UI agent + open browser (unless --no-launch)
if [ "$NO_LAUNCH" -eq 0 ]; then
    echo -e "${CYAN}  Launching Apollo Agent UI...${NC}"
    echo ""

    # Launch the agent in serve mode (it auto-opens browser to login.html)
    # The agent finds a free port (8052-8099) and opens the browser automatically
    "$INSTALL_PATH" --serve &
    AGENT_PID=$!

    echo "  Agent running (PID: $AGENT_PID)"
    echo ""
    echo "  Your browser should open automatically."
    echo "  If not, open: http://localhost:8052"
    echo ""
    if [ -z "$API_KEY" ]; then
        echo -e "${YELLOW}  Enter your API key in the login page to start scanning.${NC}"
        echo "  No key yet? Request beta access at https://aiia-tech.com"
    fi
    echo ""
    echo "  To stop the agent: kill $AGENT_PID"
    echo "  To relaunch later: apollo-agent --serve"
else
    echo "  To launch the UI: apollo-agent --serve"
    echo "  (opens browser automatically)"
fi

echo ""
echo "  Documentation: https://aiia-tech.com"
echo "  Support: contact@aiia-tech.com"
echo ""
