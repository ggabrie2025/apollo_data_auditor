[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](./LICENSE)

# Apollo Data Auditor — Agent V1.7.R

Native Rust agent for data audit and GDPR/CCPA exposure assessment.
Scans files, databases, cloud storage and directory sources — sends anonymized metadata to Apollo Cloud Hub for scoring and compliance dashboard.

## Architecture

```
Agent (on-premise, pure collector)  →  Apollo Cloud Hub  →  Risk scores · Compliance dashboard
```

The agent sends counters and metadata only — never PII values. Raw data never leaves your infrastructure.

## Free Beta Access

The agent is open source. Cloud scoring (dashboard + GDPR exposure) requires a cloud account.

**First 50 beta testers get free Starter access** (unlimited scans, up to 5 sources).

Supported connectors: Files/NAS · PostgreSQL · MySQL · MongoDB · SQL Server · LDAP/Active Directory · SharePoint/OneDrive · ERP (Pennylane)

→ Apply: contact@aiia-tech.com
   Subject: "Apollo Beta Access"
   Include: your OS, infrastructure type, connectors you want to test

## Download

Pre-built binaries available in [Releases](../../releases).

| OS | Binary |
|----|--------|
| Linux (Ubuntu 24.04+) | `apollo-agent` |
| Windows | `apollo-agent.exe` |
| macOS (15.0+ arm64) | `apollo-agent-macos` |

## Quick Start

```bash
# Linux / macOS
./apollo-agent --serve

# Windows (PowerShell)
.\apollo-agent.exe --serve
```

Open http://localhost:8052 in your browser, enter your API key, and start scanning.

```bash
# Other commands
apollo-agent --version          # Show version
apollo-agent --help             # Full CLI options
apollo-agent /path/to/scan      # Direct FILES scan (CLI mode)
```

## Security & Privacy

APOLLO™ Data Auditor scanne vos données localement. Aucune valeur PII ne quitte votre infrastructure. See our full **[Data Privacy & Security Statement](./DATA_PRIVACY.md)**.

## License

Apollo Agent is licensed under the **Business Source License 1.1 (BSL 1.1)**.

- **Free for non-commercial use** — personal, research, evaluation
- **Commercial use requires a separate license**
- **Converts to Apache 2.0** on 2030-01-01 (or 4 years after each version's release, whichever is earlier)

For commercial licensing: contact@aiia-tech.com

> This is **not** an open-source license. It is a *source-available* license.
> See [LICENSE](./LICENSE) for full terms.
