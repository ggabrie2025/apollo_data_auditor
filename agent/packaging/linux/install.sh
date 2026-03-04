#!/bin/bash
# =============================================================================
# Apollo Agent V1.7.R - Linux Install Script
# =============================================================================
#
# Usage:
#     sudo ./install.sh [--api-key KEY] [--hub-url URL]
#
# Installs:
#     /opt/apollo-agent/apollo-agent       (binary)
#     /opt/apollo-agent/config/            (configuration)
#     /etc/apollo/config.json              (API key + settings)
#     /var/log/apollo/                     (logs)
#     /etc/systemd/system/apollo-agent.service  (systemd unit)
#
# Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
# =============================================================================

set -e

INSTALL_DIR="/opt/apollo-agent"
CONFIG_DIR="/etc/apollo"
LOG_DIR="/var/log/apollo"
OUTPUT_DIR="/var/lib/apollo/output"
SERVICE_NAME="apollo-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
API_KEY=""
HUB_URL="https://apollo-cloud-api-production.up.railway.app"

while [[ $# -gt 0 ]]; do
    case $1 in
        --api-key) API_KEY="$2"; shift 2 ;;
        --hub-url) HUB_URL="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

# Check binary exists
BINARY="$SCRIPT_DIR/dist/apollo-agent"
if [ ! -f "$BINARY" ]; then
    echo "Error: Binary not found at $BINARY"
    echo "Run build_linux.sh first."
    exit 1
fi

# Prompt for API key if not provided
if [ -z "$API_KEY" ]; then
    read -p "Enter your Apollo API key: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "Error: API key is required."
        exit 1
    fi
fi

echo "=== Installing Apollo Agent ==="

# Create directories
mkdir -p "$INSTALL_DIR/config" "$CONFIG_DIR" "$LOG_DIR" "$OUTPUT_DIR"

# Copy binary
echo "Installing binary..."
cp "$BINARY" "$INSTALL_DIR/apollo-agent"
chmod 755 "$INSTALL_DIR/apollo-agent"

# Copy config
echo "Installing configuration..."
cp "$SCRIPT_DIR/../../config/exclusions.yaml" "$INSTALL_DIR/config/"
cp "$SCRIPT_DIR/../../VERSION" "$INSTALL_DIR/"

# Write config.json
cat > "$CONFIG_DIR/config.json" << EOF
{
  "api_key": "$API_KEY",
  "hub_url": "$HUB_URL",
  "version": "$(cat "$INSTALL_DIR/VERSION")",
  "log_dir": "$LOG_DIR",
  "output_dir": "$OUTPUT_DIR"
}
EOF
chmod 600 "$CONFIG_DIR/config.json"

# Create systemd service
echo "Installing systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Apollo Data Auditor Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/apollo-agent --daemon
Restart=on-failure
RestartSec=30
User=root
Environment=PYTHONUTF8=1
WorkingDirectory=${INSTALL_DIR}
StandardOutput=append:${LOG_DIR}/apollo-agent.log
StandardError=append:${LOG_DIR}/apollo-agent-error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

echo ""
echo "=== Installation Complete ==="
echo "Binary:  $INSTALL_DIR/apollo-agent"
echo "Config:  $CONFIG_DIR/config.json"
echo "Logs:    $LOG_DIR/"
echo ""
echo "Commands:"
echo "  sudo systemctl start $SERVICE_NAME    # Start the agent"
echo "  sudo systemctl enable $SERVICE_NAME   # Enable at boot"
echo "  sudo systemctl status $SERVICE_NAME   # Check status"
echo "  sudo journalctl -u $SERVICE_NAME -f   # View logs"
