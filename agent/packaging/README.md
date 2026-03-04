---
title: "Build & Packaging - Apollo Agent (Overview)"
agent: rails-executor
project_id: PRJ-APOLLO
date: 2026-02-24
tags: [packaging, build, nuitka, installer, cross-platform]
category: technical
type: guide
status: active
---

# Apollo Agent - Packaging Overview

Build system for producing standalone agent binaries and installers for all platforms.

## Architecture

```
agent/packaging/
  Makefile              Unified build commands
  README.md             This file
  windows/
    build_windows.bat   Batch build script
    build_windows.py    Python build script (Nuitka)
    installer.iss       Inno Setup installer definition
    README.md           Windows build guide
  linux/
    build_linux.sh      Nuitka build script
    install.sh          Automated installer (systemd)
    README.md           Linux build guide
  macos/
    build_macos.sh      PyInstaller build script (legacy)
    apollo_agent.spec   PyInstaller spec file
    README.md           macOS build guide
```

## Quick Start (Makefile)

```bash
cd agent/packaging

make build-windows     # Build Windows binary (Nuitka)
make build-linux       # Build Linux binary (Nuitka)
make build-macos       # Build macOS binary (PyInstaller)
make installer-win     # Build Windows installer (Inno Setup)
make clean             # Remove all build artifacts
make help              # Show available targets
```

## Platform Matrix

| Platform | Build Tool | Installer | Status |
|----------|-----------|-----------|--------|
| **Windows x64** | Nuitka 4.x + MSVC | Inno Setup 6.x (.exe) | Production |
| **Linux x64** | Nuitka + GCC | install.sh (systemd) | Production |
| **macOS** | PyInstaller | Manual | Legacy (P3: migrate to Nuitka) |

## Build Pipeline (Windows — Production)

```
1. Cross-compile Rust .pyd (Mac → cargo-xwin → apollo_io_native.pyd)
2. Transfer .pyd to Windows VM (shared drive Z:\)
3. Build binary on VM (Nuitka → apollo-agent.exe ~100 MB)
4. Build installer (Inno Setup → APOLLO_DataAuditor_Setup_1.7.R_x64.exe ~25 MB)
5. Test installer on clean VM
6. Ship setup.exe to client
```

## Build Pipeline (Linux — Production)

```
1. Build Rust module (maturin develop --release → apollo_io_native.so)
2. Build binary (Nuitka → apollo-agent ~20-50 MB)
3. Install (sudo ./install.sh --api-key xxx)
4. Enable service (systemctl enable apollo-agent)
```

## Output Summary

| Platform | Binary | Installer |
|----------|--------|-----------|
| Windows | `dist/apollo-agent.exe` | `output/APOLLO_DataAuditor_Setup_1.7.R_x64.exe` |
| Linux | `dist/apollo-agent` | N/A (install.sh) |
| macOS | `dist/apollo-agent` | N/A (manual) |

## Client Experience

The client receives a single installer file. No Python, Rust, or build tools required.

- **Windows**: Double-click `APOLLO_DataAuditor_Setup_1.7.R_x64.exe` → GUI wizard with API key page
- **Linux**: `sudo ./install.sh --api-key xxx` → Binary + systemd service
- **macOS**: Manual copy (automated installer planned P3)

## Rust Module (apollo_io_native)

Each platform needs the Rust PyO3 module compiled natively:

| Platform | Output | Build Command |
|----------|--------|---------------|
| Windows | `apollo_io_native.pyd` | `cargo xwin build --release --target x86_64-pc-windows-msvc` |
| Linux | `apollo_io_native.so` | `maturin develop --release` |
| macOS | `apollo_io_native.so` | `maturin develop --release` |

See `apollo_io_native/BUILD.md` for detailed Rust build instructions.

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
