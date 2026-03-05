---
title: "Build & Packaging - macOS Agent"
agent: rails-executor
project_id: PRJ-APOLLO
date: 2026-02-24
tags: [macos, pyinstaller, packaging]
category: technical
type: guide
status: active
---

# Apollo Agent - macOS Build & Packaging

> **Note**: macOS build uses PyInstaller (legacy). Migration to Nuitka is planned (P3).

## Prerequisites

### Build Machine (macOS)

```bash
# Python 3.12+
pip install pyinstaller

# UPX (optional, for compression)
brew install upx
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
cd agent/packaging/macos
./build_macos.sh
```

### Option 2: Makefile

```bash
cd agent/packaging
make build-macos
```

## Output

```
dist/
  apollo-agent        (~20-50 MB, CLI binary)
  Apollo Agent.app    (macOS app bundle, if spec configured)
```

## Install (Manual)

macOS does not have an automated installer yet. Manual steps:

```bash
# Copy binary to /usr/local/bin
sudo cp dist/apollo-agent /usr/local/bin/

# Create config directory
sudo mkdir -p /etc/apollo

# Write config
sudo tee /etc/apollo/config.json << EOF
{
  "api_key": "YOUR_API_KEY",
  "hub_url": "https://apollo-cloud-api-production.up.railway.app",
  "log_dir": "/var/log/apollo",
  "output_dir": "/var/lib/apollo/output"
}
EOF
sudo chmod 600 /etc/apollo/config.json

# Create log/output dirs
sudo mkdir -p /var/log/apollo /var/lib/apollo/output
```

## Test

```bash
dist/apollo-agent --version
dist/apollo-agent /path/to/scan --preview
```

## Spec File

`apollo_agent.spec` — PyInstaller spec file defining:
- Entry point: `agent/main.py`
- Bundled data: `config/exclusions.yaml`, `VERSION`
- Included modules: yaml, ldap3, requests, pymongo, psycopg2, etc.
- `apollo_io_native.so` (Rust PyO3 module)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| PyInstaller not found | `pip install pyinstaller` |
| Code signing required | `codesign --deep --sign - dist/apollo-agent` (ad-hoc) |
| Gatekeeper blocks | See `agent/packaging/DEBLOCAGE_OS.md` — procedure complete |
| Missing modules | Add to `hiddenimports` in `apollo_agent.spec` |
| Binary too large | Install UPX: `brew install upx` |

## Roadmap

- **P3**: Migrate from PyInstaller to Nuitka (align with Linux/Windows)
- **P3**: Automated `.pkg` installer with API key prompt
- **P3**: Homebrew cask distribution

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
