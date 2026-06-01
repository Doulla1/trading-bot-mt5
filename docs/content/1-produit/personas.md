# Personas et cas d'usage

## Persona 1 : Le trader algorithmique curieux

**Profil** : Alexandre, 34 ans, trader semi-professionnel, connait MetaTrader et les indicateurs techniques, debutant en Python.

**Objectif** : Automatiser une partie de son analyse pour ne plus passer 3h/jour devant les charts.

**Cas d'usage** :
- Lancer le bot le matin et recevoir des trades filtres par l'IA
- Consulter les logs pour comprendre pourquoi un trade a ete pris ou ignore
- Ajuster les parametres de risque dans le `.env`

**Douleur** : Perd du temps a scruter les memes graphiques toutes les 15 minutes. Veut un second avis systematique.

---

## Persona 2 : Le developpeur IA explorateur

**Profil** : Sarah, 28 ans, data scientist, maitrise Python et les API OpenAI, ne connait pas le forex.

**Objectif** : Decouvrir comment un modele de vision peut etre applique a un domaine financier concret.

**Cas d'usage** :
- Lire le code source pour comprendre le prompt engineering
- Modifier les prompts dans `prompts.py` pour tester differentes strategies
- Analyser les decisions JSON stockees en base

**Douleur** : Veut un projet realiste et fonctionnel pour apprendre, pas un tutorial bidon.

---

## Persona 3 : L'investisseur prudent

**Profil** : Marc, 45 ans, investit en bourse depuis 10 ans, n'a jamais utilise d'IA pour trader.

**Objectif** : Tester l'IA comme outil d'aide a la decision sans risquer de capital.

**Cas d'usage** :
- Lancer le bot en observation (`--once` ou `HOLD` systematique)
- Examiner les decisions et reasoning de l'IA
- Comparer avec sa propre analyse manuelle

**Douleur** : Meffiance envers l'IA "boite noire". Veut comprendre le *pourquoi* des decisions.

---

## Persona 4 : Le maintainer du projet

**Profil** : Developpeur backend, reprend le code pour le faire evoluer.

**Objectif** : Comprendre l'architecture, ajouter des fonctionnalites, corriger des bugs.

**Cas d'usage** :
- Lire l'architecture globale et le flux de donnees
- Modifier un module (ex: ajouter un nouvel indicateur)
- Executer les tests et verifier la couverture

**Douleur** : Documentation insuffisante, code non commente, architecture opaque.

---

## Matrice personas / fonctionnalites

| Fonctionnalite | Alexandre (trader) | Sarah (data) | Marc (investisseur) | Maintainer |
|---|---|---|---|---|
| `run.py --once` | Verification rapide | Test du cycle | Observation | Debug |
| `run.py` (boucle) | Usage principal | - | - | - |
| `run.py --stats` | Bilan jour | Analyse perf | Suivi | Validation |
| Prompts IA | - | Modification | - | Optimisation |
| Risk management | Configuration | - | Securite | Regles metier |
| Base SQLite | Historique | Data mining | Transparence | Maintenance |
