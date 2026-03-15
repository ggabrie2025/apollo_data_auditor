# =============================================================================
# Apollo Agent V1.7.R - Build System
# =============================================================================
#
# macOS: build local (PyInstaller)
# Windows/Linux: GitHub Actions (voir GITHUB_ACTIONS_BUILD.md)
#
# Usage:
#     make build-macos      Build macOS binary (PyInstaller, local)
#     make clean            Remove local build artifacts
#
# Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
# =============================================================================

.PHONY: build-macos clean help

SHELL := /bin/bash

help:
	@echo "Apollo Agent Build System"
	@echo ""
	@echo "  make build-macos      Build macOS binary (PyInstaller, local)"
	@echo "  make clean            Remove local build artifacts"
	@echo ""
	@echo "  Windows/Linux: built via GitHub Actions (tag v* or workflow_dispatch)"
	@echo "  See: GITHUB_ACTIONS_BUILD.md"

build-macos:
	@echo "=== Building macOS binary (PyInstaller) ==="
	cd macos && bash build_macos.sh

clean:
	@echo "=== Cleaning local build artifacts ==="
	rm -rf macos/dist macos/build
	@echo "Clean complete."
