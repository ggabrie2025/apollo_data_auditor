# Politique de Confidentialité — Privacy Policy
## APOLLO Data Auditor Beta Program

**Version :** 1.0-beta  
**Date d'entrée en vigueur :** 2026-04-25  
**Dernière mise à jour :** 2026-04-25  

---

## 1. Identité du Responsable de Traitement

**Gilles Gabriel**  
Opérant sous le nom commercial **AIIA-Tech**  
Email : contact@aiia-tech.com  
France  

*Note : AIIA-Tech est actuellement opéré par Gilles Gabriel en tant que personne physique. Une entité juridique (SAS) sera constituée ultérieurement. Cette politique sera mise à jour en conséquence.*

---

## 2. Données collectées et finalités

### 2.1 Données d'inscription au programme Beta

Lors de votre inscription, nous collectons :

| Donnée | Finalité | Base légale (Art. 6 RGPD) |
|--------|----------|---------------------------|
| Nom et prénom | Vous identifier en tant que beta testeur | Art. 6(1)(b) — exécution du contrat Beta |
| Fonction / poste | Comprendre votre profil d'usage | Art. 6(1)(b) — exécution du contrat Beta |
| Nom de la société | Identifier votre organisation | Art. 6(1)(b) — exécution du contrat Beta |
| Adresse email professionnelle | Vous contacter pour le support, les mises à jour, les retours Beta | Art. 6(1)(b) — exécution du contrat Beta |
| Secteur d'activité | Segmenter les retours produit par industrie | Art. 6(1)(f) — intérêt légitime d'AIIA-Tech à améliorer le produit |

### 2.2 Données de fonctionnement du service (Hub Cloud)

Lors de l'utilisation d'APOLLO, des **métadonnées non-identifiantes** transitent via notre Hub Cloud :

| Donnée | Finalité | Base légale |
|--------|----------|-------------|
| Statistiques de scan (nombre de fichiers analysés, types détectés) | Opérer et monitorer le service | Art. 6(1)(b) |
| Logs d'erreurs techniques | Diagnostiquer et corriger les incidents | Art. 6(1)(f) — intérêt légitime |
| Version du logiciel utilisé | Assurer la compatibilité | Art. 6(1)(b) |

**Ce que nous ne collectons PAS :**  
❌ Aucune valeur de donnée personnelle détectée lors des scans  
❌ Aucun contenu de fichiers analysés  
❌ Aucune donnée permettant d'identifier les personnes présentes dans vos systèmes  

### 2.3 Données de scan (traitées localement)

Les données personnelles que vous choisissez de faire analyser par APOLLO restent **exclusivement sur votre infrastructure**. APOLLO Data Auditor opère en lecture seule locale. Vous êtes le Responsable de Traitement de ces données — voir notre [DPA](./DPA.md) pour les détails.

---

## 3. Sous-traitants (Hébergement)

Vos données d'onboarding et les métadonnées de service sont hébergées par :

| Prestataire | Rôle | Localisation | Garanties |
|-------------|------|--------------|-----------|
| **Netlify, Inc.** | Interface web, formulaire d'inscription | Union Européenne | Ne vend pas les données, pas d'IA training — [Privacy Statement](https://www.netlify.com/privacy/) |
| **Railway Corp.** | API / Hub de traitement | Union Européenne | Conforme RGPD |

Aucune donnée n'est transférée hors de l'Union Européenne sans les garanties appropriées (Clauses Contractuelles Types).

---

## 4. Durées de conservation

| Données | Durée | Justification |
|---------|-------|---------------|
| Données d'inscription Beta | Durée du programme + 30 jours | Exécution du contrat Beta |
| Métadonnées Hub Cloud | 90 jours glissants | Sécurité et debug opérationnel |
| Emails de communication | 3 ans après fin de la relation | Intérêt légitime (historique support) |

À l'expiration de ces durées, vos données sont supprimées de manière sécurisée ou anonymisées.

---

## 5. Vos droits (Art. 15 à 21 RGPD)

Vous disposez des droits suivants sur vos données personnelles d'onboarding :

| Droit | Description | Comment l'exercer |
|-------|-------------|-------------------|
| **Accès** (Art. 15) | Obtenir une copie de vos données | Email à contact@aiia-tech.com |
| **Rectification** (Art. 16) | Corriger des données inexactes | Email à contact@aiia-tech.com |
| **Effacement** (Art. 17) | Demander la suppression de vos données | Email à contact@aiia-tech.com |
| **Limitation** (Art. 18) | Limiter temporairement le traitement | Email à contact@aiia-tech.com |
| **Portabilité** (Art. 20) | Recevoir vos données dans un format structuré | Email à contact@aiia-tech.com |
| **Opposition** (Art. 21) | Vous opposer au traitement fondé sur intérêt légitime | Email à contact@aiia-tech.com |
| **Retrait du consentement** | Quitter le programme Beta à tout moment | Email à contact@aiia-tech.com |

**Délai de réponse :** nous nous engageons à répondre dans un délai d'**1 mois** (délai RGPD Art. 12).

**Objet de l'email :** [RGPD - Droit d'accès] ou [RGPD - Effacement] etc.

### Recours

Si vous estimez que vos droits ne sont pas respectés, vous avez le droit d'introduire une réclamation auprès de l'autorité de contrôle compétente :

**CNIL (France)**  
Commission Nationale de l'Informatique et des Libertés  
3 Place de Fontenoy — TSA 80715 — 75334 Paris Cedex 07  
www.cnil.fr | Tél. : +33 1 53 73 22 22

---

## 6. Sécurité des données (Art. 32 RGPD)

Nous mettons en œuvre les mesures suivantes :

- **Chiffrement en transit :** TLS 1.3 pour toutes les communications
- **Architecture zero-exfiltration :** aucune donnée personnelle détectée lors des scans ne quitte votre infrastructure
- **Accès restreint :** seul Gilles Gabriel a accès aux données d'onboarding
- **Infrastructure EU :** hébergement exclusivement dans l'Union Européenne (Netlify + Railway)
- **Read-only :** APOLLO n'a aucun accès en écriture à vos systèmes

En cas de violation de données, vous serez notifié conformément à l'Art. 33 RGPD dans les 72 heures.

---

## 7. Cookies et traceurs

Le site de téléchargement et l'interface d'onboarding n'utilisent **pas de cookies de tracking tiers**.

Seuls des cookies techniques strictement nécessaires au fonctionnement du service peuvent être utilisés (session d'authentification). Ces cookies ne nécessitent pas de consentement (Art. 82 Directive ePrivacy).

---

## 8. Mineurs

APOLLO Data Auditor est un outil professionnel destiné aux entreprises. Nous ne collectons pas sciemment de données personnelles concernant des personnes de moins de 16 ans.

---

## 9. Modifications de cette politique

En cas de modification substantielle de cette Politique de Confidentialité, vous serez informé par email **30 jours avant** l'entrée en vigueur des changements.

La version en vigueur est toujours accessible sur le dépôt GitHub d'APOLLO Data Auditor.

---

## 10. Contact

Pour toute question relative à cette Politique de Confidentialité :

📧 **contact@aiia-tech.com**  
Objet : [PRIVACY] votre demande  

**Gilles Gabriel — AIIA-Tech**  
France

---

*Cette Politique de Confidentialité est rédigée conformément au Règlement (UE) 2016/679 (RGPD) et à la loi Informatique et Libertés modifiée. Elle sera mise à jour lors de la constitution d'AIIA-Tech en entité juridique formelle.*
