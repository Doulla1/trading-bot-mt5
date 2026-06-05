# Regles de gestion des risques

La gestion des risques est le coeur du bot. Elle est implantee dans `src/ai/strategy.py` (fonction `execute_decision()`) et appliquee **avant chaque execution** d'ordre.

## Regles appliquees

```mermaid
flowchart TD
    A[Decision DeepSeek] --> B{Marche ouvert ?}
    B -- Non --> C[Cycle annule]
    B -- Oui --> D{Perte jour flottante < 3% ?}
    D -- Non --> E[Trade bloque]
    D -- Oui --> F{Circuit breaker actif ?}
    F -- Oui --> G[Trade bloque - pause 4h]
    F -- Non --> H{Action CLOSE ?}
    H -- Oui --> I[Fermer toutes les positions]
    H -- Non --> J{Action BUY/SELL ?}
    J -- Non --> K[HOLD - pas d'action]
    J -- Oui --> L{Symbole desactive ?}
    L -- Oui --> M[Trade bloque - XAUUSD exclu]
    L -- Non --> N{Marche en range ? ADX < 25 x3}
    N -- Oui --> O[HOLD force - anti-range]
    N -- Non --> P{Spread <= 30 ?}
    P -- Non --> Q[Trade ignore]
    P -- Oui --> R{Confiance >= 70% ?}
    R -- Non --> S[Trade ignore]
    R -- Oui --> T{Max positions < 1 ?}
    T -- Non --> U[Trade ignore]
    T -- Oui --> V{Hard SL Floor: SL >= min_sl ?}
    V -- Non --> W[SL force au minimum]
    W --> X[Executer ordre + SL/TP]
    V -- Oui --> X
    X --> Y[Gestion active: Breakeven 1.2R, Trailing, Time Exit structure]
```

### 1. Marche ouvert

**Fichier** : `src/mt5/bridge.py` - fonction `is_market_open()`

```python
def is_market_open() -> bool:
    selected = mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    return info.trade_time != 0
```

- Verifie que le symbole est disponible dans MarketWatch
- Verifie que le trading est autorise (weekend, jours feries, overnight)

### 2. Limite de perte journaliere

**Regle** : Perte maximale de **3% du capital** par jour.

```python
daily_pnl = _get_daily_pnl()
daily_loss_pct = abs(daily_pnl) / balance * 100
if daily_loss_pct >= max_daily_loss_pct:  # 3%
    logger.warning("LIMITE PERTE JOURNALIERE ATTEINTE")
    return  # Aucun trade
```

