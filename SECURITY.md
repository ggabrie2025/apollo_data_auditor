---
title: "Security Policy — Apollo Data Auditor"
agent: redactor
project_id: PRJ-APOLLO
date: 2026-03-07
tags: [security, integrity, sha256, distribution]
category: technical
type: guide
status: active
---

# Security Policy — Apollo Data Auditor

## Distribution officielle

**Les binaires Apollo Data Auditor sont distribues exclusivement via :**

> **https://aiia-tech.com/download**

Ne pas telecharger de binaires Apollo Data Auditor depuis d'autres sources (GitHub Releases, mirrors, torrents).
Tout binaire obtenu hors de ce canal est non verifie et potentiellement compromis.

---

## Verrou 1 — Checksum SHA256 (publie par aiia-tech.com)

Chaque release publie un fichier `SHA256SUMS.txt` signe sur `https://aiia-tech.com/download/SHA256SUMS.txt`.

Ce fichier est genere automatiquement par le pipeline CI (GitHub Actions) apres chaque build PyInstaller,
puis deploye manuellement sur le serveur de distribution en meme temps que les binaires.

### Verification manuelle avant execution

```bash
# Linux
EXPECTED=$(curl -sSL https://aiia-tech.com/download/SHA256SUMS.txt | grep "apollo-agent$" | awk '{print $1}')
ACTUAL=$(sha256sum ./apollo-agent | awk '{print $1}')
[ "$EXPECTED" = "$ACTUAL" ] && echo "OK" || echo "MISMATCH — do not execute"

# macOS
EXPECTED=$(curl -sSL https://aiia-tech.com/download/SHA256SUMS.txt | grep "apollo-agent-macos$" | awk '{print $1}')
ACTUAL=$(shasum -a 256 ./apollo-agent-macos | awk '{print $1}')
[ "$EXPECTED" = "$ACTUAL" ] && echo "OK" || echo "MISMATCH — do not execute"

# Windows (PowerShell)
$expected = (Invoke-WebRequest https://aiia-tech.com/download/SHA256SUMS.txt).Content `
  | Select-String "apollo-agent.exe" | ForEach-Object { $_ -split '\s+' | Select-Object -First 1 }
$actual = (Get-FileHash .\apollo-agent.exe -Algorithm SHA256).Hash.ToLower()
if ($expected -eq $actual) { "OK" } else { "MISMATCH - do not execute" }
```

---

## Verrou 2 — Verification automatique via install.sh

Le script `install.sh` integre la verification SHA256 avant toute installation :

```bash
curl -sSL https://aiia-tech.com/download/install.sh | bash
```

Comportement :
- Telecharge le binaire depuis `aiia-tech.com/download/apollo-agent`
- Telecharge `SHA256SUMS.txt` depuis `aiia-tech.com/download/SHA256SUMS.txt`
- Compare les hashes — si mismatch :

```
======================================================
  BINARY INTEGRITY CHECK FAILED
  Do not execute this binary.
  Contact: contact@aiia-tech.com
======================================================
```

- Si OK : installe dans `/opt/apollo-agent/` et cree le symlink `/usr/local/bin/apollo-agent`

Pour installer sans verification (non recommande) :

```bash
curl -sSL https://aiia-tech.com/download/install.sh | bash -s -- --no-verify
```

---

## Signaler un binaire suspect

Si vous pensez avoir telecharge un binaire corrompu ou altere :

1. **Ne pas executer le binaire**
2. Calculer son SHA256 :
   - Linux/macOS : `sha256sum apollo-agent` ou `shasum -a 256 apollo-agent-macos`
   - Windows : `Get-FileHash apollo-agent.exe -Algorithm SHA256`
3. Comparer avec `SHA256SUMS.txt` de `https://aiia-tech.com/download/SHA256SUMS.txt`
4. Contacter : **contact@aiia-tech.com**
   - Objet : `[SECURITY] Suspect binary - Apollo Data Auditor vX.Y.Z`
   - Inclure : SHA256 du binaire, OS, source de telechargement

---

## Politique de divulgation

- Reponse sous **48h** aux signalements de securite
- Divulgation responsable : **90 jours** avant publication publique
- Contact : contact@aiia-tech.com

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.7.R   | Yes       |
| < 1.7   | No        |

---

**Copyright**: (c) 2025-2026 Gilles Gabriel / aiia-tech.com
