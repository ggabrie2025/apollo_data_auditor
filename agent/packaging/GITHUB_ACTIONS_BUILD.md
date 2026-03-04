---
title: "Build via GitHub Actions — Migration VM vers CI/CD"
agent: claude-code
project_id: PRJ-APOLLO
date: 2026-03-04
tags: [packaging, build, github-actions, nuitka, pyinstaller, ci-cd, ip-protection]
category: technical
type: guide
status: draft
---

# Build via GitHub Actions — Migration VM vers CI/CD

## Contexte

Le build actuel utilise une VM Windows UTM locale (voir `windows/VM_BUILD_PROCEDURE.md`).
18h perdues sur 3 sessions (sync fichiers, SPICE instable, Nuitka bugs).
GitHub Actions elimine ces problemes : build dans le cloud, reproductible, multi-OS parallele.

## Architecture repos — REGLE NON-NEGOCIABLE

```
~/projet_apollo_data_auditor_rust-modules/   # REPO SOURCE (dev, tests, JAMAIS de git push)
        |
        | sync manuelle (selective)
        v
~/github_push/                               # REPO GITHUB (unique repo autorise pour git push)
  origin: https://github.com/ggabrie2025/apollo_data_auditor.git
  Statut: PRIVE
```

**REGLES :**
- **1 seul repo est synchronise avec GitHub** : `~/github_push/`
- **C'est le SEUL repo autorise pour `git push`** — tous les autres repos (cloud3, agent rust, cloud v2) sont INTERDITS de push
- Le repo GitHub target est **PRIVE** (`ggabrie2025/apollo_data_auditor`)
- La sync du repo source vers `~/github_push/` est **manuelle et selective** — on ne pousse que les fichiers necessaires au build + le binaire, JAMAIS le repo source complet
- **INTERDIT** : Pousser `backend/.env`, cles API, configs avec credentials
- **INTERDIT** : Pousser le code source Python non-compile (sauf si decision explicite de passer en open-source)

### Procedure de sync source → github_push

```bash
# Depuis le repo source, copier uniquement ce qui est necessaire
DEST=~/github_push

# Binaires pre-compiles (release uniquement)
cp agent/packaging/windows/dist/apollo-agent.exe $DEST/releases/
cp agent/packaging/linux/dist/apollo-agent $DEST/releases/

# Config (sans secrets)
cp agent/config/exclusions.yaml $DEST/config/

# Workflow CI/CD
cp -r .github/ $DEST/.github/

# README, LICENSE
cp README.md LICENSE $DEST/

# JAMAIS : backend/.env, agent/core/*.py (source), agent/ui/server.py (source)
```

## Pourquoi migrer

| Probleme actuel (VM locale) | Solution GitHub Actions |
|-----------------------------|------------------------|
| Sync Mac → VM fragile (SPICE, SMB, HTTP) | Checkout automatique du repo |
| Nuitka 4.0.1 + AppleDouble crash | Nuitka-Action officielle, env propre |
| Python 3.13 incompatible Nuitka Windows | Matrix: build en 3.12 stable |
| Build Windows uniquement sur VM ARM | `windows-latest` = x64 natif |
| 1 seul OS a la fois | Windows + Linux + macOS en parallele |
| Pas reproductible (etat VM variable) | Container propre a chaque build |

## Choix du compilateur

### Nuitka vs PyInstaller — Decision pour GitHub public

| Critere | Nuitka | PyInstaller (actuel) |
|---------|--------|---------------------|
| **Protection IP** | **C natif — quasi irreversible** | Bytecode .pyc — reversible en 5 min avec `uncompyle6` |
| **Taille binaire** | ~58 MB (Linux) | ~24 MB |
| **Vitesse startup** | Rapide (natif) | Lent (bootstrap loader) |
| **Build time** | 15-20 min | 1 min |
| **Bugs connus 2026** | Python 3.13 instable, certifi, VS2026 | Stable, multiprocessing-fork |
| **GitHub Action** | `Nuitka/Nuitka-Action@main` (officielle) | `JackMcKew/pyinstaller-action-*` |

