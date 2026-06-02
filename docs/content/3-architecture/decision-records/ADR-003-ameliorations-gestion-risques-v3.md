# ADR-003 : Ameliorations de la gestion des risques v3.0

**Statut** : Accepte

**Date** : 2026-06-03

**Contexte** : L'audit v3.0 du trading bot a revele quatre defauts dans la gestion des risques qui causaient des pertes systematiques ou des opportunites manquees :

1. **Breakeven trop agressif** : le seuil de 0.5R (50% du SL initial) declenchait le breakeven avant que le trade ait traverse le bruit normal du marche. Resultat : epidemie de "zero-win" - les trades gagnants etaient systematiquement coupes au breakeven avant d'atteindre leur potentiel. Les commissions et swaps n'etaient pas couverts.

2. **Time exit arbitraire** : un chronometre de 120 minutes fermait mecaniquement les positions stagnantes, sans considerer le contexte de la structure de marche. Une consolidation saine (ex: drapeau haussier de 2h) etait traitee de la meme facon qu'une vraie stagnation.

3. **Filtres anti-tendance aveugles au regime** : les filtres RSI > 75 et Bollinger position > 100% bloquaient systematiquement les entrees, meme en tendance forte ou le RSI peut rester surachete pendant des heures et le prix surfer sur les bandes de Bollinger sans jamais corriger. Cela faisait manquer les moves explosifs les plus rentables.

4. **Rejet silencieux des modifications SL par MT5** : le bot modifiait le stop loss sans verifier la distance minimale imposee par le broker (`trade_stops_level`). MT5 rejette silencieusement les ordres SLTP quand le nouveau niveau est trop proche du prix courant. Le bot croyait avoir securise la position, alors que le SL etait reste a son niveau d'origine.

## Decision

Implementer quatre correctifs cibles dans `src/ai/strategy.py` et `src/ai/prompts.py`.

### 1. Breakeven a 1.2R

**Fichier** : `src/ai/strategy.py` - `_apply_breakeven()`

Remplacer le seuil de 0.5R par 1.2R (120% de la distance SL initiale).

```python
# v3.0: Breakeven a 1.2R (couvre commissions/swaps + marge de respiration)
if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl < entry_price:
    _modify_sl(ticket, entry_price)
```

**Justification** :
- 1.2R donne au trade assez d'espace pour traverser le bruit normal du marche
- Couvre les commissions (~0.06R sur EURUSD) et les swaps accumules
- Reduit l'epidemie de zero-win sans compromettre la protection du capital

### 2. Time exit base sur la structure de marche

**Fichier** : `src/ai/strategy.py` - `_check_time_exit()`

Remplacer le timer arbitraire de 120 minutes par une logique de structure de marche :

```
BUY:  fermer si prix < SMA20  OU  swing low recent < swing low precedent (HL cassee)
SELL: fermer si prix > SMA20  OU  swing high recent > swing high precedent (LH cassee)
Tous: securite absolue si age > 4h ET P&L quasi nul (< 0.50)
```

```python
# Calcul SMA20 depuis les 20 dernieres bougies M15
rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 20)
sma20 = sum(close_prices) / 20

# Structure HL/LH
recent_low = min(lows[-5:])    # Swing low des 5 dernieres bougies
prior_low = min(lows[-10:-5])  # Swing low des 5 bougies precedentes
```

**Justification** :
- La structure de marche (HH/HL pour tendance haussiere, LH/LL pour tendance baissiere) est un indicateur plus fiable qu'un timer arbitraire
- Une consolidation saine ne casse pas la structure - le trade peut respirer
- La SMA20 sert de ligne de tendance rapide : la casser signifie que la dynamique a change
- La securite 4h empeche un trade zombie de rester ouvert indefiniment
- Fallback sur le chronometre 4h si les donnees de rates MT5 sont indisponibles

### 3. Filtres anti-tendance conditionnes a l'ADX

**Fichier** : `src/ai/strategy.py` - `_passes_trade_filters()`

Conditionner les filtres RSI/Bollinger au regime de marche mesure par l'ADX :

```python
if adx <= 25:  # Ranging: mean-reversion valide
    if action == "BUY" and rsi > 75:   return False  # bloque
    if action == "SELL" and rsi < 25:  return False  # bloque
elif adx > 25:  # Trending: trend-following, RSI peut rester extreme
    # Filtres desactives - logger un message debug
```

**Justification** :
- ADX <= 25 = ranging : le prix oscille dans un range, les extremes RSI sont effectivement des points de retournement - mean-reversion fonctionne
- ADX > 25 = trending : le prix suit une direction, le RSI peut rester surachete/survendu pendant des heures sans corriger - les filtres mean-reversion sont contre-productifs
- Les moves les plus rentables en Forex sont les tendances fortes ou le prix surfe sur les bandes de Bollinger et le RSI reste > 75 pendant toute la jambe

