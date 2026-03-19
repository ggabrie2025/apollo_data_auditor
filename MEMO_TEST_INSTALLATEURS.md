---
title: "Memo — Test local installateurs Apollo Agent v1.7.R"
agent: redactor
project_id: PRJ-APOLLO
date: 2026-03-19
tags: [installateur, test, binaire, distribution]
category: technical
type: note
status: active
---

# Memo — Test local installateurs Apollo Agent v1.7.R

## Organisation des repertoires

### 1. Repo GitHub Push (`~/github_push`)

Code source + scripts d'installation. C'est ce qui est pousse sur GitHub.

```
~/github_push/
  install.sh              ← installateur Linux
  install_macos.sh        ← installateur macOS
  install_windows.ps1     ← installateur Windows
  agent/                  ← code source agent Python
    packaging/
      macos/dist/         ← build PyInstaller local (apollo-agent)
      linux/              ← build CI (pas de dist/ local)
      windows/            ← build CI (pas de dist/ local)
```

### 2. Repo Agent Rust (`~/projet_apollo_data_auditor_rust-modules`)

Repo de developpement local. Contient les releases finales organisees par OS.

```
~/projet_apollo_data_auditor_rust-modules/
  releases/v1.7.R/
    macos/apollo-agent-macos     ← binaire VALIDE (arm64 natif, build local PyInstaller)
    linux/apollo-agent           ← binaire CI (telecharger depuis GH Actions artifacts)
    windows/apollo-agent.exe     ← binaire CI (telecharger depuis GH Actions artifacts)
```

> **Note (2026-03-19)** : Linux et Windows sont buildés par GitHub Actions sur tag. Telecharger via :
> `gh run download $RUN_ID --repo ggabrie2025/apollo_data_auditor -n apollo-agent-ubuntu-latest -D /tmp/patch_linux`
> `gh run download $RUN_ID --repo ggabrie2025/apollo_data_auditor -n apollo-agent-windows-latest -D /tmp/patch_win`

### 3. Hostinger (`aiia-tech.com/download/`) — structure cible finale

Dossier PLAT — tous les fichiers au meme niveau :

```
aiia-tech.com/download/
  apollo-agent              ← Linux
  apollo-agent-macos        ← macOS
  apollo-agent.exe          ← Windows
  SHA256SUMS.txt            ← hashes des 3 binaires
  install.sh                ← installateur Linux
  install_macos.sh          ← installateur macOS
  install_windows.ps1       ← installateur Windows
```

---

## Plan de test local (macOS)

### Objectif

Valider que `install_macos.sh` fonctionne de bout en bout AVANT upload Hostinger.

### Principe

On reproduit la structure Hostinger en local avec un serveur HTTP temporaire.
Le script `install_macos.sh` a une variable `DOWNLOAD_BASE` en haut.
On la surcharge pour pointer vers le serveur local au lieu de aiia-tech.com.

### Etapes

1. **Creer un dossier temporaire qui reproduit la structure Hostinger :**
   ```bash
   mkdir -p /tmp/apollo-download-test
   cp ~/projet_apollo_data_auditor_rust-modules/releases/v1.7.R/macos/apollo-agent-macos /tmp/apollo-download-test/
   ```

2. **Generer SHA256SUMS.txt :**
   ```bash
   cd /tmp/apollo-download-test
   shasum -a 256 apollo-agent-macos > SHA256SUMS.txt
   ```

3. **Lancer un serveur HTTP local :**
   ```bash
   cd /tmp/apollo-download-test && python3 -m http.server 8888
   ```

4. **Dans un autre terminal, lancer l'installateur :**
   ```bash
   DOWNLOAD_BASE="http://localhost:8888" bash ~/github_push/install_macos.sh --api-key TEST_KEY
   ```

5. **Verifications attendues :**
   - Download du binaire : OK
   - SHA256 verification : PASSED
   - xattr quarantine remove : OK
   - sudo cp vers /usr/local/bin/apollo-agent : OK
   - Config ecrite dans ~/.apollo/config.json : OK
   - `apollo-agent --version` : repond correctement

6. **Nettoyage :**
   ```bash
   rm -rf /tmp/apollo-download-test
   # sudo rm /usr/local/bin/apollo-agent  (si voulu)
   ```

### Pourquoi /tmp/ et pas un dossier existant ?

- On ne pollue pas les repos avec des fichiers temporaires de test
- Structure identique a Hostinger (dossier plat)
- Nettoyage trivial

---

## Apres le test macOS

Meme pattern pour Linux et Windows une fois les binaires CI rebuildes.

---

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
