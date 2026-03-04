# Apollo Agent V1.6 - Agent Leger

Standalone file scanner for Apollo Data Auditor. Scans file systems for metadata and PII detection, exports JSON for Hub Cloud consolidation.

## Features

- Pure Python stdlib (single dependency: PyYAML)
- File metadata collection via `os.walk`
- PII detection: email, phone_fr, iban, ssn_fr
- Configurable exclusions (extensions, paths, patterns)
- JSON export compatible with Hub Cloud API
- PyInstaller binary packaging (3.6MB)

## Installation

### From Source

```bash
cd agent
pip install -r requirements.txt

# Run directly
python3 -m agent.main --version
```

### Pre-built Binary (macOS)

```bash
# Download from releases
./apollo-agent --version
```

## Usage

### Preview Mode (Dry Run)

```bash
# Show what would be scanned without scanning
python3 -m agent.main /path/to/scan --preview
```

### Full Scan

```bash
# Scan with PII detection, output to JSON
python3 -m agent.main /path/to/scan -o output.json

# Scan without PII detection (faster)
python3 -m agent.main /path/to/scan --no-pii -o output.json

# Pretty-print JSON output
python3 -m agent.main /path/to/scan -o output.json --pretty
```

### Options

| Option | Description |
|--------|-------------|
| `--version` | Show version (v1.6.0) |
| `--preview` | Dry run - show config and stats |
| `-o, --output FILE` | Output JSON file path |
| `--no-pii` | Skip PII scanning (faster) |
| `--include-network-mounts` | Include NFS/SMB mounts (excluded by default) |
| `-v, --verbose` | Show detailed progress |

## Output Format

```json
{
  "version": "1.6.0",
  "scan_id": "uuid",
  "timestamp": "2025-12-11T16:50:05Z",
  "source_path": "/scanned/path",
  "summary": {
    "total_files": 10,
    "total_size_bytes": 43361,
    "files_with_pii": 1,
    "pii_by_type": {"email": 1},
    "excluded_count": 2,
    "error_count": 0
  },
  "files": [...],
  "config_used": {...}
}
```

## PII Detection

Detects 4 French-focused PII patterns:

| Type | Pattern | Example |
|------|---------|---------|
| `email` | RFC 5322 | user@domain.com |
| `phone_fr` | French mobile/landline | +33 6 12 34 56 78 |
| `iban` | Bank account number | FR76 3000 6000 0112 3456 7890 189 |
| `ssn_fr` | NIR (Securite Sociale) | 1 85 12 75 108 123 45 |

## Exclusions

Default exclusions in `config/exclusions.yaml`:

- **30 extensions**: .exe, .dll, .sys, .tmp, .log, .cache, etc.
- **40 path patterns**: node_modules, .git, __pycache__, build, dist, etc.
- **Size limits**: min 10 bytes, max 100MB

## Architecture

```
agent/
├── core/
│   ├── collector.py      # os.walk file traversal
│   ├── exclusions.py     # YAML config loader
│   ├── pii_scanner.py    # Regex PII detection
│   └── exporter.py       # JSON export
├── config/
│   └── exclusions.yaml   # Exclusion rules
├── models/
│   └── contracts.py      # Dataclasses
├── main.py               # CLI entry point
├── requirements.txt      # PyYAML only
└── packaging/
    ├── apollo_agent.spec # PyInstaller config
    └── build_macos.sh    # Build script
```

## Building Binary

### macOS

```bash
cd agent/packaging
./build_macos.sh

# Output:
# - dist/apollo-agent (3.6MB CLI)
# - dist/Apollo Agent.app (3.7MB bundle)
```

### Windows (Requires Windows machine)

```bash
cd agent/packaging
pyinstaller apollo_agent.spec
```

## Integration with Hub Cloud

The agent exports JSON that Hub Cloud V1.4 will consume:

```
Agent V1.6 (client)         Hub Cloud V1.4 (server)
┌─────────────────┐         ┌─────────────────┐
│ Scan files      │         │ Receive JSON    │
│ Detect PII      │ ──JSON──│ Consolidate     │
│ Export JSON     │         │ Score           │
└─────────────────┘         │ Dashboard       │
                            └─────────────────┘
```

## Requirements

- Python 3.9+ (uses `from __future__ import annotations`)
- PyYAML >= 6.0
- macOS / Windows / Linux

## License

Proprietary - AIIA Tech

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.6.0 | 2025-12-28 | Network mount exclusion, STOP/RESET, Hub connection indicator |
| 1.5.0 | 2025-12-23 | Fingerprint, Dedup, SmartSampler, Differential, Multi-source |
| 1.3.0 | 2025-12-11 | Initial release - files only agent |