**Decision : Nuitka pour release publique GitHub** (IP protection critique).
PyInstaller reste en fallback pour builds internes rapides.

### Bugs Nuitka connus (mars 2026)

| Bug | Impact | Mitigation |
|-----|--------|------------|
| Python 3.13 structure layouts Windows | Build fail ou crash runtime | **Utiliser Python 3.12 dans le CI** |
| CPython 3.13.4 Windows GIL link library | Break Nuitka "heavily" | Python 3.12 |
| certifi 2025.6.15 ImportError | `requests` crash a l'execution | Nuitka >= 2.7.10 ou pin certifi < 2025.6 |
| Visual Studio 2026 detection | C compiler non trouve | Le runner `windows-latest` a VS pre-installe |
| Onefile `__compiled__.original_argv0` crash | Crash au demarrage | Fixe dans Nuitka >= 2.8 |
| AppleDouble `._` files | `AssertionError agent.core..___init__` | N/A sur GitHub (pas de macOS resource forks) |

**Recommandation** : `python-version: '3.12'` + `nuitka-version: main` (derniere stable).

### Alternatives evaluees

| Outil | Protection IP | Verdict |
|-------|--------------|---------|
| **Nuitka** | Compile en C natif | **CHOIX** pour release publique |
| **PyInstaller** | Bytecode reversible | Fallback interne uniquement |
| **cx_Freeze** | Bytecode reversible | Pas d'avantage vs PyInstaller |
| **PyOxidizer** | Binaire Rust natif | Projet en maintenance, docs pauvres |
| **Cython** | Compile en C | Bonne protection mais requires .pyx rewrite |

## IP Protection — Ce qui reste expose dans le binaire

Meme compile avec Nuitka, `strings` sur le binaire extrait :

| Expose | Risque | Mitigation possible |
|--------|--------|---------------------|
| 58 regex PII (email, IBAN, phone_fr, SSN...) | HAUTE | Externaliser dans fichier chiffre charge au runtime |
| Sampling rates (100/30/15%) | MOYENNE | Deplacer dans config chiffree |
| 76 messages logger | BASSE | Remplacer par codes (`[F01]`, `[D03]`) |
| 26 endpoints API paths | BASSE | Pas de secret, juste la surface |
| URL Railway prod | BASSE | Publique de toute facon |
| `exclusions.yaml` (texte clair) | HAUTE | Retirer commentaires, minifier |

**Ce qui est protege** :
- Scoring = 100% cote Hub Cloud, JAMAIS dans l'agent
- Logique Rust (walker, fingerprint, bloom) = binary stripped + LTO
- Flow Python (ordre operations, branchements) = C natif Nuitka

## Workflow GitHub Actions

### Fichier : `.github/workflows/build-agent.yml`

```yaml
name: Build Apollo Agent

on:
  push:
    tags: ['v*']           # Build sur tags release uniquement
  workflow_dispatch:        # Build manuel depuis GitHub UI

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: windows-latest
            artifact: apollo-agent.exe
          - os: ubuntu-latest
            artifact: apollo-agent.bin
          # macOS a ajouter quand teste
          # - os: macos-latest
          #   artifact: apollo-agent

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'    # PAS 3.13 — instable avec Nuitka

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Build Rust module
        if: false   # Desactive — le module Rust est pre-compile
        # Pour activer: installer Rust, maturin, compiler per-platform
        # Voir apollo_io_native/BUILD.md
        run: |
          pip install maturin
          cd apollo_io_native
          maturin build --release

      - name: Build with Nuitka
        uses: Nuitka/Nuitka-Action@main
        with:
          nuitka-version: main
          script-name: agent/main.py
          mode: onefile
          output-filename: ${{ matrix.artifact }}
          include-package: agent
          include-data-dir: |
            agent/ui/static=agent/ui/static
            agent/config=agent/config

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: apollo-agent-${{ matrix.os }}
          path: build/${{ matrix.artifact }}
          retention-days: 90

  # Release automatique sur tag
  release:
    needs: build
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/')

    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v4

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            apollo-agent-windows-latest/apollo-agent.exe
            apollo-agent-ubuntu-latest/apollo-agent.bin
          generate_release_notes: true
```

