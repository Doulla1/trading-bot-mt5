# Module Data : calendar.py, database.py, models.py

## Vue d'ensemble

Le module `src/data/` gere les donnees du bot : scraping du calendrier economique, persistance SQLite et modeles de donnees.

```
src/data/
  __init__.py
  calendar.py     # Scraping ForexFactory
  database.py     # SQLite singleton + CRUD
  models.py       # Dataclasses
```

## `calendar.py` - Calendrier economique (v1.1)

**Fichier** : `src/data/calendar.py`

### `fetch_events() -> list[dict]`

Recupere les evenements economiques depuis ForexFactory avec cache SQLite (TTL 4h).

**Algorithme** :

1. **Cache** : tente de charger depuis `calendar_cache` (valide 4h)
2. **Si cache manquant** : requete HTTP GET sur `https://www.forexfactory.com/calendar`
3. **Parsing HTML** avec `BeautifulSoup(lxml)`
4. **Pour chaque ligne** `calendar__row` : extraction impact (via `_parse_impact()`), devise, nom, heure
5. **Sauvegarde** dans le cache SQLite
6. **Retour** de la liste des evenements

**Fonctions internes** :

| Fonction | Role |
|---|---|
| `_load_from_cache(date, now)` | Charge les evenements depuis `calendar_cache` si TTL valide |
| `_save_to_cache(date, events, now)` | Persiste les evenements dans `calendar_cache` |
| `_scrape_forexfactory()` | Telecharge et parse la page ForexFactory |
| `_parse_calendar_row(row)` | Extrait un evenement d'une ligne HTML |
| `_parse_impact(row)` | Determine l'impact (high/medium/low) via les classes CSS |

**Headers HTTP** :

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
```

**Timeout** : 15 secondes. En cas d'echec, retourne une liste vide (fallback).

### `filter_relevant_events(events, symbol="EURUSD") -> list[dict]`

Filtre les evenements par devise du symbole de trading.

```python
currencies = [symbol[:3], symbol[3:]]  # EUR, USD
return [ev for ev in events if ev.get("impact") in ("high", "medium") and ev.get("currency") in currencies]
```

- Ne conserve que les evenements HIGH et MEDIUM
- Filtre par devise (ex: EURUSD conserve les evenements EUR et USD)

### `_fallback_events() -> list`

Retourne une liste vide quand le scraping echoue. Le bot continue sans donnees calendaires.

---

## `database.py` - Base de donnees SQLite

**Fichier** : `src/data/database.py`

### Architecture Singleton thread-safe (v1.1)

```python
import threading

_db: Optional[sqlite3.Connection] = None
_db_lock = threading.Lock()

def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = sqlite3.connect(...)
                _init_tables(_db)
    return _db
```

- Connexion unique (singleton) pour toute la duree de vie du bot
- **Thread-safe** : double-check locking avec `threading.Lock()`
- Mode WAL (Write-Ahead Logging) pour de meilleures performances en lecture/ecriture concurrentes
- `row_factory = sqlite3.Row` pour un acces par nom aux colonnes

### Schemas des tables

**Table `trades`** :

```sql
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
    volume REAL NOT NULL,
    opened_at TEXT NOT NULL,
    open_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    confidence INTEGER NOT NULL,
    reasoning TEXT,
    closed_at TEXT,
    close_price REAL,
    profit REAL
);
```

**Table `analysis_logs`** :

```sql
CREATE TABLE IF NOT EXISTS analysis_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    decision_action TEXT NOT NULL,
    decision_confidence INTEGER NOT NULL,
    decision_reasoning TEXT,
    screenshot_path TEXT,
    indicators_snapshot TEXT,
    calendar_snapshot TEXT,
    was_executed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_cache (
    date TEXT PRIMARY KEY,
    events_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
```

**Index** :

```sql
CREATE INDEX IF NOT EXISTS idx_trades_opened ON trades(opened_at);
CREATE INDEX IF NOT EXISTS idx_trades_profit ON trades(profit);
CREATE INDEX IF NOT EXISTS idx_analysis_timestamp ON analysis_logs(timestamp);
```

### Nouvelles tables (v1.1)

| Table | Role | Utilisation |
|---|---|---|
| `bot_state` | Stocke l'etat du circuit breaker (4h de pause apres 4 pertes) | `_set_circuit_breaker_until()` / `_circuit_breaker_active()` |
| `calendar_cache` | Cache TTL 4h des evenements ForexFactory | `_load_from_cache()` / `_save_to_cache()` |

### Fonctions CRUD

| Fonction | Description | Table |
|---|---|---|
| `log_analysis(symbol, timeframe, decision, screenshot_path, indicators, calendar_events, was_executed) -> int` | Enregistre une analyse IA | `analysis_logs` |
| `log_trade_open(ticket, symbol, direction, volume, open_price, stop_loss, take_profit, confidence, reasoning) -> int` | Enregistre l'ouverture d'un trade | `trades` |
| `log_trade_close(ticket, close_price, profit)` | Met a jour un trade avec sa fermeture (appele par `reconcile_closed_positions()`) | `trades` |
| `get_recent_trades(limit=20) -> list[dict]` | Retourne les derniers trades | `trades` |
| `get_statistics() -> dict` | Statistiques (total, wins, losses, win_rate, profit, avg_confidence) | `trades` + `analysis_logs` |

### `get_statistics() -> dict`

```python
{
    "total_closed": 15,       # Nombre de trades fermes
    "wins": 9,                 # Trades gagnants
    "losses": 6,               # Trades perdants
    "win_rate": 60.0,          # % reussite
    "total_profit": 125.50,    # Profit/Pertes cumule
    "avg_confidence": 74.3     # Confiance moyenne de l'IA
}
```

---

## `models.py` - Dataclasses

**Fichier** : `src/data/models.py`

### `Trade`

```python
@dataclass
class Trade:
    ticket: int
    symbol: str
    direction: str
    volume: float
    opened_at: datetime
    open_price: float
    stop_loss: float
    take_profit: float
    confidence: int
    reasoning: str
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    profit: Optional[float] = None
    id: Optional[int] = None
```

### `AnalysisLog`

```python
@dataclass
class AnalysisLog:
    timestamp: datetime
    symbol: str
    timeframe: str
    decision_action: str
    decision_confidence: int
    decision_reasoning: str
    screenshot_path: str
    indicators_snapshot: str
    calendar_snapshot: str
    was_executed: bool
    id: Optional[int] = None
```

Les dataclasses sont utilisees pour le typage statique et la documentation. La persistence reelle est assuree par `database.py` avec des dictionnaires issus de `sqlite3.Row`.
