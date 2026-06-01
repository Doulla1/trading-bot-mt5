# ADR-001 : Utilisation de GPT-4o-mini Vision pour l'analyse des charts

**Statut** : Accepte

**Date** : 2026-06-01

**Contexte** : Le trading bot a besoin d'analyser visuellement les graphiques de trading (chandeliers, supports, resistances, patterns) pour prendre des decisions eclairees. L'analyse purement numerique (indicateurs calcules) ne permet pas de detecter les patterns graphiques complexes comme les doubles sommets, triangles, drapeaux, ou les figures de retournement.

**Decision** : Utiliser **GPT-4o-mini Vision** (modele `gpt-4o-mini` avec capacite de traitement d'images) comme moteur d'analyse principal.

**Details techniques** :

- Modele : `gpt-4o-mini` (pas le modele de base `gpt-4o-mini` sans vision)
- Resolution image : 800x600, encodee en base64, detail `high`
- Cout estime : **$0.15 a $0.30 par jour**
  - ~400 tokens image par appel
  - ~600 tokens texte (prompt + completions)
  - ~96 appels/jour (15 min d'intervalle, 16h de trading) = ~96 000 tokens/jour
  - Cout : ~$0.15/token image + ~$0.60/token texte = ~$0.25/jour
- Retry : 3 tentatives avec backoff exponentiel (via `tenacity`)
- Temperature : 0.3 (faible, decisions coherentes)
- Max tokens : 600 (reponses concises)

**Alternatives considerees** :

| Alternative | Pour | Contre | Verdict |
|---|---|---|---|
| **GPT-4o** | Meilleure precision visuelle | Cout ~10x plus eleve ($1.50-$3.00/jour) | Rejete (cout trop eleve pour un bot experimental) |
| **Analyse purement numerique** | Gratuit, rapide | Pas de vision des patterns graphiques, pas de lecture des chandeliers | Rejete (perd l'avantage de l'IA visuelle) |
| **Modele open source local (LLaVA, CogVLM)** | Pas de cout API, confidentialite | Necessite GPU, maintenance, qualite inferieure | Rejete (complexite operationnelle) |
| **Claude Vision** | Alternative valable | Cout similaire, dependance additionnelle | Garde en reserve (pas de besoin de multi-cloud) |

**Consequences** :

- **Positives** :
  - Analyse visuelle riche (patterns, tendances visuelles, niveaux cles)
  - Pas de GPU necessaire (tout est cloud)
  - Cout faible et previsible (~$0.25/jour)
  - Modele rapide (< 5s par analyse)

- **Negatives** :
  - Necessite une connexion Internet permanente
  - Dependance au service OpenAI (disponibilite, changements de pricing)
  - Donnees de trading envoyees a un tiers (confidentialite)
  - Latence additionnelle (~2-5s par appel)
  - La qualite de l'analyse peut varier (le modele n'est pas entraine specifiquement pour le trading)

- **Neutres** :
  - L'analyse combine vision + texte dans un seul appel API (pas de pipeline separe)
  - Le prompt guide fortement la sortie (peu de place pour l'hallucination)
  - Les decisions sont validees par des regles de risk management cote bot

**Suivi** : Revoir cette decision si :
- Le cout depasse $1/jour
- Un modele local atteint une qualite comparable
- OpenAI modifie les prix ou la disponibilite de GPT-4o-mini