### Variante PyInstaller (fallback rapide)

```yaml
      - name: Build with PyInstaller (fallback)
        if: false   # Activer si Nuitka echoue
        run: |
          pip install pyinstaller
          cd agent/packaging/windows
          pyinstaller apollo_agent_win.spec --clean --noconfirm
```

## Module Rust — Strategie CI

Le module `apollo_io_native` (PyO3) doit etre compile per-platform.
Deux options :

### Option A : Pre-compile et commit les binaires (RECOMMANDE pour MVP)

```
apollo_io_native/prebuilt/
  apollo_io_native.pyd      # Windows x64
  apollo_io_native.so        # Linux x64
  apollo_io_native.dylib     # macOS ARM (si besoin)
```

Le workflow copie le bon binaire dans le build.
Simple, zero Rust toolchain dans le CI.

### Option B : Compile Rust dans le CI (long terme)

```yaml
      - name: Install Rust
        uses: actions-rs/toolchain@v1
        with:
          toolchain: stable

      - name: Build Rust module
        run: |
          pip install maturin
          cd apollo_io_native
          maturin build --release
          pip install target/wheels/*.whl
```

Ajoute ~5 min au build. Necessaire quand le Rust evolue souvent.

## Migration progressive

| Phase | Action | Effort |
|-------|--------|--------|
| ~~**P0**~~ | ~~Creer le repo GitHub (private)~~ | ~~FAIT~~ — `ggabrie2025/apollo_data_auditor` |
| **P1** | Premier commit dans `~/github_push/` : README + LICENSE + workflow | 1h |
| **P2** | `.github/workflows/build-agent.yml` avec PyInstaller (fallback) | 1h |
| **P3** | Tester Nuitka dans le CI (Python 3.12) | 2h |
| **P4** | Ajouter build Linux | 1h |
| **P5** | Pre-build Rust `.pyd` et le commit dans github_push | 30 min |
| **P6** | Tag `v1.7.R` → release automatique avec binaires | 10 min |
| **P7** | Passer le repo en **public** pour traction | Decision business + audit IP pre-requis |

**Pre-requis avant P7 (passage public) :**
- Retirer commentaires explicatifs de `exclusions.yaml`
- Verifier qu'aucun secret n'est dans l'historique git (`git log -p | grep -i key\|token\|password`)
- Audit `strings` sur le binaire compile (regex PII, sampling rates)
- Decision : pousser le source Python ou uniquement les binaires compiles

## Avantages GitHub Actions (gratuit sur repo public)

- **2000 min/mois** de build gratuit (repos publics)
- **Windows/Linux/macOS** en parallele sans VM locale
- **Python 3.12** pour les builds, 3.13 pour le dev local
- **Reproductible** — chaque tag produit exactement les memes binaires
- **Artifacts** telechargeables par les beta testeurs depuis GitHub Releases
- **Zero infrastructure** — pas de VM UTM, pas de sync, pas de SPICE

## References

- `docs/plans/GITHUB_LAUNCH_CHECKLIST.md` — **Checklist lancement complet** (8 phases : repo, dataset demo, GIF, README, posts Reddit, Windows)
- [Nuitka-Action GitHub](https://github.com/Nuitka/Nuitka-Action) — Action officielle
- [Nuitka Issues](https://github.com/Nuitka/Nuitka/issues) — Bugs connus
- [Nuitka Python 3.13 changelog](https://nuitka.net/changelog/Changelog.html) — Compatibilite
- [PyInstaller Action](https://github.com/marketplace/actions/pyinstaller-action) — Fallback
- [2026 Comparison Nuitka vs PyInstaller vs cx_Freeze](https://ahmedsyntax.com/2026-comparison-pyinstaller-vs-cx-freeze-vs-nui/)
- [Build Binary with GitHub Actions (DEV.to)](https://dev.to/rahul_suryash/steps-to-build-binary-executables-for-python-code-with-github-actions-4k92)
- `agent/packaging/README.md` — Build overview actuel
- `agent/packaging/windows/VM_BUILD_PROCEDURE.md` — Procedure VM (a remplacer)

---

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
