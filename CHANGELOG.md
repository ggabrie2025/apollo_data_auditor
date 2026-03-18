# CHANGELOG — Apollo Agent

## [1.7.R-patch9] — 2026-03-18

### Fixed
- Infra scan: add `--mode infra` dispatch in main.py (frozen binary routing)
- Infra scan: add `agent.main_infra` to mode_map in _build_scan_cmd (server.py)
- Infra scan: _silent_infra_scan now writes apollo_infra_{key_prefix}_{ts}.json
  to tempdir before Hub send — payload survives quota errors / network failures.
  File cleaned up on successful Hub ingest. Path logged if send fails.

## [1.7.R-patch8] — 2026-03-18

### Fixed
- Windows: detect NTFS junction point loops in _walk_directory
  os.walk(followlinks=False) does not detect junction points as symlinks — AppData\Local
  junctions looped back creating 21 phantom files per real file (max_depth=15 cap hit).
  Fix: track resolved canonical paths via seen_real_paths set.

## [1.7.R-patch5] — 2026-03-18

### Changed
- Exclusions: browser AppData paths excluded by default (Edge, Chrome, Firefox, Brave)
  Prevents false PII positives from minified JS files in Windows AppData

## [1.7.R-patch4] — 2026-03-17

### Fixed
- LDAP/AD connector: fallback NTLM -> SIMPLE bind for Active Directory Windows (KB4520011)
- ldap3 + pyasn1 added to requirements.txt and PyInstaller hidden-imports

## [1.7.R-patch1] — 2026-03-15

### Fixed
- Force UTF-8 encoding on Windows stdout/stderr — prevents CP1252 crash on Unicode characters (arrows, accented paths)

### Changed
- Purged all Nuitka references from build docs — PyInstaller is the only authorized build tool
- Build docs now clarify: macOS = local PyInstaller, Windows/Linux = GitHub Actions
- Makefile simplified: only `build-macos` target (Windows/Linux via CI)
- Added 8-step pre-push checklist in GITHUB_ACTIONS_BUILD.md

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
