# Module Data : calendar.py, investing_calendar.py, database.py, models.py

## Vue d'ensemble

Le module `src/data/` gere les donnees du bot : scraping du calendrier economique (cascade multi-sources), persistance SQLite et modeles de donnees.

```
src/data/
  __init__.py
  calendar.py              # Orquestrateur calendrier (cascade multi-sources)
  investing_calendar.py    # Scrapeur Investing.com (Playwright)
  database.py              # SQLite multi-symboles (v4.1) + CRUD
  models.py                # Dataclasses
```

## Architecture multi-symboles (v4.1)

### Probleme resolu : contamination entre bases de donnees

Avant v4.1, le bot multi-symboles (`run_multi.py`) ecrivait certains trades dans `data/eurusd/trading.db` quel que soit le symbole reellement trade. La cause etait que `get_db()` utilisait toujours `settings.db_path` (pointe vers `data/{trading_symbol}/trading.db`) et que `trading_symbol` n'etait pas correctement propage lors des appels depuis le scheduler.

### Solution : `get_db(symbol=...)` explicite

```python
def get_db(symbol: str | None = None) -> sqlite3.Connection:
    """Retourne la connexion SQLite pour un symbole donne.
    v4.1: Accepte un symbole explicite pour eviter la contamination entre DB."""
    if symbol is not None:
        sym_dir = symbol.lower()
        path = str(settings.project_root / "data" / sym_dir / "trading.db")
    else:
        path = str(settings.db_path)  # retrocompatibilite
```

**Exemple de routage** :

| Appel | Chemin DB |
|---|---|
| `get_db(symbol="EURUSD")` | `data/eurusd/trading.db` |
| `get_db(symbol="GBPUSD")` | `data/gbpusd/trading.db` |
| `get_db(symbol="XAUUSD")` | `data/xauusd/trading.db` |
| `get_db()` (sans argument) | `data/{trading_symbol}/trading.db` (retrocompatibilite) |

### Fonctions impactees

| Fonction | Changement v4.1 |
|---|---|
| `get_db(symbol)` | Accepte un parametre `symbol` optionnel |
| `log_trade_open(..., symbol)` | Passe `symbol` a `get_db()` pour ecrire dans la bonne DB |
| `log_trade_close(..., symbol)` | Passe `symbol` a `get_db()` pour ecrire dans la bonne DB |
| `reconcile_closed_positions(sym)` | Passe `sym` a `get_db()` et `log_trade_close()` |
| `run_symbol(cfg)` | Passe `cfg["symbol"]` a `log_trade_open()` |

## `calendar.py` - Orquestrateur calendrier economique (v3.0)

**Fichier** : `src/data/calendar.py`

### Strategie de cascade

Le calendrier utilise une cascade a 4 niveaux pour garantir la disponibilite des donnees :

```
Cache SQLite (TTL 4h)
    -> Investing.com (Playwright, Chromium headless)
        -> ForexFactory (httpx + BeautifulSoup)
            -> Evenements statiques (fallback ultime)
```

Chaque niveau sert de filet de securite au precedent. En cas d'echec, le niveau suivant est tente automatiquement.

### `fetch_events() -> list[dict]`

Recupere les evenements economiques en suivant la cascade.

**Algorithme** :

1. **Cache** : tente de charger depuis `calendar_cache` (TTL 4h). Si les donnees sont encore fraiches, retourne immediatement.
2. **Investing.com** : appel a `fetch_events_investing()` via Playwright. Si reussi, sauvegarde dans le cache et retourne.
3. **ForexFactory** : requete HTTP GET sur `https://www.forexfactory.com/calendar` + parsing BeautifulSoup. Si reussi, sauvegarde dans le cache et retourne.
4. **Statique** : generation d'evenements macroeconomiques majeurs recurrents a partir d'une base interne.
5. Si tout echoue, retourne une liste vide.

**Fonctions internes** :

| Fonction | Role |
|---|---|
| `_load_from_cache(date, now)` | Charge les evenements depuis `calendar_cache` si TTL valide |
| `_save_to_cache(date, events, now)` | Persiste les evenements dans `calendar_cache` |
| `_try_investing()` | Tente le scraping Investing.com via `investing_calendar.py`. Retourne vide si Playwright indisponible |
| `_scrape_forexfactory()` | Telecharge et parse la page ForexFactory |
| `_parse_calendar_row(row)` | Extrait un evenement d'une ligne HTML ForexFactory |
| `_parse_impact(row)` | Determine l'impact (high/medium/low) via les classes CSS |
| `_get_static_events()` | Genere les evenements macroeconomiques recurrents (fallback ultime) |

