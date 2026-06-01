# Module MT5 : bridge.py, executor.py, indicators.py, screenshots.py

## Vue d'ensemble

Le module `src/mt5/` est l'interface entre le bot et MetaTrader 5. Il est divise en 4 fichiers specialises.

```
src/mt5/
  __init__.py
  bridge.py         # Connexion, donnees, infos compte
  executor.py       # Ordres de trading
  indicators.py     # Calculs indicateurs techniques
  screenshots.py    # Capture d'ecran
```

## `bridge.py` - Connexion et donnees MT5

**Fichier** : `src/mt5/bridge.py`

### `connect() -> bool`

Etablit la connexion au terminal MT5 avec les identifiants du `.env`.

```python
if not mt5.initialize(login=settings.mt5_login, password=settings.mt5_password, server=settings.mt5_server):
    return False
return True
```

**Retour** : `True` si connecte, `False` avec message d'erreur dans les logs.

### `disconnect() -> None`

Ferme proprement la connexion MT5.

```python
mt5.shutdown()
```

### `get_account_info() -> dict | None`

Retourne les informations du compte de trading.

```python
info = mt5.account_info()
return info._asdict()  # balance, equity, margin, profit, etc.
```

**Retour** : Dictionnaire avec les champs MT5 (`balance`, `equity`, `margin`, `margin_free`, `profit`, etc.) ou `None` si echec.

### `get_rates(symbol, timeframe, count=200) -> pd.DataFrame`

Recupere les donnees OHLCV historiques.

```python
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
}
rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df.set_index("time", inplace=True)
```

**Parametres** :
- `symbol` : defaut `TRADING_SYMBOL` du `.env`
- `timeframe` : defaut `TRADING_TIMEFRAME`
- `count` : nombre de bougies (defaut 200)

**Retour** : DataFrame avec index temporel, colonnes `open`, `high`, `low`, `close`, `tick_volume`, `spread`, `real_volume`.

### `get_current_price(symbol) -> float | None`

Retourne le prix bid actuel.

```python
tick = mt5.symbol_info_tick(sym)
return tick.bid
```

### `get_symbol_info(symbol) -> dict | None`

Proprietes du symbole de trading.

```python
info = mt5.symbol_info(sym)
return info._asdict()  # point, digits, spread, trade_tick_value, etc.
```

Champs importants :
- `point` : plus petit increment de prix (ex: 0.00001 pour EURUSD)
- `digits` : nombre de decimales (ex: 5)
- `trade_tick_value` : valeur du tick pour le calcul de position

### `is_market_open() -> bool`

Verifie si le marche est ouvert pour le symbole via `trade_mode` (v1.1).

```python
info = mt5.symbol_info(sym)
# SYMBOL_TRADE_MODE_FULL = 4 = trading complet autorise
return info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL
```

> **v1.1** : Correction du bug `trade_time` (qui indiquait l'heure du dernier trade, pas l'ouverture). Remplace par `trade_mode`.

---

## `executor.py` - Ordres de trading

**Fichier** : `src/mt5/executor.py`

### `TradeResult` (dataclass)

```python
@dataclass
class TradeResult:
    success: bool
    ticket: int | None
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    comment: str
    error: str | None
```

### `calculate_position_size(account_balance, stop_loss_pips, symbol_info, risk_pct=None) -> float`

Calcule le volume en lots selon la regle de gestion des risques.

```python
risk = risk_pct or settings.max_risk_per_trade_pct  # 1%
risk_amount = account_balance * (risk / 100)
point_value = symbol_info.get("trade_tick_value", 1.0)
pip_size = 10 * symbol_info.get("point", 0.00001)
sl_price_distance = stop_loss_pips * pip_size
lots = risk_amount / (sl_price_distance * point_value / pip_size * 10)
lots = max(0.01, round(lots, 2))
```

### `open_position(direction, volume, stop_loss, take_profit, symbol, comment) -> TradeResult`

Ouvre une position BUY ou SELL.

- **BUY** : utilise le prix `ask`, SL calcule depuis l'ASK
- **SELL** : utilise le prix `bid`, SL calcule depuis le BID
- **Protection tick** : retourne `TradeResult(error=...)` si `mt5.symbol_info_tick()` est None
- Deviation : 20 pips (slippage maximum accepte)
- Magic number : configurable via `MT5_MAGIC_NUMBER` dans le `.env` (defaut `123456`)
- Type d'ordre : `ORDER_FILLING_IOC` (Immediate or Cancel)

### `close_position(ticket, symbol) -> TradeResult`

Ferme une position existante identifiee par son ticket MT5.

- Position BUY -> ordre SELL (et vice versa)
- Verifie que la position existe avant d'envoyer l'ordre

### `get_open_positions(symbol) -> list[dict]`

Retourne les positions ouvertes pour un symbole.

### `count_open_positions(symbol) -> int`

Compte le nombre de positions ouvertes.

---

## `indicators.py` - Indicateurs techniques

**Fichier** : `src/mt5/indicators.py`

### `compute_all(df) -> dict`

Fonction principale qui execute tous les calculs. Voir [Cycle d'analyse](../../2-fonctionnel/cycle-analyse.md) pour le detail de chaque indicateur.

**Contraintes** :
- Minimum 50 bougies requises (sinon retourne `{}`)
- Toutes les operations sont vectorisees via pandas/NumPy

### Methodes internes

| Fonction | Description |
|---|---|
| `_rsi(close, period=14)` | RSI avec EMA du gain/perte moyen |
| `_macd(close, fast=12, slow=26, signal=9)` | MACD avec EMA exponentielles |
| `_bollinger_bands(close, period=20, std_dev=2)` | Bandes de Bollinger |
| `_atr(high, low, close, period=14)` | Average True Range |

---

## `screenshots.py` - Capture d'ecran (v1.1)

**Fichier** : `src/mt5/screenshots.py`

### `capture_chart(symbol) -> Path | None`

Capture un screenshot du moniteur principal via la bibliotheque `mss`.

```python
import mss
with mss.mss() as sct:
    monitor = sct.monitors[1]
    screenshot = sct.grab(monitor)
    mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
```

> **v1.1** : Correction du bug `mt5.screen_shot()` (methode inexistante dans l'API Python MT5). Remplace par `mss`.

- Moniteur principal capture
- Format : PNG
- Nom : `{SYM}_{YYYYMMDD_HHMMSS}.png`
- Dossier : `data/screenshots/` (cree automatiquement)

### `cleanup_old_screenshots(max_age_hours=24) -> int`

Supprime les screenshots plus vieux que `max_age_hours` heures. Appele automatiquement a la fin de chaque cycle d'analyse.
