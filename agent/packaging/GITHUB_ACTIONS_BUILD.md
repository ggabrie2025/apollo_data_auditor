---
title: "Build via GitHub Actions — Migration VM vers CI/CD"
agent: claude-code
project_id: PRJ-APOLLO
date: 2026-03-14
tags: [packaging, build, github-actions, pyinstaller, ci-cd]
category: technical
type: guide
status: active
---

# Build via GitHub Actions — Migration VM vers CI/CD

## Contexte

Le build actuel utilise PyInstaller en local (macOS ARM). Les builds Windows/Linux
sont bloques car les VM UTM sur Mac ARM produisent des binaires ARM, pas x86_64.
18h perdues sur 3 sessions (sync fichiers, SPICE instable, incompatibilites arch).

**Nuitka = ABANDONNE** (decision definitive, Sprint 117). Trop de bugs, Python 3.13
instable, AppleDouble crash, 0 build reussi en 3 tentatives. PyInstaller = seul outil
de packaging autorise.

GitHub Actions elimine le probleme d'architecture :
`windows-latest` et `ubuntu-latest` = **x86_64 natif**.

## Architecture repos — REGLE NON-NEGOCIABLE

```
~/projet_apollo_data_auditor_rust-modules/   # REPO SOURCE (dev, tests, JAMAIS de git push)
        |
        | sync manuelle via git diff-tree + cp (JAMAIS rsync)
        v
~/github_push/                               # REPO GITHUB (unique repo autorise pour git push)
  origin: https://github.com/ggabrie2025/apollo_data_auditor.git
  Statut: PRIVE
```

**REGLES :**
- **1 seul repo est synchronise avec GitHub** : `~/github_push/`
- **C'est le SEUL repo autorise pour `git push`**
- Le repo GitHub target est **PRIVE** (`ggabrie2025/apollo_data_auditor`)
- La sync est **manuelle et selective** via `git diff-tree + cp` (JAMAIS rsync)
- **INTERDIT** : Pousser `backend/.env`, cles API, configs avec credentials

### Procedure de sync source vers github_push

```bash
# Apres un commit dans le repo dev :
cd ~/projet_apollo_data_auditor_rust-modules
git diff-tree --no-commit-id --name-only -r HEAD -- agent/ apollo_io_native/
# Copier chaque fichier individuellement :
cp <fichier_modifie> ~/github_push/<fichier_modifie>
```

## Pourquoi migrer

| Probleme actuel (local) | Solution GitHub Actions |
|--------------------------|------------------------|
| VM UTM sur Mac ARM = binaires ARM, pas x86_64 | `windows-latest` / `ubuntu-latest` = x64 natif |
| Sync Mac vers VM fragile (SPICE, SMB) | Checkout automatique du repo |
| Build Windows impossible sans VM | Runner Windows x64 gratuit |
| Build Linux inexistant | Runner Ubuntu x64 gratuit |
| 1 seul OS a la fois | Windows + Linux + macOS en parallele |
| Pas reproductible (etat VM variable) | Container propre a chaque build |

## Compilateur : PyInstaller (SEUL AUTORISE)

**Nuitka = ABANDONNE** — ne jamais reproposer.

| Critere | PyInstaller |
|---------|-------------|
| **Stabilite** | Stable, Python 3.12/3.13, tous OS |
| **Build time** | ~1 min |
| **Taille binaire** | ~24 MB |
| **GitHub Action** | `JackMcKew/pyinstaller-action-*` ou `pip install pyinstaller` direct |
| **Spec existant** | `agent/packaging/macos/apollo_agent.spec` (macOS), `agent/packaging/windows/apollo_agent_win.spec` (Windows) |

## IP Protection — Ce qui est expose dans le binaire PyInstaller

Le bytecode .pyc est reversible (`uncompyle6`). Mitigations :

| Expose | Risque | Mitigation |
|--------|--------|------------|
| 58 regex PII (email, IBAN, phone_fr, SSN...) | HAUTE | Externaliser dans fichier chiffre charge au runtime |
| Sampling rates (100/30/15%) | MOYENNE | Deplacer dans config chiffree |
| 76 messages logger | BASSE | Remplacer par codes (`[F01]`, `[D03]`) |
| 26 endpoints API paths | BASSE | Pas de secret, juste la surface |
| URL Railway prod | BASSE | Publique de toute facon |
| `exclusions.yaml` (texte clair) | HAUTE | Retirer commentaires, minifier |

**Ce qui est protege nativement** :
- Scoring = 100% cote Hub Cloud, JAMAIS dans l'agent (zero IP scoring dans le binaire)
- Logique Rust (walker, fingerprint, bloom) = binary stripped + LTO (quasi irreversible)

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
            spec: agent/packaging/windows/apollo_agent_win.spec
          - os: ubuntu-latest
            artifact: apollo-agent
            spec: agent/packaging/linux/apollo_agent_linux.spec

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Install PyInstaller
        run: pip install pyinstaller

      - name: Build with PyInstaller
        run: pyinstaller ${{ matrix.spec }} --clean --noconfirm

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: apollo-agent-${{ matrix.os }}
          path: dist/${{ matrix.artifact }}
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
            apollo-agent-ubuntu-latest/apollo-agent
          generate_release_notes: true