### 4. Verification trade_stops_level du broker

**Fichier** : `src/ai/strategy.py` - `_modify_sl()`

Verifier la distance minimale autorisee par le broker avant toute modification de SL :

```python
stops_level = sym_info.trade_stops_level * sym_info.point
distance_from_bid = tick.bid - new_sl
if distance_from_bid < stops_level and new_sl < tick.bid:
    logger.warning("SL rejete: distance < stops_level broker")
    return  # Ne pas envoyer l'ordre MT5
```

**Justification** :
- `trade_stops_level` est une propriete du symbole dans MT5 qui definit la distance minimale entre un ordre stop et le prix courant
- Sans cette verification, MT5 rejette silencieusement la modification : le bot pense avoir securise la position alors que le SL est reste inchange
- La verification est faite dans `_modify_sl()` pour couvrir a la fois le breakeven et le trailing stop

### 5. Prompts semantiques pour le LLM

**Fichier** : `src/ai/prompts.py` - `_format_indicators_v2()`

Remplacer les valeurs brutes d'indicateurs par des etats semantiques interpretes :

| Avant (v2.0) | Apres (v3.0) |
|---|---|
| `RSI 14: 78.2` | `RSI 14: 78.2 - Zone de SURACHAT (pression acheteuse extreme)` |
| `BB Position: 98.5` | `Prix SUR LA BANDE SUPERIEURE (surf haussier, possible cassure)` |
| `ATR 14: 0.00152` | `ATR 14: 0.00152 - VOLATILITE ELEVEE (0.52% du prix)` |
| `MACD: 0.00012, Signal: 0.00008` | `MACD au-dessus du Signal (momentum haussier) en zone positive` |

**Justification** : Les LLMs sont des moteurs de logique semantique, pas des calculateurs mathematiques. Leur fournir des concepts interpretes ("SURACHAT", "surf haussier", "VOLATILITE ELEVEE") donne de meilleurs resultats que des nombres bruts, car le modele peut correler ces etats entre eux pour inferer un scenario de marche coherent.

## Alternatives considerees

| Changement | Alternative | Pourquoi rejete |
|---|---|---|
| Breakeven | Garder 0.5R | Cause l'epidemie de zero-win sur Forex/XAUUSD volatils |
| Breakeven | Passer a 2R | Trop conservateur, les trades gagnants ne sont jamais securises |
| Time exit | Sortie basee ATR uniquement | L'ATR ne capture pas la structure de marche (HH/HL, LH/LL) |
| Time exit | Sortie basee RSI | Le RSI peut rester extrême en tendance, generant des sorties prematurees |
| Filtres ADX | Supprimer completement les filtres RSI/BB | Perd la protection en ranging, ou les retournements RSI sont fiables |
| Stops level | Verifier dans chaque appelant | Duplication de code ; centraliser dans `_modify_sl` est plus sur |

## Consequences

### Positives
- **Breakeven 1.2R** : les trades gagnants survivent au bruit normal du marche et atteignent leur potentiel
- **Time exit structure** : les consolidations saines ne declenchent plus de sortie prematuree ; les vrais retournements sont detectes plus rapidement
- **Filtres ADX** : le bot peut enfin trader les tendances fortes (les moves les plus rentables), sans bloquer les entrees sur des extremes RSI
- **Stops level broker** : plus de faux sentiment de securite - le bot sait exactement quand MT5 accepte ou rejette une modification SL
- **Prompts semantiques** : decisions LLM plus nuancees et mieux contextualisees

### Negatives
- **Breakeven plus tardif** : le trade est vulnerable plus longtemps avant d'etre securise (compromis : potentiel de gain vs protection)
- **Time exit structure** : necessite 20 bougies M15 de donnees MT5 (5h d'historique), indisponible en debut de session
- **Filtres ADX** : en tendance, le bot peut entrer sur un RSI extreme qui finit par corriger violemment (risque de retournement)
- **Stops level** : si le `trade_stops_level` change dynamiquement (broker different, compte different), le comportement change sans modification de code

### Neutres
- Le breakeven et le time exit restent non configurables (hardcodes) - un fichier de configuration serait souhaitable pour le futur
- La securite 4h du time exit est un filet de securite qui ne devrait jamais etre atteint si la structure fonctionne correctement
- Les prompts semantiques peuvent etre etendus a d'autres indicateurs (Ichimoku, Pivots) dans une future version

## Suivi

Revoir ces decisions si :
- Le win rate ne s'ameliore pas apres 2 semaines de trading live avec v3.0
- Le breakeven 1.2R laisse trop de trades se retourner en pertes (surveiller le ratio trades breaches / trades gagnants)
- Les filtres ADX laissent passer des entrees en fausse tendance (ADX > 25 mais prix en range etroit)
- Un nouveau broker avec des `trade_stops_level` differents est ajoute
- Un modele LLM local devient disponible et peut etre teste avec les prompts semantiques vs bruts
