# CHANGELOG — Apollo Agent

## [1.7.R] — 2026-03-10

### Added
- Installers for macOS (`install_macos.sh`) and Windows (`install_windows.ps1`)
- SHA256 integrity verification on all installers (abort on mismatch)
- Distribution exclusively via aiia-tech.com/download
- BSL 1.1 v2 license with NOTICE, CLA, third-party licenses
- Beta tester guide (APOLLO_Beta_Guide_2026.docx)
- Full product README with connectors, dashboard modules, security details

### Fixed
- Frozen binary subprocess routing via `--mode` flag (PyInstaller)
- Complete frozen binary fix for FILES + OneDrive + asyncpg connectors
- Infrastructure scan now runs automatically at login (was only triggered after FILES scan)

### Changed
- macOS installer: native arm64 (Apple Silicon) — removed Rosetta 2 requirement
- DOWNLOAD_BASE configurable via env var for testing

## Versioning & BSL Change Dates

| Version | Release Date | BSL Change Date (earliest of fixed date or +4 years) |
|---------|-------------|------------------------------------------------------|
| 1.7.R   | 2026-03-08  | 2030-01-01 (fixed) OR 2030-03-08 (4 years) — 2030-01-01 applies |
| 0.1.0   | 2025-06-01  | 2029-06-01 (4 years from release) OR 2030-01-01 — 2029-06-01 applies |

> Per BSL 1.1: each version converts to Apache 2.0 on whichever date comes first —
> the fixed Change Date (2030-01-01) or 4 years after that version's first public release.