```

## Module Rust — Strategie CI

Le module `apollo_io_native` (PyO3) doit etre compile per-platform.

### Option A : Pre-compile et commit les binaires (RECOMMANDE pour MVP)

```
apollo_io_native/prebuilt/
  apollo_io_native.pyd      # Windows x64
  apollo_io_native.so        # Linux x64
  apollo_io_native.dylib     # macOS ARM
```

Le workflow copie le bon binaire dans le build.
Simple, zero Rust toolchain dans le CI.

### Option B : Compile Rust dans le CI (long terme)

```yaml
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Build Rust module
        run: |
          pip install maturin
          cd apollo_io_native
          maturin build --release
          pip install target/wheels/*.whl
```

Ajoute ~5 min au build. Necessaire quand le Rust evolue souvent.

## Migration progressive

| Phase | Action | Effort | Status |
|-------|--------|--------|--------|
| ~~**P0**~~ | ~~Creer le repo GitHub (private)~~ | ~~FAIT~~ | `ggabrie2025/apollo_data_auditor` |
| ~~**P1**~~ | ~~Premier commit : README + LICENSE~~ | ~~FAIT~~ | github_push operationnel |
| ~~**P2**~~ | ~~`.github/workflows/build-agent.yml` (PyInstaller)~~ | ~~FAIT~~ | `build-agent.yml` deploye |
| ~~**P3**~~ | ~~Tester le build CI Windows + Linux~~ | ~~FAIT~~ | CI operationnel depuis patch13 — Windows `.exe` + Linux binaire produits automatiquement sur tag `v*` |
| ~~**P4**~~ | ~~Compile Rust dans le CI (Option B — maturin)~~ | ~~FAIT~~ | `maturin build --release` dans `build-agent.yml` — pas de prebuilt a commiter |
| ~~**P5**~~ | ~~Tags release → release automatique avec binaires~~ | ~~FAIT~~ | `v1.7.R-patch13` → `v1.7.R-patch18` (2026-03-20 → 2026-03-26). macOS uploade manuellement via `gh release upload` |
| **P6** | Passer le repo en **public** pour traction | Decision business + audit IP | En attente (voir pre-requis ci-dessous) |

**Pre-requis avant P6 (passage public) :**
- Retirer commentaires explicatifs de `exclusions.yaml`
- Verifier qu'aucun secret n'est dans l'historique git (`git log -p | grep -i key\|token\|password`)
- Audit `strings` sur le binaire PyInstaller (regex PII, sampling rates)
- Decision : pousser le source Python ou uniquement les binaires compiles

## Avantages GitHub Actions

- **2000 min/mois** de build gratuit (repos publics), 500 min/mois (repos prives)
- **Windows x64 / Linux x64 / macOS** en parallele sans VM locale
- **Reproductible** — chaque tag produit exactement les memes binaires
- **Artifacts** telechargeables par les beta testeurs depuis GitHub Releases
- **Zero infrastructure** — pas de VM UTM, pas de sync SPICE, pas de probleme d'architecture ARM

## Build par plateforme — RESUME

| Plateforme | Ou | Comment |
|------------|-----|---------|
| **macOS arm64** | **Local** (ce Mac) | `pyinstaller agent/packaging/macos/apollo_agent.spec` |
| **Windows x64** | **GitHub Actions** | Tag `v*` ou workflow_dispatch |
| **Linux x64** | **GitHub Actions** | Tag `v*` ou workflow_dispatch |

macOS est build en local car on a la machine Apple Silicon.
Windows/Linux passent par GitHub Actions car les VM UTM ARM ne produisent pas de binaires x86_64.

## Checklist pre-push vers github_push

**AVANT chaque push vers `~/github_push/` :**

```
[ ] 1. Tests critiques passes
      cd ~/projet_apollo_data_auditor_rust-modules
      python3 -m pytest critical/ -v

[ ] 2. Copier les fichiers modifies (JAMAIS rsync)
      git diff-tree --no-commit-id --name-only -r HEAD -- agent/ apollo_io_native/
      cp <fichier> ~/github_push/<fichier>

[ ] 3. Mettre a jour ~/github_push/CHANGELOG.md
      - Ajouter les changements sous la version courante
      - Format: ### Added / ### Fixed / ### Changed

[ ] 4. Build macOS local (si code agent modifie)
      pyinstaller agent/packaging/macos/apollo_agent.spec --clean --noconfirm
      cp dist/apollo-agent ~/github_push/agent/packaging/macos/dist/

[ ] 5. Mettre a jour SHA256SUMS.txt (si binaire macOS rebuild)
      cd ~/github_push && shasum -a 256 agent/packaging/macos/dist/apollo-agent > SHA256SUMS.txt

[ ] 6. Verifier qu'aucun secret ne fuit
      cd ~/github_push && grep -rn "API_KEY\|TOKEN\|PASSWORD\|SECRET" agent/ --include="*.py" | grep -v "test\|example\|placeholder"

[ ] 7. Commit + push depuis ~/github_push/ UNIQUEMENT
      cd ~/github_push
      git add -A && git diff --cached --stat
      git commit -m "<type>: <description>"
      git push origin main

[ ] 8. Si release Windows/Linux : tagger pour declencher GH Actions
      git tag v1.X.Y && git push origin v1.X.Y
```

## References

- `agent/packaging/README.md` — Build overview
- `agent/packaging/macos/apollo_agent.spec` — Spec PyInstaller macOS
- `agent/packaging/windows/apollo_agent_win.spec` — Spec PyInstaller Windows

---

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
