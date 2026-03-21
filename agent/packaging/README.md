---
title: "Build & Packaging - Apollo Data Auditor (Overview)"
agent: rails-executor
project_id: PRJ-APOLLO
date: 2026-03-15
tags: [packaging, build, pyinstaller, github-actions, cross-platform]
category: technical
type: guide
status: active
---

# Apollo Data Auditor - Packaging Overview

Build system for producing standalone agent binaries for all platforms.

## Compilateur : PyInstaller (SEUL AUTORISE)

**Nuitka = ABANDONNE** (decision definitive, Sprint 117). PyInstaller = seul outil de packaging.

## Architecture de build

```
macOS (arm64)     -> PyInstaller LOCAL (ce Mac)
Windows (x64)     -> PyInstaller via GitHub Actions (windows-latest)
Linux (x64)       -> PyInstaller via GitHub Actions (ubuntu-latest)
```

**Pourquoi macOS en local ?**
- On a la machine Apple Silicon
- Le build fonctionne directement (`pyinstaller agent/packaging/macos/apollo_agent.spec`)
- Pas besoin de CI pour ca

**Pourquoi Windows/Linux en CI ?**
- VM UTM sur Mac ARM = binaires ARM, pas x86_64 (18h perdues sur 3 sessions)
- GitHub Actions fournit des runners x64 natifs gratuitement

## Structure

```
agent/packaging/
  Makefile              Build macOS (seul OS local)
  README.md             This file
  DEBLOCAGE_OS.md       Guide deblocage Gatekeeper/SmartScreen
  GITHUB_ACTIONS_BUILD.md   Migration CI/CD, checklist pre-push
  windows/
    apollo_agent_win.spec   Spec PyInstaller Windows (utilise par GH Actions)
    installer.iss           Inno Setup installer definition
    README.md               Windows build guide
  linux/
    build_linux.sh          Build script Linux
    install.sh              Automated installer (systemd)
    README.md               Linux build guide
  macos/
    apollo_agent.spec       Spec PyInstaller macOS (build local)
    build_macos.sh          Build script macOS
    README.md               macOS build guide
```

## Build macOS (local)

```bash
cd ~/projet_apollo_data_auditor_rust-modules
pyinstaller agent/packaging/macos/apollo_agent.spec --clean --noconfirm
# Binaire: dist/apollo-agent
```

## Build Windows + Linux (GitHub Actions)

Le workflow `.github/workflows/build-agent.yml` dans `~/github_push/` :
- Se declenche sur tag `v*` ou manuellement (workflow_dispatch)
- Compile le module Rust (maturin) + PyInstaller sur chaque OS
- Produit des artifacts telechargeables + SHA256SUMS.txt

Voir `GITHUB_ACTIONS_BUILD.md` pour les details et la checklist pre-push.

## Platform Matrix

| Platform | Build Tool | Build Location | Spec |
|----------|-----------|----------------|------|
| **macOS arm64** | PyInstaller | **Local** (ce Mac) | `macos/apollo_agent.spec` |
| **Windows x64** | PyInstaller | **GitHub Actions** | `windows/apollo_agent_win.spec` |
| **Linux x64** | PyInstaller | **GitHub Actions** | `linux/apollo_agent_linux.spec` |

## Rust Module (apollo_io_native)

Chaque plateforme a besoin du module Rust PyO3 compile nativement :

| Platform | Output | Build |
|----------|--------|-------|
| macOS | `apollo_io_native.so` | `maturin develop --release` (local) |
| Windows | `apollo_io_native.pyd` | maturin dans GH Actions |
| Linux | `apollo_io_native.so` | maturin dans GH Actions |

## Client Experience

Le client recoit un seul binaire. Pas besoin de Python, Rust, ou outils de build.

- **Windows**: `apollo-agent.exe` (ou installateur Inno Setup)
- **Linux**: `apollo-agent` + `install.sh` (systemd)
- **macOS**: `apollo-agent-macos` + `install_macos.sh`

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
