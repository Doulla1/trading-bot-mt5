# ADR-004 : Mecanisme de recuperation JSON pour reponses IA tronquees

**Statut** : Accepte

**Date** : 2026-06-10

**Contexte** : DeepSeek V4 Pro tronque occasionnellement ses reponses JSON au milieu du champ `reasoning` lorsque la generation atteint la limite de tokens ou qu'un timeout interne se produit. Une reponse JSON invalide signifie la perte complete du signal de trading pour ce cycle, ce qui peut faire manquer des opportunites.

Le probleme a ete detecte via les logs de production qui montraient des `JSONDecodeError` sur des reponses dont le contenu etait visiblement un JSON valide coupe en plein milieu d'une valeur string. Exemple typique :

```json
{"action": "SELL", "confidence": 75, "reasoning": "Tendance baissiere confirmee par EMA, Ichimoku et ADX
```

## Decision

Implementer un mecanisme de recuperation en 4 strategies + 3 mesures preventives dans `src/ai/analyzer.py`.

### 1. Fonction `_recover_truncated_json(raw: str) -> dict | None`

Quatre strategies executees en cascade jusqu'a obtention d'un resultat utilisable :

| Ordre | Strategie | Methode |
|---|---|---|
| 1 | Fermeture d'accolades | Compte `{`/`}`, ajoute `}` manquants, coupe les strings incompletes |
| 2 | Regex greedy | `\{.*\}` sur le texte brut |
| 3 | Extraction champ par champ | Regex par type (string, int/float, nullable) pour 9 champs |
| 4 | Fusion | Merge du resultat partiel S1/S2 avec les champs individuels S3 |

Valeurs par defaut pour les champs manquants : `reasoning="(reponse tronquee)"`, numeriques=0, `risk_level="MEDIUM"`, nullable=None.

### 2. `response_format={"type": "json_object"}`

Ajout du parametre `response_format` a l'appel API OpenAI-compatible. Ce parametre est supporte par DeepSeek et OpenAI et force le modele a emettre un JSON syntaxiquement valide, reduisant les troncatures a la source.

### 3. Augmentation `max_tokens` : 4000 -> 4096

Les 96 tokens supplementaires donnent plus de marge au modele pour terminer sa reponse, particulierement pour les analyses complexes qui necessitent un `reasoning` long (>500 tokens).

### 4. Alerte de proximite de limite

Un warning est emis quand `completion_tokens >= 3500` (sur 4096) pour signaler un risque de troncature avant qu'il ne se produise.

### 5. Log etendu pour diagnostic

Les 500 premiers caracteres de la reponse brute sont logges en debug (au lieu de 200 avant), facilitant le diagnostic des troncatures.

## Alternatives considerees

| Alternative | Pour | Contre | Verdict |
|---|---|---|---|
| **json_repair (librairie externe)** | Robuste, couvre tous les cas | Nouvelle dependance, pas assez testee en production | Rejete (implementer notre propre logique donne plus de controle) |
| **Augmenter massivement max_tokens (ex: 8000)** | Simple | Cout 2x en tokens, ne garantit pas l'absence de troncature, augmente la latence | Rejete (le probleme peut venir d'un timeout, pas seulement des tokens) |
| **Streaming + accumulation** | Detection en temps reel de la fin du JSON | Complexite de code, parsing partiel fragile | Rejete (trop complexe pour le gain) |
| **Re-essayer la requete (retry)** | Simple, fiable si la troncature est aleatoire | Cout double en tokens, latence doublee, pas garanti | Partiellement applique (tenacity retry deja en place, mais la recuperation evite le retry) |

## Consequences

### Positives
- **Zero perte de signal** : les reponses tronquees sont recuperees au lieu d'etre jetees
- **Transparent pour le reste du systeme** : `_validate_decision()` recoit un dict normal
- **Pas de dependance externe** : tout est implemente avec `json` et `re` standards
- **Couverture de test** : 9 cas unitaires couvrent tous les chemins de recuperation
- **Mesures preventives** : `response_format` reduit les troncatures a la source, l'alerte tokens permet d'anticiper

### Negatives
- **Complexite ajoutee** : +80 lignes dans `analyzer.py` pour la fonction de recuperation
- **Perte partielle de donnees** : si le `reasoning` est tronque, une partie de l'analyse qualitative est perdue (mais la decision action/confidence/SL/TP est preservee)
- **Faux positifs impossibles** : si la recuperation produit un JSON syntaxiquement valide mais semantiquement incorrect, `_validate_decision()` le rejettera via les plages de validation

### Neutres
- La recuperation ne s'applique qu'aux reponses du modele principal (`make_decision`) et du modele rapide (`make_decision_fast`)
- Les deux fonctions partagent la meme logique de recuperation, garantissant un comportement coherent
- Le `response_format` est encapsule dans un `try/except` pour ne pas casser les providers qui ne le supportent pas
