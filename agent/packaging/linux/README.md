---
title: "Build & Packaging - Linux Agent"
agent: rails-executor
project_id: PRJ-APOLLO
date: 2026-02-24
tags: [linux, pyinstaller, packaging, systemd, installer]
category: technical
type: guide
status: active
---

# Apollo Agent - Linux Build & Packaging

## Prerequisites

### Build Machine (Linux x64)

```bash
# Python 3.12+
pip install pyinstaller
```

### Rust Module

```bash
cd apollo_io_native
maturin develop --release
# Output: apollo_io_native.so (loaded automatically by Python)
```

## Build

### Option 1: Build Script

```bash
cd agent/packaging/linux
./build_linux.sh
```

### Option 2: Makefile

```bash
cd agent/packaging
make build-linux
```

## Output

```
dist/
  apollo-agent    (~20-50 MB, standalone, no Python required)
```

If `patchelf` is not installed, falls back to `--standalone` mode (directory output instead of single file).

## Install

### Automated Install

```bash
sudo ./install.sh --api-key clientname_xxx
```

Optional: specify custom Hub URL:

```bash
sudo ./install.sh --api-key clientname_xxx --hub-url https://custom-hub.example.com
```

### What Gets Installed

| Path | Content |
|------|---------|
| `/opt/apollo-agent/apollo-agent` | Binary executable |
| `/opt/apollo-agent/config/` | exclusions.yaml, VERSION |
| `/etc/apollo/config.json` | API key + settings (chmod 600) |
| `/var/log/apollo/` | Log files |
| `/var/lib/apollo/output/` | Scan output |
| `/etc/systemd/system/apollo-agent.service` | Systemd unit |

### Systemd Commands

```bash
sudo systemctl start apollo-agent     # Start the agent
sudo systemctl enable apollo-agent    # Enable at boot
sudo systemctl status apollo-agent    # Check status
sudo journalctl -u apollo-agent -f    # View logs
```

## Uninstall

```bash
sudo systemctl stop apollo-agent
sudo systemctl disable apollo-agent
sudo rm /etc/systemd/system/apollo-agent.service
sudo systemctl daemon-reload
sudo rm -rf /opt/apollo-agent /etc/apollo /var/log/apollo /var/lib/apollo
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| PyInstaller build fails | Check `pip install pyinstaller` |
| Missing modules | Add `--hidden-import=xxx` to build_linux.sh |
| Permission denied | Run install.sh with `sudo` |
| Service won't start | Check logs: `journalctl -u apollo-agent -n 50` |
| Binary too large | Normal (50-100 MB). PyInstaller bundles Python runtime. |

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
