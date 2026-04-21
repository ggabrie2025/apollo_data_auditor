# CHANGELOG — Apollo Data Auditor

## [1.7.R-patch24] — 2026-04-22

### Fixed
- pyo3 upgraded 0.22 → 0.24: migrate `new_bound()` → `new()` API (9 occurrences
  across fingerprint.rs, raw_collector.rs, reader.rs, platform.rs).
  Closes Dependabot alert #1 (LOW). KI-203 resolved.

---

## [1.7.R-patch23] — 2026-04-20

### Docs
- agent/README.md: full rewrite — V1.7.R, BSL 1.1, 44 PII types, 11 connectors,
  correct description as local scan binary (not an AI agent), Cloud Hub V3 architecture
- agent/packaging/DEBLOCAGE_OS.md: branding "Apollo Agent" → "APOLLO Data Auditor" throughout
- apollo_io_native/README.md: license corrected MIT → BSL 1.1 (covered by root LICENSE)

---

## [cloud-2026-04] — 2026-04-15

> Cloud Hub — Dashboard & Scoring. All features below were driven by alpha tester feedback.

### Performance
> *"The dashboard is slow to load after a multi-source scan."*
- Redis cache layer: dashboard responses served from cache — 3–5× faster load after first scan
- 8 gunicorn workers in parallel for concurrent ingests during beta

### US Compliance
> *"We operate in the US — CCPA doesn't cover our state-by-state obligations."*
- US Multi-State Privacy Landscape: 50-state table with revenue-based thresholds and cure period per state
- CCPA framework panel in Executive tab (US mode)
- Corrective actions tagged `article_us` in recommendations

### Insurance Readiness V2
> *"Our broker needs a cyber insurance readiness assessment before renewal."*
- 8 cyber insurance controls scored and graded (backend + dashboard)
- Declarative questionnaire: IRP, coverage, deductible, exclusions
- Insurance Readiness section in Executive PDF export

### What-If Engine
> *"We want to see what changes concretely if we fix a specific gap."*
- Exact GDPR/CCPA penalty recalculation per selected corrective action
- Breach cost projection with CEO-facing scenarios
- Available across 4 tabs: Executive, Risk, Compliance, Intelligence

### Cross-Source Correlations (SCI)
> *"Risks are shown source by source — we don't see the connections between them."*
- SCI cascade badge on priority actions — shows which actions unlock multiple risk reductions
- New APP↔FILES correlation: shadow data detection across ERP and file systems

### JSON Export
> *"We want to integrate results into our internal tools."*
- Full dashboard export via `exportAllTabsJSON()`: all 6 tabs consolidated with client metadata in a single file

---

## [1.7.R-patch22] — 2026-04-08

### Changed
- Beta operational limits raised for real PME environments:
  max_files 100K → 500K (NAS 200-300K files),
  PII scan max_size 10MB → 50MB (ERP CSV exports),
  file read buffer 64KB → 256KB (PII detection in large headers),
  OneDrive max_file_size 100MB → 500MB (SharePoint archives),
  DB scan timeout 30s → 60s (VPN latency).

## [1.7.R-patch21] — 2026-04-04

### Changed
- Sprint 151: Agent UI Redesign — sidebar navigation, toast notifications,
  message slots system. Improved layout consistency across scan views.
- hub-link-section fixed bottom: Stop Scan + Reset Dashboard buttons always
  visible regardless of scroll position.
- Footer unified: single fixed bar with stop/reset buttons + copyright.

## [1.7.R-patch20] — 2026-03-26

### Fixed
- KI-119: ram_total_bytes=0 instead of null when psutil absent — init
  ram_total/ram_available to None (was 0). ImportError now emits JSON null
  for D180/D181. Same fix for disk OSError fallback D184/D185.

## [1.7.R-patch19] — 2026-03-26

### Fixed
- KI-118: MongoDB completeness_score=0.0, zone=null, sample_rate=null — wire
  _compute_quality_metrics + smart_sampler into MongoDB branch of _extract_schema.
  New elif mongodb in _compute_quality_metrics: motor aggregate pipeline
  $group/$sum/$cond/$ifNull to compute null_pcts per field (guard <= 100K docs).
  MongoDB collections now report real completeness_score, zone, sample_rate.

## [1.7.R-patch18] — 2026-03-26

### Changed
- Beta period: all connectors unlocked for all tiers (Sprint 115 L2).
  DB and Cloud scan buttons no longer locked for free tier during beta.

### Docs
- VM_BUILD_PROCEDURE.md: add patch13 validation results (9 Windows + 8 Linux
  connectors, 102 PASS / 0 FAIL E2E on 2026-03-20).

## [1.7.R-patch17] — 2026-03-26

### Fixed
- F5: add logger.warning to all 6 except blocks in get_governance_metrics().
  Silent exception swallowing replaced with named exception + warning log.
  Pattern: [governance/<metric>] <command> failed: <error>

## [1.7.R-patch16] — 2026-03-26

### Fixed
- KI-130: governance_metrics=null for MongoDB — implement get_governance_metrics()
  in MongoDBConnector. 6 MongoDB-native KPIs: documentation_coverage (JSON Schema
  validators), security_compliance (usersInfo root roles), access_control (read-only
  users ratio), change_tracking (replica set hello command), table_size_distribution
  (1-CV of collStats storageSize), ai_act_article11 (ML collection name heuristic).
  hasattr() guard at db_scanner.py:296 now activates automatically for MongoDB.

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
