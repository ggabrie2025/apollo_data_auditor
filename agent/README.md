# APOLLO Data Auditor — Agent V1.7.R

Local scan binary for APOLLO Data Auditor. Installed on client infrastructure (Windows, Linux, macOS), it scans files, databases, cloud storage, directory services, and ERP sources — detects 44 PII types — and sends metadata counters to the APOLLO Cloud Hub. No AI. No data exfiltration. Counters only.

## Features

- **11 source connectors**: local files, NFS/SMB shares, PostgreSQL, MySQL, MongoDB, SQL Server, OneDrive, SharePoint, Active Directory/LDAP, Pennylane, infrastructure
- **44 PII types detected**: IBAN, SSN (FR/US), email, phone, passport, PESEL, BSN, NIE, NISS, codice fiscale, and 34 more (EU + US)
- **Rust I/O module** (PyO3): up to 1.16M rows/second file scan throughput
- **Zero data exfiltration**: only metadata counters transit to the Cloud Hub — raw file contents and database rows never leave client infrastructure
- **scores=None**: the binary exports raw metadata only — all scoring and analysis is performed server-side by the Cloud Hub
- **PyInstaller binary**: single executable, no Python runtime required on client machines

## Installation

### Pre-built binary (recommended)

Download `apollo-agent` (macOS/Linux) or `apollo-agent.exe` (Windows) from the [releases page](https://github.com/ggabrie2025/apollo_data_auditor/releases/latest).

Verify integrity before running:

```bash
sha256sum apollo-agent        # macOS / Linux
Get-FileHash apollo-agent.exe # Windows PowerShell
```

Compare against `SHA256SUMS.txt` from the release.

### From source

```bash
pip install -r requirements.txt
python3 -m agent.main --version
```

## Usage

```bash
# Start the local agent server (opens dashboard at http://localhost:8052)
./apollo-agent --serve

# Run a file scan directly
./apollo-agent --mode files --path /path/to/scan --output result.json

# Show version
./apollo-agent --version
```

See [DEBLOCAGE_OS.md](packaging/DEBLOCAGE_OS.md) if macOS Gatekeeper or Windows SmartScreen blocks the binary.

## Output Format

The agent produces a JSON file with raw metadata — no scores:

```json
{
  "version": "1.7.R",
  "source_type": "files",
  "scores": null,
  "summary": {
    "total_files": 48210,
    "total_size_bytes": 15728640000,
    "files_with_pii": 312,
    "pii_by_type": {"iban": 47, "email": 203, "ssn_fr": 12, "phone_fr": 50},
    "error_count": 0
  }
}
```

`scores: null` is intentional — scoring is 100% server-side.

## PII Detection

Detects 44 PII types across EU and US regulations:

| Category | Examples |
|----------|---------|
| Financial | IBAN (SEPA), IBAN-FR, bank account |
| Identity FR | NIR (SSN), passport, driving licence |
| Identity EU | BSN (NL), NISS (BE), PESEL (PL), DNI/NIE/NIF (ES), codice fiscale (IT) |
| Identity US | SSN, ITIN, EIN |
| Contact | Email, phone (FR/EU/US), mobile |
| Healthcare | NDA, patient ID patterns |

## Architecture

```
Client infrastructure                  APOLLO Cloud Hub (Railway)
┌─────────────────────────┐            ┌──────────────────────────┐
│  apollo-agent binary    │  POST      │  Cloud Hub V3            │
│  (this repo)            │ /api/v1/   │  scoring + dashboard     │
│                         │ hub/ingest │                          │
│  Scan sources           │ ─────────> │  Compute 129 scores      │
│  Detect PII (regex)     │  metadata  │  Generate PDF reports    │
│  Export JSON            │  counters  │  GDPR/CCPA exposure      │
│  scores=None            │  only      │                          │
└─────────────────────────┘            └──────────────────────────┘
```

## Building

Binaries are built via GitHub Actions CI on every tagged release:

- **Windows** — `windows-latest` runner, PyInstaller
- **Linux** — `ubuntu-latest` runner, PyInstaller
- **macOS** — local build (Apple Silicon), PyInstaller

See [GITHUB_ACTIONS_BUILD.md](packaging/GITHUB_ACTIONS_BUILD.md) for the full build procedure.

## Requirements

- Python 3.9+ (source only — not required for pre-built binary)
- Rust toolchain (source only — required to build the `apollo_io_native` module)
- macOS / Windows / Linux

## License

BSL 1.1 — see root [LICENSE](../LICENSE) file.

| Version | Release | BSL Change Date |
|---------|---------|----------------|
| 1.7.R | 2026-03-08 | 2030-01-01 |
