# Flux de donnees

Ce document decrit les formats de donnees qui transitent entre les modules du bot.

## 1. Donnees OHLCV (MT5 -> Indicateurs)

**Format** : `pandas.DataFrame`

**Source** : `src/mt5/bridge.py` - fonction `get_rates(symbol, timeframe, count=200)`

```python
>>> df = bridge.get_rates("EURUSD", "M15", 200)
>>> df.columns
Index(['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'], dtype='object')
>>> df.dtypes
time           datetime64[ns]
open           float64
high           float64
low            float64
close          float64
tick_volume    int64
spread         int64
real_volume    int64
```

- `time` devient l'index du DataFrame
- 200 bougies par defaut (suffisant pour SMA 50 et RSI 14)
- Les donnees sont telechargees a chaque cycle d'analyse

## 2. Indicateurs calcules (Indicateurs -> IA)

**Format** : `dict[str, float | str | None]`

**Source** : `src/mt5/indicators.py` - fonction `compute_all(df)`

```python
{
    "rsi_14": 58.3,              # RSI 0-100
    "macd_line": 0.00012,         # MACD principale
    "macd_signal": 0.00008,       # Signal line
    "macd_histogram": 0.00004,    # Histogramme
    "sma_20": 1.08450,            # Moyenne 20 periodes
    "sma_50": 1.08210,            # Moyenne 50 periodes
    "bb_upper": 1.08720,          # Bande superieure
    "bb_middle": 1.08450,         # Bande mediane (SMA 20)
    "bb_lower": 1.08180,          # Bande inferieure
    "bb_position_pct": 55.2,      # % position dans les bandes
    "atr_14": 0.00120,            # Volatilite
    "current_price": 1.08480,     # Dernier prix close
    "high_24h": 1.08650,          # Plus haut 24h
    "low_24h": 1.08100,           # Plus bas 24h
    "trend_short": "haussier",    # Court terme
    "trend_medium": "haussier"    # Moyen terme
}
```

- Les valeurs `None` surviennent quand les donnees sont insuffisantes (< 50 bougies)
- Les tendances sont calculees par comparaison aux SMA

## 3. Evenements calendaires (ForexFactory -> IA)

**Format** : `list[dict]`

**Source** : `src/data/calendar.py` - fonctions `fetch_events()` et `filter_relevant_events()`

```python
[
    {
        "time": "08:30",
        "currency": "USD",
        "event": "Non-Farm Employment Change",
        "impact": "high",          # "high", "medium", "low"
        "previous": "243K",
        "forecast": "185K",
        "actual": ""
    }
]
```

- Seuls les evenements HIGH et MEDIUM sont transmis a l'IA
- Filtres par devise (ex: EURUSD conserve EUR et USD)

## 4. Decisions IA (IA -> Strategy)

**Format** : `dict` (JSON)

**Source** : `src/ai/vision.py` - fonction `analyze()`

```python
{
    "action": "BUY",              # BUY | SELL | HOLD | CLOSE
    "confidence": 78,             # 0-100
    "reasoning": "RSI remonte de zone survendue...",
    "stop_loss_pips": 25,         # Entier (pips)
    "take_profit_pips": 45,       # Entier (pips), >= SL * 1.5
    "risk_level": "MEDIUM"        # LOW | MEDIUM | HIGH
}
```

**Validation** : Champs requis verifies avec `re.search()` puis `json.loads()`. Si un champ manque ou que l'action est invalide, la decision est rejetee (retour `None`).

## 5. Ordres de trading (Strategy -> MT5)

**Format** : `dict` (requete MT5)

**Source** : `src/mt5/executor.py` - fonction `open_position()`

```python
{
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": "EURUSD",
    "volume": 0.05,               # Lots calcules
    "type": mt5.ORDER_TYPE_BUY,   # ou ORDER_TYPE_SELL
    "price": 1.08480,             # Prix ask (BUY) ou bid (SELL)
    "sl": 1.08230,                # Stop loss prix absolu
    "tp": 1.08780,                # Take profit prix absolu
    "deviation": 20,              # Slippage max en pips
    "magic": 123456,              # Identifiant du bot
    "comment": "IA confiance=78%",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC
}
```

## 6. Resultat de trade (MT5 -> Strategy -> Database)

**Format** : `TradeResult` (dataclass)

**Source** : `src/mt5/executor.py`

```python
@dataclass
class TradeResult:
    success: bool          # True si l'ordre a ete accepte
    ticket: int | None     # Numero du ticket MT5
    volume: float          # Lots executes
    price: float           # Prix d'execution
    stop_loss: float       # Prix SL
    take_profit: float     # Prix TP
    comment: str           # Commentaire
    error: str | None      # Message d'erreur si echec
```

## 7. Screenshots (MT5 -> Disque -> IA)

**Format** : Fichier PNG 800x600

**Source** : `src/mt5/screenshots.py` - fonction `capture_chart()`

- Stockage : `data/screenshots/EURUSD_20260601_143000.png`
- Taille moyenne : ~200-400 KB par image
- Retention : 48 heures (nettoyage automatique)
- Encodage : converti en base64 avant envoi a l'API

## 8. Base de donnees SQLite

**Fichier** : `data/trading.db`

**Tables** :

### Table `trades`

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER NOT NULL,             -- Ticket MT5
    symbol TEXT NOT NULL,                -- EX: EURUSD
    direction TEXT NOT NULL,             -- BUY / SELL
    volume REAL NOT NULL,                -- Lots
    opened_at TEXT NOT NULL,             -- ISO datetime
    open_price REAL NOT NULL,            -- Prix ouverture
    stop_loss REAL NOT NULL,             -- Prix SL
    take_profit REAL NOT NULL,           -- Prix TP
    confidence INTEGER NOT NULL,         -- 0-100
    reasoning TEXT,                      -- Texte IA
    closed_at TEXT,                      -- ISO datetime (NULL si ouvert)
    close_price REAL,                    -- Prix fermeture
    profit REAL                          -- P&L (NULL si ouvert)
);
```

### Table `analysis_logs`

```sql
CREATE TABLE analysis_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,              -- ISO datetime
    symbol TEXT NOT NULL,                 -- EURUSD
    timeframe TEXT NOT NULL,              -- M15
    decision_action TEXT NOT NULL,        -- BUY/SELL/HOLD/CLOSE
    decision_confidence INTEGER NOT NULL, -- 0-100
    decision_reasoning TEXT,              -- Texte IA
    screenshot_path TEXT,                 -- Chemin PNG
    indicators_snapshot TEXT,             -- JSON indicateurs
    calendar_snapshot TEXT,               -- JSON evenements
    was_executed INTEGER NOT NULL DEFAULT 0  -- 0/1
);
```

## Diagramme de flux global

```mermaid
flowchart LR
    MT5_OHLCV[MT5 OHLCV] -->|DataFrame| IND[Indicateurs]
    IND -->|dict| AI[GPT-4o-mini]
    MT5_SS[MT5 Screenshot] -->|PNG file| AI
    FF[ForexFactory] -->|list[dict]| AI
    AI -->|JSON decision| STRAT[Strategy]
    STRAT -->|TradeResult| DB[(SQLite)]
    STRAT -->|ORDER| MT5_EXEC[MT5 Execution]
    MT5_EXEC -->|confirmation| DB

    style AI fill:#f9f,stroke:#333,stroke-width:2px
    style DB fill:#bbf,stroke:#333
    style STRAT fill:#bfb,stroke:#333
```
