# CHANGELOG — Apollo Data Auditor

## [1.7.R-patch15] — 2026-03-26

### Fixed
- KI-128: tables_scanned=0 — add default assignment before differential branch.
  Full scan mode now sets tables_scanned=len(tables) before the differential
  override block. Previously always 0 in non-differential mode.
- KI-129: total_size_bytes=null — aggregate sum(size_bytes) from scanned tables.
  size_values list comprehension skips None entries; result is None only if all
  tables have no size_bytes data.

## [1.7.R-patch13] — 2026-03-20

### Fixed
- KI-103: db_scanner._detect_pii() double-counting — add `break` after first valid
  PII match per cell value. Prevents French IBAN from generating 'iban' + 'iban_fr',
  and ITIN from generating 'ssn_us' + 'itin_us'. One type per cell value.

## [1.7.R-patch12] — 2026-03-20

### Added
- KI-101: estimated_data_subjects — distinct identifier count (CNIL Art.33 / D195)
  Track unique identifier values (email, phone_fr, ssn_fr, ssn_us) per file in
  pii_scanner + optimized_scanner. Aggregate across all files. Add to JSON summary:
  estimated_data_subjects, data_subjects_method, data_subjects_identifiers_used,
  data_subjects_fallback. Fallback = files_with_pii when no identifiers found.
  DB/app exports: fields present with fallback=true.

### Fixed
- KI-097: normalize seen_values (strip spaces + uppercase) before dedup comparison
  prevents iban/iban_fr double-counting when values differ only by spacing.
- Parallel path metadata bug: missing 'type' key in PII entries caused crash.

## [1.7.R-patch11] — 2026-03-19

### Fixed
- PII scan (KI-080/L-006): apply elfproef (BSN NL) and mod97 (NISS BE) validators in all 3 scan
  paths. PATH B (optimized_scanner, default prod) and PATH C (db_scanner) had no validator —
  every 9-digit number was counted as Dutch BSN. All paths now apply validators consistently.

### Refactored
- PII scan (KI-080/L-011): consolidate 3 independent PII pattern dicts into single source +
  derivation. DICT-C (340 lines, dead code) deleted. DICT-B derived from DICT-A at module load.
  6 EU patterns (DNI/NIE/NIF/PESEL/CF/IBAN-SEPA) reactivated in PATH B. iban_fr added.
  Deduplication (seen_values set) in both scan paths. Net: -420 lines.

## [1.7.R-patch10] — 2026-03-18

### Fixed
- LDAP connector: warn when bind_dn uses DN format (CN=/DC=) instead of UPN
  Windows Server 2022 AD rejects SIMPLE bind with DN format (KB4520011).
  Warning logged with truncated bind_dn and explicit hint to use UPN (user@domain.local).
  Documented as KI-088. No code logic changed — config-level workaround.

## [1.7.R-patch9] — 2026-03-18

### Fixed
- Infra scan: add `--mode infra` to argparse choices + dispatch in main.py
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
