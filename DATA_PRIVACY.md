# Data Privacy & Security Statement — APOLLO™ Data Auditor

> **TL;DR : APOLLO scanne vos données localement. Seuls des compteurs et métadonnées transitent vers le cloud. Aucune valeur PII ne quitte jamais votre infrastructure.**

---

## Ce qu'est APOLLO™ Data Auditor

APOLLO™ Data Auditor est un **binaire natif compilé en Rust**, installé sur votre infrastructure (Windows ou Linux). Il scanne fichiers, bases de données et cloud pour mesurer votre exposition financière RGPD/CCPA — sans jamais exfiltrer vos données.

---

## Principes fondamentaux

| Principe | Statut |
|----------|--------|
| 🔍 Lecture seule | ✅ APOLLO ne modifie, n'écrit et ne supprime aucune donnée |
| 🚫 Zéro exfiltration de données | ✅ Aucune valeur PII ne quitte votre infrastructure |
| 🖥️ Exécution locale | ✅ Le binaire tourne sur votre machine ou vos serveurs |
| 📡 Métadonnées uniquement | ✅ Seuls des compteurs transitent (ex : "156 IBAN détectés") |
| 🔐 Zero data persistence cloud | ✅ Aucune donnée PII n'est stockée côté cloud |

---

## Ce que scanne APOLLO — et comment

### 📁 Fichiers locaux & partages réseau
- APOLLO **lit** les fichiers pour détecter les patterns PII (44 types détectés).
- Il ne copie, ne télécharge et ne met en cache aucun contenu de fichier hors de votre environnement local.
- Les résultats d'analyse sont traités en mémoire.

### 🗄️ Bases de données (MySQL, PostgreSQL, MongoDB, SQL Server)
- APOLLO se connecte avec les credentials que **vous fournissez** à l'exécution.
- Il émet uniquement des requêtes **SELECT** en lecture seule — aucun INSERT, UPDATE, DELETE ou DDL.
- L'inspection de schéma utilise les vues système en lecture seule (`information_schema`).

### ☁️ Cloud (OneDrive, SharePoint) & Active Directory / LDAP
- APOLLO utilise des **scopes de lecture seule** pour les connexions cloud.
- Les tokens API sont utilisés en session uniquement, jamais écrits sur disque par le binaire.

---

## Ce qui quitte votre infrastructure

**Uniquement des compteurs et métadonnées agrégées.**

Le binaire envoie vers le cloud APOLLO uniquement :
- Des **compteurs** (ex : "156 IBAN détectés dans la source MySQL")
- Des **métadonnées** (type de PII, source, volume)
- **Jamais** les valeurs PII elles-mêmes

Ces métadonnées sont utilisées côté cloud pour calculer les scores d'exposition financière (RGPD/CCPA), les risk matrices et le plan d'actions. **Zero data persistence côté cloud** : aucune métadonnée n'est conservée après génération du rapport.

Toutes les communications entre le binaire et le Hub cloud sont chiffrées via **TLS 1.3**.

---

## Architecture de sécurité

```
Votre infrastructure                    Cloud APOLLO
─────────────────────────────────────   ──────────────────────────
Binaire Rust (collecteur pur)      →    Compteurs + métadonnées
  ├── Scan fichiers locaux               (jamais les valeurs PII)
  ├── Connexions DB (SELECT only)   →    Scoring & calcul exposition
  └── Connexions cloud (read-only)  →    Génération rapport
                                         Zero data persistence
```

---

## Comment vérifier vous-même

Nous vous encourageons à auditer le binaire et le trafic réseau :

```bash
# Vérifier les connexions réseau sortantes pendant un scan
# (aucune connexion vers des tiers non documentés attendue)
netstat -an | grep ESTABLISHED

# Vérifier qu'aucune donnée PII n'est écrite sur disque pendant le scan
# (seul le rapport final est écrit dans le répertoire que vous spécifiez)
lsof -p <pid_apollo> | grep REG
```

Aucune connexion sortante vers des tiers (analytics, télémétrie, publicité) n'est initiée par le binaire.

---

## Notice beta testeurs

En tant que beta testeur, merci de noter :

- **Ne connectez pas APOLLO à des bases de données de production** contenant des données clients réelles pendant la phase beta.
- Utilisez des environnements de staging ou des datasets anonymisés.
- Si vous observez une activité réseau inattendue ou une écriture de fichiers non documentée, signalez-le immédiatement à : **contact@aiia-tech.com**

---

## Divulgation responsable

Si vous identifiez un problème de sécurité ou de confidentialité, merci de le signaler en privé avant toute divulgation publique :

📧 **contact@aiia-tech.com**
Objet : `[SECURITY] APOLLO Data Auditor — <description courte>`

Nous nous engageons à accuser réception sous 48h et à résoudre les problèmes confirmés sous 30 jours.

---

## Base légale

Ce document est fourni comme engagement de transparence envers les utilisateurs. Il ne constitue pas un DPA (Data Processing Agreement) formel. Les clients enterprise nécessitant un DPA doivent contacter **contact@aiia-tech.com**.

APOLLO™ Data Auditor est régi par la [Business Source License 1.1](./LICENSE) et le droit français.

---

*Dernière mise à jour : 2026 — Gilles Gabriel / aiia-tech.com*
