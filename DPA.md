# Data Processing Agreement (DPA)
## APOLLO Data Auditor — Beta Program

**Version :** 1.0-beta  
**Date :** 2026-04-25  
**Responsable de traitement (Processor) :** Gilles Gabriel, opérant sous le nom commercial AIIA-Tech  
**Contact :** contact@aiia-tech.com  

---

## Préambule

Le présent Accord de Traitement des Données (DPA) est conclu entre :

- **Le Client** (ci-après "Responsable du Traitement" / "Controller") : toute personne physique ou morale qui utilise APOLLO Data Auditor dans le cadre du programme Beta
- **Gilles Gabriel** (ci-après "Sous-traitant" / "Processor"), développeur et opérateur d'APOLLO Data Auditor, domicilié en France

Cet accord est conclu conformément à l'article 28 du Règlement (UE) 2016/679 (RGPD) et constitue une annexe aux Conditions d'Utilisation Beta d'APOLLO Data Auditor.

---

## Article 1 — Définitions

- **Données Personnelles** : toute information permettant d'identifier directement ou indirectement une personne physique (Art. 4 RGPD)
- **Traitement** : toute opération effectuée sur des données personnelles (collecte, lecture, analyse, structuration)
- **Données de Scan** : données personnelles détectées lors de l'analyse des systèmes du Client par APOLLO
- **Données d'Onboarding** : données collectées lors de l'inscription au programme Beta (nom, prénom, fonction, nom de société, email, secteur d'activité)
- **Hub Cloud** : composant serveur d'APOLLO hébergé sur Netlify (UE) et Railway (UE) recevant les métadonnées de scan

---

## Article 2 — Objet et portée du traitement

### 2.1 Nature du traitement

APOLLO Data Auditor effectue un **audit local en lecture seule** des systèmes désignés par le Client. L'outil :

- Scanne les fichiers, bases de données et sources cloud **uniquement ceux désignés par le Client**
- Détecte et classe les données personnelles (PII) présentes dans ces systèmes
- Génère des rapports de conformité à destination exclusive du Client
- N'exfiltre **aucune valeur de donnée personnelle** vers le Hub Cloud

### 2.2 Finalités du traitement

Le traitement est effectué **uniquement** pour :
1. Permettre au Client d'identifier et cartographier ses propres données personnelles
2. Générer des rapports d'audit RGPD/conformité à usage interne du Client
3. Opérer et améliorer le service APOLLO (via métadonnées non-identifiantes uniquement)

### 2.3 Ce qu'APOLLO NE fait PAS

- ❌ Aucune copie de données personnelles vers des serveurs externes
- ❌ Aucune vente ou partage de données avec des tiers
- ❌ Aucun entraînement de modèle d'IA sur les données du Client
- ❌ Aucun accès en écriture aux systèmes du Client (read-only strict)

### 2.4 Catégories de données concernées

**Données d'onboarding (collectées par le Processor) :**
| Donnée | Finalité | Base légale |
|--------|----------|-------------|
| Nom / Prénom | Identification beta testeur | Art. 6(1)(b) RGPD — exécution accord beta |
| Fonction | Qualification du profil | Art. 6(1)(b) RGPD |
| Nom de société | Identification organisation | Art. 6(1)(b) RGPD |
| Email professionnel | Communication, support beta | Art. 6(1)(b) RGPD |
| Secteur d'activité | Segmentation usage produit | Art. 6(1)(f) RGPD — intérêt légitime |

**Données de scan (traitées localement, sous contrôle exclusif du Client) :**
- Nature et catégories : **déterminées exclusivement par le Client**
- Le Processor n'accède pas à ces données et n'en a pas connaissance
- Le Client est seul responsable de la licéité du scan de ses propres données

---

## Article 3 — Obligations du Processor (Gilles Gabriel / AIIA-Tech)

### 3.1 Traitement sur instruction documentée

Le Processor s'engage à traiter les données personnelles **uniquement sur instruction documentée du Controller**, conformément au présent DPA et aux Conditions d'Utilisation Beta.

### 3.2 Confidentialité

Le Processor s'engage à :
- Maintenir la confidentialité des données d'onboarding
- Limiter l'accès aux seules personnes nécessaires à l'opération du service
- Imposer des obligations de confidentialité équivalentes à toute personne autorisée à traiter les données

### 3.3 Sécurité (Art. 32 RGPD)

Mesures techniques et organisationnelles en place :
- **Transit** : TLS 1.3 pour toutes les communications Hub Cloud
- **Architecture** : traitement local, zéro exfiltration de valeurs PII
- **Accès** : authentification requise, accès en lecture seule aux connecteurs
- **Infrastructure** : Netlify (EU) + Railway (EU) — datacenters conformes RGPD
- **Audit** : logs d'accès conservés 90 jours maximum

### 3.4 Notification de violation (Art. 33 RGPD)

En cas de violation de données personnelles affectant les données d'onboarding, le Processor notifiera le Controller **dans les 72 heures** suivant la découverte, avec :
- Nature de la violation
- Catégories et volume approximatif de données concernées
- Conséquences probables
- Mesures prises ou envisagées

Contact incident : contact@aiia-tech.com, objet : [SECURITY-BREACH]

### 3.5 Assistance aux droits des personnes

Le Processor s'engage à **coopérer avec le Controller** dans un délai de 5 jours ouvrés pour répondre aux demandes d'exercice de droits (accès, rectification, effacement, portabilité) concernant les données d'onboarding.

### 3.6 Suppression des données

À la fin du programme Beta ou sur demande du Controller :
- Données d'onboarding : suppression dans les **30 jours**
- Métadonnées de scan Hub Cloud : suppression dans les **30 jours**
- Confirmation écrite sur demande

---

## Article 4 — Sous-traitants ultérieurs (Sub-processors)

Conformément à l'Art. 28(2) RGPD, le Processor utilise les sous-traitants suivants :

| Sub-processor | Rôle | Données | Localisation | Garanties |
|---------------|------|---------|--------------|-----------|
| **Netlify, Inc.** | Hébergement web, onboarding | Données d'onboarding | UE (à confirmer) | [Privacy Statement Netlify](https://www.netlify.com/privacy/) — pas de vente, pas d'IA training |
| **Railway Corp.** | Compute / Hub API | Métadonnées de scan (non-PII) | UE | SCCs disponibles sur demande |

**Engagement Netlify (email avril 2026) :** Netlify confirme explicitement : "We do not sell your code or content, and we do not use it to train AI models without your permission."

Le Controller sera notifié par email **30 jours avant** tout ajout ou changement de sub-processor significatif.

---

## Article 5 — Transferts hors UE

Les données sont traitées et stockées dans l'**Union Européenne** (Netlify EU, Railway EU).

En cas de transfert hors UE rendu nécessaire, le Processor s'engage à mettre en place les garanties appropriées :
- Clauses Contractuelles Types (CCT/SCC) de la Commission européenne (décision 2021/914)
- Ou tout mécanisme équivalent approuvé par le CEPD

---

## Article 6 — Durées de conservation

| Données | Durée de conservation | Justification |
|---------|----------------------|---------------|
| Données d'onboarding | Durée du programme Beta + 30 jours | Exécution du contrat Beta |
| Logs d'accès Hub | 90 jours glissants | Sécurité opérationnelle |
| Métadonnées de scan | Session + 30 jours maximum | Génération des rapports |
| Données de scan locales | **Non conservées par le Processor** | Architecture zero-persistence |

---

## Article 7 — Droits du Controller

Le Controller conserve à tout moment le droit de :
- Auditer les mesures de sécurité du Processor (sur préavis de 15 jours)
- Demander la suppression immédiate de ses données
- Révoquer son consentement à la participation au programme Beta
- Recevoir une copie de ses données d'onboarding (portabilité)

---

## Article 8 — Responsabilité

Pendant la phase Beta, le Processor agit en qualité de **sous-traitant au sens de l'Art. 28 RGPD** pour les données de scan (dont le Controller conserve la maîtrise exclusive), et en qualité de **responsable de traitement** pour les données d'onboarding.

Le Controller est seul responsable :
- De la licéité du scan de ses propres systèmes
- Des données qu'il choisit de soumettre à l'analyse APOLLO
- De la communication aux personnes concernées de l'existence de l'audit

---

## Article 9 — Loi applicable et juridiction

Le présent DPA est régi par le droit français.  
Tout litige sera soumis aux tribunaux compétents de Paris, France.  
En cas de contradiction, le RGPD prévaut sur toute disposition contractuelle contraire.

---

## Article 10 — Acceptation

L'utilisation d'APOLLO Data Auditor dans le cadre du programme Beta vaut acceptation du présent DPA.

Pour toute demande relative au présent DPA :  
📧 contact@aiia-tech.com — Objet : [DPA REQUEST]

---

*Ce DPA sera mis à jour lors de la constitution d'une entité juridique formelle (AIIA-Tech SAS). Les Controllers seront notifiés 30 jours avant toute modification substantielle.*

**Gilles Gabriel — AIIA-Tech**  
contact@aiia-tech.com  
France