- Calcule le P&L du jour depuis la table `trades` (SUM des profits des trades fermes aujourd'hui)
- Si la limite est atteinte, **tous les trades sont bloques** jusqu'au jour suivant
- Configurable via `MAX_DAILY_LOSS_PCT` dans le `.env`

### 3. Confiance minimale

**Regle** : Ne trader que si la confiance de l'IA est >= **70%**.

```python
if confidence < settings.min_confidence_threshold:  # 70
    logger.info(f"Confiance {confidence}% < seuil {min_confidence}%")
    return
```

- Les actions BUY/SELL avec confidence < 70% sont ignorees
- Les actions HOLD et CLOSE ne sont pas concernees par cette regle
- Configurable via `MIN_CONFIDENCE_THRESHOLD`

### 4. Nombre maximum de positions

**Regle** : Maximum **1 position ouverte** a la fois.

```python
if count_open_positions() >= settings.max_open_positions:  # 1
    logger.info("Max positions atteint")
    return
```

- Evite le sur-trading et la concentration de risque
- Configurable via `MAX_OPEN_POSITIONS`

### 5. Risque maximum par trade

**Regle** : Ne pas risquer plus de **1% du capital** par trade.

```python
risk_amount = account_balance * (risk / 100)  # risk = 1%
volume = risk_amount / (sl_price_distance * point_value / pip_size * 10)
volume = max(0.01, round(volume, 2))
```

- Le volume (lots) est calcule automatiquement en fonction de la distance du stop loss
- Plus le SL est serre, plus le volume peut etre eleve (et vice versa)
- Configurable via `MAX_RISK_PER_TRADE_PCT`

### 6. Stop loss obligatoire

**Regle** : Tout ordre BUY/SELL doit avoir un **stop loss** defini.

- Aucun trade n'est execute sans SL
- Le SL est fourni par l'IA dans la decision (`stop_loss_pips`)
- Fourchette recommandee : 15-50 pips selon la volatilite
- Le SL est converti en prix absolu en fonction du `point` et `digits` du symbole

### 7. Take profit minimum

**Regle** : Le take profit doit etre au moins **1.5 fois** le stop loss.

- Applique dans le prompt IA (instruction donnee a GPT-4o-mini)
- Garantit un ratio risque/recompense (R/R) d'au moins 1:1.5
- Exemple : SL a 20 pips -> TP minimum a 30 pips

### 8. Ordre CLOSE

**Regle** : Si l'IA decide CLOSE, **toutes** les positions ouvertes sont fermees.

```python
if action == "CLOSE":
    for pos in get_open_positions():
        close_position(pos["ticket"])
```

- Utile en cas de retournement de tendance ou d'evenement economique majeur
- Ne tient pas compte de la confiance (CLOSE est toujours execute)

### 9. Filtre de spread (v1.1)

**Regle** : Ne pas ouvrir de trade si le spread depasse **30 points** (3 pips sur EURUSD).

- Applique dans `_passes_trade_filters()`
- Evite de trader pendant les periodes de faible liquidite

### 10. Circuit breaker (v1.1)

**Regle** : Apres **4 pertes consecutives**, pause de **4 heures**.

- Implante via `_count_consecutive_losses()` et `_circuit_breaker_active()`
- Etat persiste dans la table `bot_state` (survit aux redemarrages)

### 11. Limite de perte flottante (v1.1)

**Regle** : La perte journaliere inclut les pertes **flottantes** (positions ouvertes non fermees).

- `_get_daily_pnl()` somme les trades fermes + `mt5.positions_get()` floating P&L
- Evite d'ouvrir un nouveau trade quand le compte est deja en drawdown

### 12. Reconciliation automatique des trades (v1.1)

**Regle** : A chaque cycle, le bot detecte les positions fermees par SL/TP dans MT5.

- `reconcile_closed_positions()` dans le scheduler
- Met a jour la table `trades` (closed_at, close_price, profit)

### 13. Blocage news HIGH impact (v1.1)

**Regle** : Si une news HIGH impact est prevue, le cycle saute l'execution.

- `_has_high_impact_news_soon()` verifie les evenements du calendrier
- Protege contre la volatilite extreme (NFP, CPI, decisions de taux)

### 14. Breakeven a 1.2R (v3.0)

**Regle** : Le stop loss est deplace au prix d'entree (breakeven) quand le profit atteint **120% du SL initial** (1.2R).

```python
# v3.0: Breakeven a 1.2R (couvre commissions/swaps + marge de respiration)
if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl < entry_price:
    _modify_sl(ticket, entry_price)
```

- **Avant v3.0** : breakeven a 0.5R (trop agressif pour Forex/XAUUSD)
- **Apres v3.0** : breakeven a 1.2R - laisse le trade respirer au-dessus du bruit de marche
- Couvre les commissions et swaps avant de securiser la position
- Evite l'epidemie de "zero-win" ou le breakeven coupe systematiquement les trades gagnants

### 15. Time Exit base sur la structure de marche (v3.0)

**Regle** : Les positions stagnantes sont fermees si la structure de marche s'inverse contre le trade (et non plus apres un delai arbitraire).

```python
def _check_time_exit(pos) -> bool:
    # BUY: ferme si prix cloture sous SMA20 OU structure Higher Low cassee
    # SELL: ferme si prix cloture au-dessus SMA20 OU structure Lower High cassee
    # Securite: stagnation totale >4h (quelle que soit la direction)
```

**Logique de sortie** :

| Type de position | Condition de sortie |
|---|---|
| BUY | Prix < SMA20 (casse la tendance haussiere) |
| BUY | Swing low recent < swing low precedent (structure HL cassee) |
| SELL | Prix > SMA20 (casse la tendance baissiere) |
| SELL | Swing high recent > swing high precedent (structure LH cassee) |
| Tous | Age > 4h ET P&L quasi nul (< 0.50) - securite absolue |

### 16. Hard SL Floor (v4.1)

**Regle** : Le SL ne peut JAMAIS etre inferieur au minimum defini par symbole dans `_ATR_SL_CONFIG`.

Meme si `_get_atr_based_sl_tp()` calcule theoriquement un SL >= `min_sl`, un deuxieme controle imperatif est effectue juste avant l'execution de l'ordre. Si le SL est en dessous du minimum, il est force a `min_sl` et un avertissement est loggue.

```python
cfg_floor = _ATR_SL_CONFIG.get(sym, _ATR_SL_CONFIG["EURUSD"])
if stop_loss_pips < cfg_floor["min_sl"]:
    logger.warning(f"SL HARD FLOOR pour {sym}: {stop_loss_pips} -> {cfg_floor['min_sl']} pips")
    stop_loss_pips = cfg_floor["min_sl"]
    take_profit_pips = max(take_profit_pips, cfg_floor["min_tp"], int(stop_loss_pips * cfg_floor["tp_ratio"]))
```

**Minimums SL par symbole (v4.1)** :

| Symbole | min_sl (pips) | Changement v4.1 |
|---|---|---|
| XAUUSD | 150 | - |
| EURUSD | 15 | - |
| GBPUSD | 25 | 18 → 25 |
| AUDUSD | 15 | - |
| USDJPY | 30 | 20 → 30 |
| USDCHF | 15 | - |

**Probleme resolu** : l'IA suggerait SL=20 pips sur XAUUSD, ce qui etait systematiquement stoppe par le bruit normal de l'or (~150 pips de volatilite). Le Hard Floor empeche ces SL irrealistes quel que soit le chemin de code.

### 17. Filtre Anti-Range (v4.1)

**Regle** : Bloquer tous les BUY/SELL quand le marche est detecte comme etant en range (sans tendance directionnelle) depuis 3+ periodes d'analyse.

**Algorithme** : la fonction `_is_ranging_market()` suit l'ADX par symbole :

- ADX >= 25 : marche directionnel → compteur reset, trading autorise
- ADX < 25 : marche potentiellement rangeant → compteur +1
- Compteur >= 3 : marche en range confirme → HOLD force, pas de BUY/SELL

```python
_RANGING_ADX_THRESHOLD: float = 25.0
_RANGING_CONSECUTIVE_BARS: int = 3
_ranging_state: dict[str, int] = {}  # sym -> compteur de periodes ADX < seuil
```

**Justification** : dans un marche sans tendance, le prix oscille entre support et resistance sans direction claire. Les signaux de l'IA sont moins fiables dans ces conditions (taux d'echec eleve sur les analyses du 03-05 Juin 2026).

