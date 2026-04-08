# APOLLO™ Data Auditor — Every file is a risk. Measure it.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
[![Beta](https://img.shields.io/badge/Status-Beta-orange.svg)]()
[![Website](https://img.shields.io/badge/Website-apollo.aiia--tech.com-blue.svg)](https://apollo.aiia-tech.com)

APOLLO™ Data Auditor is a local-first data risk audit tool for SMBs and mid-market companies. It scans files, databases, and cloud storage — and returns your financial exposure in € and $ under GDPR and CCPA. Not an abstract score. A number your CFO and your DPO can act on.

**What it does:**
- Scans 11 sources: PostgreSQL, MySQL, MongoDB, SQL Server, OneDrive, SharePoint, Active Directory/LDAP, Pennylane (ERP), local files, NFS/SMB shares
- Detects 44 PII types automatically
- Produces 129 scores across 4 modules: Risk Exposure, Compliance, Data Protection, Intelligence (AI Readiness)
- Identifies toxic PII combinations, simulates breach scenarios, evaluates cyber insurance readiness
- Up to 1.16M rows/sec with our native Rust agent

**Zero data exfiltration** — your data never leaves your infrastructure. Only metadata and counters transit to the cloud hub.

**4 modules, 4 audiences:**
- **Risk Exposure** — for DPOs, executives, CFOs
- **Compliance** — for DPOs, auditors, CISOs (GDPR, CCPA, NIS2, SOC2, DORA)
- **Data Protection** — for infra leads, backup admins (breach simulation, ransomware scenarios)
- **Intelligence** — for CDOs, CTOs (AI Readiness, data quality, AI Act pre-compliance)

Deployed in minutes. Not weeks. No consultant needed. Pricing starts at €0 (free tier) up to €4,999/year.

![APOLLO Demo](assets/teaser_readme.gif)

**[Watch the demo on YouTube →](https://youtu.be/gwu6BGKkbag)**

---

## Architecture

```
Agent (on-premise, pure collector)  →  Apollo Cloud Hub  →  Risk scores · Compliance dashboard
```

The agent sends counters and metadata only — never PII values. Raw data never leaves your infrastructure.

---

## 🎯 The Problem

SMEs hold thousands of files, databases, and cloud documents containing personal data. Without knowing. Without protecting them.

- **GDPR fines:** up to 4% of global revenue or €20M
- **CCPA penalties:** $7,988 per violation, no cure period
- **Average SME breach cost:** $3.31M (IBM/Ponemon 2025)

Enterprise solutions exist — at $50K–$150K/year. For a 50–500 employee company, that's not an option.

**APOLLO changes that.**

---

## ⚡ Quick Start

### 1. Download

Go to **[Releases](https://github.com/ggabrie2025/apollo_data_auditor/releases/latest)** and download the binary for your OS:

| OS | File |
|----|------|
| Windows | `apollo-agent.exe` |
| Linux | `apollo-agent` |
| macOS | `apollo-agent-macos` |

### 2. Launch

**Windows** — Open PowerShell in the download folder and run:
```powershell
.\apollo-agent.exe --serve
```

**Linux / macOS** — Open a terminal and run:
```bash
chmod +x ./apollo-agent
./apollo-agent --serve
```

> The browser opens automatically on `http://localhost:8052`

### 3. Use

Enter your API key and start scanning. Get your API key at [apollo.aiia-tech.com](https://apollo.aiia-tech.com).

---

## ⚠️ Windows Troubleshooting

### The window opens and closes immediately

Windows blocks executables downloaded from the internet. Use one of these methods:

**Option 1 — PowerShell (as administrator):**
```powershell
Unblock-File .\apollo-agent.exe
.\apollo-agent.exe --serve
```

**Option 2 — File Explorer:**
Right-click `apollo-agent.exe` → **Properties** → check **Unblock** at the bottom → OK

**Option 3 — SmartScreen popup:**
If a blue SmartScreen dialog appears → click **More info** → **Run anyway**

### I don't see the error message (window closes too fast)

Open PowerShell **first**, then run the command from inside it — the window stays open and shows the error.

### The browser does not open automatically

Navigate manually to `http://localhost:8052` in your browser. The server is running even if the browser did not open.

---

## 🔌 Connectors

| Source | Status | Types |
|--------|--------|-------|
| **Files** | ✅ | Local, NFS, SMB |
| **Database** | ✅ | PostgreSQL, MySQL, MongoDB, SQL Server |
| **Cloud** | ✅ | OneDrive, SharePoint |
| **Directory** | ✅ | Active Directory, LDAP |
| **ERP** | ✅ | Pennylane (more coming) |
| **Infrastructure** | ✅ | Hardware, OS, Backup, SMART |

**44 PII types** detected automatically across all sources.

---

## 📊 What You Get

### 6 Dashboard Modules

| Module | For | What It Shows |
|--------|-----|---------------|
| **Executive** | CEO, CFO | Global score, trajectory, top risks |
| **Risk Exposure** | CEO, CFO, Consultant | Financial exposure (€/$), Breach Theater simulation |
| **Compliance** | DPO, Legal, CISO | GDPR Art.9/30/32, NIS2, SOC2, CCPA, AI Act |
| **Data Protection** | MSP, Backup, IT | Backup resilience, encryption, data hygiene |
| **Intelligence** | CTO, ESN, AI Integrator | AI Readiness, data quality, blockers |
| **Scoreboard** | Auditor, Consultant | 71 scores, 319 metrics — full registry |

All values computed from your actual scan. Zero hardcoded constants.

---

## 🛡️ Security

- **Zero data exfiltration** — PII never leaves your infrastructure
- **Native Rust agent** — No dependencies, no server
- **Cloud scoring only** — Anonymized metadata sent to scoring engine
- **TLS 1.3 encryption** — All data in transit
- **GDPR compliant** — By design

---

## 📈 Performance

- Up to **1.16M rows/second** scan rate
- Full audit in **< 48 hours** (vs 3-6 months traditional)
- Unlimited re-scans included

---

## 🆓 Free Beta Access

**50 places available**

| Feature | Beta |
|---------|------|
| Sources | 5 |
| Scans | 25 |
| Price | €0 |

No credit card. No commitment.

**[Request Beta Access](https://apollo.aiia-tech.com)** or email contact@aiia-tech.com

---

## 📋 Requirements

- **Windows** 10/11 or **Linux** (Ubuntu 20.04+, Debian 11+)
- **macOS** 12+ (Apple Silicon & Intel)
- 4GB RAM minimum
- Network access to your data sources

---

## 📖 Documentation

- [APOLLO Website](https://apollo.aiia-tech.com)
- [Installation Guide](install.sh) (Linux) | [macOS](install_macos.sh) | [Windows](install_windows.ps1)
- [Security Policy](SECURITY.md)
- [Third-Party Licenses](THIRD_PARTY_LICENSES.md)

---

## 🤝 Support

- **Email:** contact@aiia-tech.com
- **Issues:** [GitHub Issues](https://github.com/ggabrie2025/apollo_data_auditor/issues)

---

## 📜 License

[Business Source License 1.1](LICENSE)

- ✅ Non-commercial use permitted
- ✅ Internal business use permitted
- ❌ Commercial redistribution requires license
- 📅 Change Date: 2030 → Apache 2.0

---

## 🏢 About

APOLLO Data Auditor is built by [aiia-tech.com](https://aiia-tech.com), founded by MIT Sloan Executive Program alumni.

- [apollo.aiia-tech.com](https://apollo.aiia-tech.com) — Product page
- [aiia-tech.com](https://aiia-tech.com) — Company

**Vision:** Democratize enterprise-grade data auditing for European SMEs.

---

© 2025-2026 aiia-tech.com — APOLLO™ is a registered trademark.
