---
title: "Deblocage OS - APOLLO Data Auditor"
agent: redactor
project_id: PRJ-APOLLO
date: 2026-03-05
tags: [windows, macos, gatekeeper, smartscreen, troubleshooting, installation]
category: technical
type: guide
status: active
---

# APOLLO Data Auditor - Deblocage OS

Ce document couvre les situations ou macOS ou Windows bloque l'execution du binaire APOLLO Data Auditor.

---

## macOS - Gatekeeper

### Symptome

> "Apple ne peut pas verifier que ce logiciel ne contient pas de logiciels malveillants"

Ou : double-clic sans effet, ou message "Le developpeur ne peut pas etre verifie".

### Solution 1 : Terminal (recommandee)

```bash
xattr -rd com.apple.quarantine /chemin/vers/apollo-agent
```

Puis lancer normalement :

```bash
./apollo-agent --version
```

### Solution 2 : Interface graphique

1. Finder -> localiser `apollo-agent`
2. **Clic droit** -> **Ouvrir**
3. Dans la fenetre d'alerte -> cliquer **"Ouvrir quand meme"**

> Cette methode fonctionne uniquement la premiere fois. Les lancements suivants sont autorises automatiquement.

### Solution 3 : Reglages Systeme (macOS 13+)

1. Ouvrir **Reglages Systeme** -> **Confidentialite et securite**
2. Descendre jusqu'a la section **Securite**
3. Cliquer **"Ouvrir quand meme"** en face du message concernant apollo-agent

---

## Windows - SmartScreen

### Symptome

> "Windows a protege votre ordinateur"
> "L'editeur de ce logiciel est inconnu"

### Solution 1 : Interface (utilisateurs non-techniques)

1. Cliquer **"Informations complementaires"** (lien en bleu sous le message)
2. Cliquer **"Executer quand meme"**

### Solution 2 : Proprietes du fichier

1. Clic droit sur `apollo-agent.exe` -> **Proprietes**
2. Onglet **General**
3. En bas : cocher **"Debloquer"**
4. Cliquer **OK**
5. Lancer normalement

### Solution 3 : PowerShell (administrateur)

```powershell
Unblock-File -Path "C:\chemin\vers\apollo-agent.exe"
```

### Quick Start beta testeur (depuis Downloads)

Copiez-collez dans PowerShell apres avoir telecharge `apollo-agent.exe` :

```powershell
cd $env:USERPROFILE\Downloads; Unblock-File .\apollo-agent.exe; .\apollo-agent.exe --serve
```

L'agent affiche l'URL dans le terminal et ouvre le navigateur automatiquement :

```
APOLLO Data Auditor V1.7.R — UI starting on http://localhost:8052/static/login.html
```

> **Note port** : si 8052 est occupe, l'agent choisit automatiquement un port libre entre 8052 et 8099.
> L'URL exacte est toujours affichee dans le terminal au demarrage.

---

## Windows - Antivirus (faux positif)

### Contexte

Les binaires compiles avec PyInstaller peuvent declencher des faux positifs antivirus. C'est un comportement connu lie au packaging (pas au code).

### Solution : Ajouter une exclusion

Selon l'antivirus installe :

**Windows Defender :**

1. **Securite Windows** -> **Protection contre les virus et menaces**
2. **Parametres de protection** -> **Ajouter ou supprimer des exclusions**
3. Ajouter le fichier : `C:\chemin\vers\apollo-agent.exe`
4. Ajouter le dossier : `C:\ProgramData\Apollo\`

**PowerShell (administrateur) :**

```powershell
Add-MpPreference -ExclusionPath "C:\chemin\vers\apollo-agent.exe"
Add-MpPreference -ExclusionPath "C:\ProgramData\Apollo\"
```

**Autres antivirus (ESET, Kaspersky, Bitdefender...) :**

Chercher dans les reglages : "Exclusions", "Exceptions" ou "Fichiers autorises" et ajouter le chemin du binaire.

---

## Verification post-deblocage

```bash
# macOS / Linux
./apollo-agent --version

# Windows
apollo-agent.exe --version
```

Resultat attendu :

```
APOLLO Data Auditor v1.7.R
```

---

## Si le probleme persiste

Transmettre a l'equipe Apollo :

1. OS et version exacte (ex: macOS 14.3, Windows Server 2022)
2. Nom de l'antivirus installe et version
3. Capture d'ecran du message d'erreur
4. Resultat de la commande :

```bash
# macOS
xattr -l ./apollo-agent

# Windows (PowerShell)
Get-Item "apollo-agent.exe" | Select-Object -ExpandProperty Attributes
```

---

**Copyright**: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