### 18. XAUUSD temporairement desactive (v4.1)

**Regle** : L'or (XAUUSD) est temporairement exclu du trading. Toute decision BUY/SELL est bloquee dans `_passes_trade_filters()`.

```python
_DISABLED_SYMBOLS: set[str] = {"XAUUSD"}

if settings.trading_symbol in _DISABLED_SYMBOLS:
    logger.info(f"Symbole {settings.trading_symbol} temporairement desactive - pas d'execution")
    return False
```

**Justification** : XAUUSD a accumule -10.15 de pertes sur 5 trades (tous perdants) entre le 03 et le 05 Juin 2026. Le modele IA actuel ne capture pas correctement :
- La volatilite intraday extreme de l'or (ATR ~450 pips, contre ~10 pips pour EURUSD)
- La correlation inverse avec le Dollar Index (DXY)
- Les flux safe-haven qui invalident l'analyse technique classique

Reactivation prevue apres fine-tuning specifique a l'or.

- **Avant v3.0** : timer arbitraire de 120 minutes (ferme mecaniquement les perdants)
- **Apres v3.0** : logique de structure de marche - laisse les consolidations saines respirer
- Fallback sur le chronometre 4h si les donnees MT5 (rates) sont indisponibles

### 16. Filtres anti-tendance conditionnes a l'ADX (v3.0)

**Regle** : Les filtres RSI/Bollinger Band ne sont appliques qu'en regime de ranging (ADX <= 25). En tendance (ADX > 25), ils sont desactives.

```python
# v3.0: Filtres RSI/BB conditionnes au regime de marche
if adx <= 25:  # Ranging: appliquer les filtres mean-reversion
    if action == "BUY" and rsi > 75:   # bloque
    if action == "SELL" and rsi < 25:  # bloque
elif adx > 25:  # Trending: desactiver les filtres
    # Le RSI peut rester surachete/survendu pendant des heures en tendance
```

- **Avant v3.0** : RSI > 75 ou BB_position > 100% bloquaient systematiquement les entrees
- **Apres v3.0** : en tendance forte, le RSI peut rester surachete pendant des heures et le prix surfer sur les bandes de Bollinger - le bot ne bloque PLUS ces entrees
- Evite de manquer les moves explosifs ou le prix ne corrige jamais

## Tableau recapitulatif

| Regle | Valeur | Fichier | Configurable |
|---|---|---|---|
| Risque max par trade | 1% du capital | `executor.py` | `MAX_RISK_PER_TRADE_PCT` |
| Perte journaliere max | 3% du capital (realise + flottant) | `strategy.py` | `MAX_DAILY_LOSS_PCT` |
| Positions max | 1 | `strategy.py` | `MAX_OPEN_POSITIONS` |
| Confiance minimale | 70% | `strategy.py` | `MIN_CONFIDENCE_THRESHOLD` |
| Stop loss | Obligatoire | `executor.py` | Non (fourni par IA) |
| Take profit | >= 1.5x SL | `vision.py` (validation) | Non |
| Deviation max | 20 pips | `executor.py` | Non (hardcode) |
| Magic number | Configurable | `executor.py` | `MT5_MAGIC_NUMBER` |
| Spread max | 30 points | `strategy.py` | Non (hardcode) |
| Circuit breaker | 4 pertes consecutives / 4h pause | `strategy.py` | Non (hardcode) |
| Reconciliation | A chaque cycle | `scheduler.py` | Non |
| News HIGH impact | Bloque execution | `scheduler.py` | Non |
| Breakeven | 1.2R (120% du SL initial) | `strategy.py` | Non (hardcode) |
| Time exit | Structure de marche (SMA20 + HH/HL) + securite 4h | `strategy.py` | Non (hardcode) |
| Filtres RSI/BB | ADX-conditionnes (ranging uniquement) | `strategy.py` | Non (hardcode) |
| Stops level broker | Verifie `trade_stops_level` avant modif SL | `strategy.py` | Non (hardcode) |
