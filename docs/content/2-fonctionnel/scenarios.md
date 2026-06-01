# Scenarios metier

Ce document decrit les differents comportements du bot en fonction de la decision de l'IA et des conditions du marche.

## Scenario BUY

**Condition** : L'IA identifie une opportunite d'achat (tendance haussiere, support solide, indicateurs en faveur).

**Deroulement** :

1. L'IA retourne `{"action": "BUY", "confidence": 78, ...}`
2. Verifications :
   - Marche ouvert ? OK
   - Perte jour < 3% ? OK
   - Confiance 78 >= 70 ? OK
   - Positions ouvertes < 1 ? OK
3. Calcul du volume : `calculate_position_size(balance, 25 pips, symbol_info)` -> 0.05 lots
4. Calcul des prix :
   - SL = bid - (25 * 10 * 0.00001)
   - TP = bid + (45 * 10 * 0.00001)
5. Ordre envoye : `ORDER_TYPE_BUY` a prix ask
6. Enregistrement en base (tables `analysis_logs` et `trades`)

**Cas d'echec** :
- Slippage > 20 pips : ordre rejete
- Fonds insuffisants : ordre rejete
- Marche ferme entre temps : ordre rejete

---

## Scenario SELL

**Condition** : L'IA identifie une opportunite de vente (tendance baissiere, resistance, indicateurs baissiers).

**Deroulement** :

Identique a BUY mais en symetrie :

1. L'IA retourne `{"action": "SELL", "confidence": 82, ...}`
2. Memes verifications que BUY
3. Calcul du volume identique
4. SL = ask + (stop_loss_pips * 10 * point)
5. TP = ask - (take_profit_pips * 10 * point)
6. Ordre envoye : `ORDER_TYPE_SELL` a prix bid

---

## Scenario HOLD

**Condition** : L'IA ne voit pas d'opportunite claire ou la confiance est insuffisante.

**Deroulement** :

1. L'IA retourne `{"action": "HOLD", "confidence": 45, "reasoning": "Marche range, pas de signal clair...", ...}`
2. `execute_decision()` detecte `action == "HOLD"` -> log et retour sans action
3. L'analyse est tout de meme enregistree dans `analysis_logs` avec `was_executed = 0`

**Sous-scenarios** :

| Condition | Comportement |
|---|---|
| Aucune position ouverte | Rien ne se passe, prochain cycle |
| Position ouverte + HOLD | La position reste ouverte, prochaine analyse decidera |
| HOLD repetitif | Le bot continue d'analyser sans agir (normal en marche range) |

---

## Scenario CLOSE

**Condition** : L'IA estime que la position ouverte doit etre fermee (retournement, prise de profit, stop avant evenement).

**Deroulement** :

1. L'IA retourne `{"action": "CLOSE", "confidence": 90, "reasoning": "NFP imminent, on se couvre...", ...}`
2. `execute_decision()` boucle sur toutes les positions ouvertes :
   ```python
   for pos in get_open_positions():
       close_position(pos["ticket"])
   ```
3. Chaque fermeture est enregistree dans `Trades` avec `profit` calcule
4. La valeur `confidence` n'est **pas verifiee** pour CLOSE (toujours execute)

**Cas particuliers** :
- Aucune position ouverte : CLOSE est ignore (pas d'erreur)
- Plusieurs positions : toutes fermees
- Echec de fermeture d'une position : loggue mais ne bloque pas les autres

---

## Scenario d'erreur : Pas de screenshot

**Condition** : `mt5.screen_shot()` retourne `None`.

**Cause possible** : Terminal MT5 non initialise, dossier screenshots inaccessible.

**Comportement** :
- `screenshot_path` = `None`
- L'analyse IA ne peut pas etre lancee (`ai_analyze` recoit `screenshot_path=None`)
- Decision = `None`, cycle marque comme HOLD
- L'erreur est loggue dans le fichier de logs

---

## Scenario d'erreur : Echec API OpenAI

**Condition** : L'appel a l'API OpenAI echoue apres 3 tentatives (timeout, quota depasse, cle invalide).

**Comportement** :

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def analyze(...):
    ...
```

- 3 tentatives avec backoff exponentiel (2s, 4s, 8s)
- Si toutes echouent : retour `None`
- Le cycle continue sans decision
- L'erreur est loggue

---

## Scenario d'erreur : Reponse IA invalide

**Condition** : L'IA retourne un JSON malforme ou des champs manquants.

**Comportement** :

```python
json_match = re.search(r"\{.*\}", raw, re.DOTALL)
if not json_match:
    return None  # Pas de JSON trouve

champs_requis = ["action", "confidence", "reasoning", "stop_loss_pips", "take_profit_pips", "risk_level"]
for field in champs_requis:
    if field not in decision:
        return None  # Champ manquant

if decision["action"] not in ("BUY", "SELL", "HOLD", "CLOSE"):
    return None  # Action invalide
```

- La reponse brute est loggue (300 premiers caracteres) pour debug
- Le cycle continue sans execution

---

## Scenario d'erreur : Limite de perte atteinte

**Condition** : Le P&L journalier atteint -3%.

**Comportement** :
- `execute_decision()` retourne immediatement sans trade
- Le prochain cycle reverifie la limite
- Les analyses sont toujours enregistrees dans `analysis_logs` (avec `was_executed = 0`)
- Blocage jusqu'au prochain jour de trading

---

## Scenario weekend / marche ferme

**Condition** : Le marche est ferme (dimanche, lundi avant ouverture, vendredi apres fermeture).

**Comportement** :
- `is_market_open()` retourne `False`
- Le cycle s'arrete avant l'analyse
- En mode `run_forever()`, le bot continue de boucler mais sans action
- Reprise automatique a la reouverture du marche

---

## Scenario : Premier demarrage

**Condition** : Base de donnees vide, aucun historique.

**Comportement** :
- Les tables sont creees automatiquement par `_init_tables()`
- `_get_daily_pnl()` retourne 0.0
- `get_statistics()` retourne des zeros
- Aucun comportement specifique, le bot commence a analyser immediatement