**Headers HTTP (ForexFactory)** :

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
```

**Timeout** : 15 secondes pour ForexFactory, 30 secondes pour Investing.com (navigation + attente selecteur).

### `filter_relevant_events(events, symbol="EURUSD") -> list[dict]`

Filtre les evenements par devise du symbole de trading.

```python
currencies = {symbol[:3], symbol[3:]}  # EUR, USD
return [ev for ev in events if ev.get("impact") in ("high", "medium") and ev.get("currency") in currencies]
```

- Ne conserve que les evenements HIGH et MEDIUM
- Filtre par devise (ex: EURUSD conserve les evenements EUR et USD)

### Cache SQLite

- Table : `calendar_cache(date TEXT PK, events_json TEXT, fetched_at TEXT)`
- TTL : 4 heures
- Insertion : `INSERT OR REPLACE`
- Le cache est persiste entre les redemarrages du bot

---

## Schema de la base de donnees

Chaque symbole a sa propre base `data/{symbole}/trading.db` avec les tables suivantes :

### `trades`

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Identifiant auto-increment |
| `ticket` | INTEGER | Ticket MT5 du trade |
| `symbol` | TEXT | Symbole (EURUSD, GBPUSD, ...) |
| `direction` | TEXT | BUY ou SELL |
| `volume` | REAL | Taille de la position en lots |
| `opened_at` | TEXT | Timestamp ISO d'ouverture |
| `open_price` | REAL | Prix d'entree |
| `stop_loss` | REAL | Niveau du stop loss |
| `take_profit` | REAL | Niveau du take profit |
| `confidence` | INTEGER | Confiance IA (0-100) |
| `reasoning` | TEXT | Raisonnement de l'IA |
| `closed_at` | TEXT | Timestamp ISO de fermeture (NULL si ouvert) |
| `close_price` | REAL | Prix de sortie (NULL si ouvert) |
| `profit` | REAL | Profit/Perte en devise du compte (NULL si ouvert) |

### `bot_state`

| Colonne | Type | Description |
|---|---|---|
| `key` | TEXT PK | Cle de l'etat (ex: `circuit_breaker_until`, `cooldown_EURUSD_BUY`) |
| `value` | TEXT | Valeur (souvent timestamp ISO) |

Utilise par : circuit breaker, cooldown post TIME EXIT.

---

## `investing_calendar.py` - Scrapeur Investing.com (v1.0)

**Fichier** : `src/data/investing_calendar.py`

### Description

Scrapeur specialise pour le calendrier economique d'Investing.com (version française). Utilise **Playwright** avec un navigateur Chromium headless pour contourner le rendu JavaScript cote client (Next.js).

### `fetch_events_investing() -> list[dict]`

Point d'entree unique du module. Gere les tentatives avec retry (3 max, delai 3s).

**Retourne** un dictionnaire par evenement :

```python
{
    "time": "08:30",       # Heure fixe ou temps restant: "57m"
    "currency": "USD",     # Devise mappee depuis le code pays
    "event": "Non-Farm Payrolls",
    "impact": "high",      # "high" | "medium" | "low"
    "actual": "243K",
    "forecast": "185K",
    "previous": "228K",
}
```

**Si Playwright n'est pas installe** : retourne une liste vide sans planter (import tardif).

### Techniques anti-detection

Investing.com detecte et bloque les bots. Le module implemente plusieurs contre-mesures :

| Technique | Implementation |
|---|---|
| **User-agent** | Chrome 125 Windows (spoofing) |
| **Webdriver flag** | Desactive via `context.add_init_script()` |
| **Plugins** | Simule 5 plugins navigateur presents |
| **Languages** | `fr-FR, fr, en-US, en` |
| **Chrome runtime** | `window.chrome.runtime` defini |
| **Permissions** | Geolocalisation accordee, notifications refusees |
| **Viewport** | 1920x1080 (ecran standard) |
| **Locale** | `fr-FR`, fuseau Europe/Paris |

### Extraction des donnees

L'extraction se fait par `page.evaluate()` avec JavaScript injecte dans le navigateur :

1. **Navigation** vers `https://fr.investing.com/economic-calendar`, attente `networkidle`
2. **Attente** du selecteur `table.datatable-v2_table__93S4Y` (max 30s)
3. **Pause** supplementaire de 2s pour le rendu complet
4. **Iteration** sur les lignes `<tbody tr>`, ignore les separateurs de date (`td[colspan]`)
5. **Extraction** :
   - Nom de l'evenement : lien `<a>` dans la 4e colonne (index 3)
   - Heure : texte de la 2e colonne (index 1) - peut etre `"08:30"` ou `"57m"` (temps restant)
   - Devise : mapping pays -> devise via dictionnaire (ISO 3166-1 alpha-2 -> ISO 4217)
   - Impact : comptage des etoiles remplies (classe CSS `opacity-60`) : >= 3 = high, >= 2 = medium, sinon low
   - Valeurs : actual (col 5), forecast (col 6), previous (col 7)

### Gestion des erreurs

- Si Playwright est absent du systeme (ImportError) : retourne `[]` silencieusement
- 3 tentatives avec `time.sleep(3)` entre chaque
- Timeout de navigation : 30s
- Timeout d'attente du selecteur : 30s
- Toute exception est capturee et loggee. En echec total, retourne `[]`

### `filter_relevant_investing_events(events, symbol="EURUSD") -> list[dict]`

Meme logique que `filter_relevant_events()` dans `calendar.py`, mais specifique au module Investing.com. Conserve les evenements HIGH/MEDIUM dont la devise correspond a la paire.

### Mapping pays -> devise

Le dictionnaire `COUNTRY_TO_CURRENCY` couvre ~50 codes pays ISO 3166-1 alpha-2. Cas notables :

| Pays | Code | Devise |
|---|---|---|
| Etats-Unis | US | USD |
| Japon | JP | JPY |
| Australie | AU | AUD |
| Allemagne, France, Italie, Espagne... | DE, FR, IT, ES... | EUR |
| Royaume-Uni | GB | GBP |
| Suisse | CH | CHF |
| Canada | CA | CAD |
| Chine | CN | CNY |

### `if __name__ == "__main__"`

Le module peut etre teste en ligne de commande :

```powershell
python -m src.data.investing_calendar
```

Affiche le nombre total d'evenements, les 10 premiers, puis les evenements filtres pour EURUSD.

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
