# =============================================================================
# Apollo Agent V1.7.R - Unified Build System
# =============================================================================
#
# Usage:
#     make build-windows    Build Windows binary (Nuitka)
#     make build-linux      Build Linux binary (Nuitka)
#     make build-macos      Build macOS binary (Nuitka or PyInstaller)
#     make installer-win    Build Windows installer (Inno Setup)
#     make clean            Remove all build artifacts
#
# Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
# =============================================================================

.PHONY: build-windows build-linux build-macos installer-win clean help

SHELL := /bin/bash

help:
	@echo "Apollo Agent Build System"
	@echo ""
	@echo "  make build-windows    Build Windows binary (Nuitka)"
	@echo "  make build-linux      Build Linux binary (Nuitka)"
	@echo "  make build-macos      Build macOS binary (PyInstaller legacy)"
	@echo "  make installer-win    Build Windows installer (Inno Setup)"
	@echo "  make clean            Remove all build artifacts"

build-windows:
	@echo "=== Building Windows binary ==="
	cd windows && python build_windows.py

build-linux:
	@echo "=== Building Linux binary ==="
	cd linux && bash build_linux.sh

build-macos:
	@echo "=== Building macOS binary (PyInstaller legacy) ==="
	cd macos && bash build_macos.sh

installer-win:
	@echo "=== Building Windows installer (Inno Setup) ==="
	@command -v iscc >/dev/null 2>&1 || { echo "Inno Setup (iscc) not found."; exit 1; }
	cd windows && iscc installer.iss

clean:
	@echo "=== Cleaning all build artifacts ==="
	rm -rf windows/dist windows/build windows/output
	rm -rf linux/dist linux/build
	rm -rf macos/dist macos/build
	@echo "Clean complete."
