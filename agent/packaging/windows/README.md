---
title: "Build & Packaging - Windows Agent"
agent: rails-executor
project_id: PRJ-APOLLO
date: 2026-02-21
tags: [windows, pyinstaller, inno-setup, packaging, installer]
category: technical
type: guide
status: active
---

# Apollo Data Auditor - Windows Build & Packaging

## Prerequisites

### Build Machine (Windows x64 or cross-compile from Mac)

```powershell
# Python 3.12+ (x64)
pip install pyinstaller

# Inno Setup 6.x (for installer)
# Download from: https://jrsoftware.org/isinfo.php
```

### Rust Module (cross-compile from Mac)

```bash
# On Mac:
cargo install cargo-xwin
cd apollo_io_native
PYO3_CROSS_LIB_DIR=/path/to/python312.lib \
  cargo xwin build --release --target x86_64-pc-windows-msvc
# Output: target/x86_64-pc-windows-msvc/release/apollo_io_native.pyd
```

## Build

### Option 1: Build on Windows

```cmd
cd agent\packaging\windows
build_windows.bat
```

### Option 2: Build via Python

```bash
cd agent/packaging/windows
python build_windows.py [--test]
```

### Option 3: Makefile

```bash
cd agent/packaging
make build-windows
```

## Output

```
dist/
  apollo-agent.exe    (~20-50 MB, standalone, no Python required)
```

## Installer

After building the binary:

```bash
cd agent/packaging/windows
iscc installer.iss
```

Output: `output/APOLLO_DataAuditor_Setup_1.7.R_x64.exe`

### Installer Features

- GUI wizard (French/English)
- API key configuration page
- Hub URL configuration (pre-filled with production)
- Optional Windows service registration
- Desktop shortcut
- Clean uninstaller (Add/Remove Programs)
- Configuration saved to `C:\ProgramData\Apollo\config.json`

### Silent Install

```cmd
APOLLO_DataAuditor_Setup_1.7.R_x64.exe /SILENT /API_KEY=clientname_xxx
```

## Code Signing (Production)

```powershell
# Sign the binary
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\apollo-agent.exe

# Sign the installer
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com output\APOLLO_DataAuditor_Setup_1.7.R_x64.exe
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| PyInstaller build fails | Check `pip install pyinstaller` |
| Missing modules | Add `--include-module=xxx` to build script |
| Large binary size | Normal (20-50 MB). Use `--onefile` for single file. |
| SmartScreen alert | See `agent/packaging/DEBLOCAGE_OS.md` — procedure complete |
| Antivirus faux positif | See `agent/packaging/DEBLOCAGE_OS.md` — exclusions antivirus |
| PyO3 module not found | Copy `.pyd` to `dist/` manually if not auto-included |

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
