# Architecture globale v2.1

## Diagramme C4 - Niveau 1 (Contexte Systeme)

```mermaid
flowchart TD
    subgraph MT5["MetaTrader 5 (Fusion Markets)"]
        CHART[Chart OHLCV - 200 bougies M15 + 100 H1]
        EXEC[Trade Execution - ordres]
        ACCT[Account Info - balance, positions]
    end
    subgraph BOT["Trading Bot IA v2.1"]
        BRIDGE[bridge.py - Connexion MT5]
        INDIC[indicators.py - RSI, MACD, ADX, Ichimoku, Pivots, Patterns]
        CHARTGEN[chart_renderer.py - Generation chart pro]
        SCR[screenshots.py - Capture debug]
        CAL[calendar.py - ForexFactory + cache]
        DB[database.py - SQLite + memoire]
        OCR[ocr.py - GPT-4o-mini OCR chart]
        ANALYZER[analyzer.py - DeepSeek V4 Pro decision]
        STRAT[strategy.py - Risk + Position management]
        SCHED[scheduler.py - Orchestrateur]
    end
    subgraph AI_SVC["API IA"]
        GPT[GPT-4o-mini - Vision OCR]
        DS[DeepSeek V4 Pro - Decision 1M contexte]
    end
    subgraph WEB["Web"]
        FF[Calendrier economique]
    end

    MT5 <-->|"OHLCV + Positions + Ordres"| BRIDGE
    BRIDGE -->|"DataFrame pandas"| INDIC
    BRIDGE -->|"DataFrame"| CHARTGEN
    INDIC -->|"dict indicateurs"| CHARTGEN
    CHARTGEN -->|"Chart PNG"| OCR
    OCR -->|"JSON chart"| ANALYZER
    INDIC -->|"dict enrichi"| ANALYZER
    CAL -->|"evenements"| ANALYZER
    DB -->|"historique + stats"| ANALYZER
    FF -->|"HTTP GET"| CAL
    OCR -->|"image+prompt"| GPT
    GPT -->|"JSON OCR"| OCR
    ANALYZER -->|"texte complet"| DS
    DS -->|"JSON decision"| ANALYZER
    ANALYZER -->|"decision"| STRAT
    STRAT -->|"ordre MT5"| EXEC
    STRAT -->|"breakeven/trailing"| EXEC
    SCHED -->|"run_once()"| BRIDGE
    SCHED -->|"manage_positions()"| STRAT
    SCHED -->|"fetch_events()"| CAL
    SCHED -->|"log_*()"| DB
```

## Description des systemes

### MetaTrader 5 (Fusion Markets)

Plateforme de trading CFD/Forex. Le bot s'y connecte via l'API Python `MetaTrader5`.

- **Chart OHLCV** : fournit les donnees de prix historiques (Open, High, Low, Close, Volume)
- **Trade Execution** : recoit et execute les ordres BUY/SELL/CLOSE
- **Account Info** : expose le solde, les positions ouvertes, les proprietes des symboles

### Trading Bot IA

Application Python autonome decoupee en 6 modules. Voir les sections ci-dessous.

### OpenAI API

Service cloud GPT-4o-mini Vision qui analyse le screenshot et les donnees structurees pour produire une decision JSON.

### ForexFactory

Site web de calendrier economique. Scrape a chaque cycle pour recuperer les evenements a fort impact.

## Diagramme C4 - Niveau 2 (Conteneurs)

```mermaid
flowchart LR
    subgraph BOT["Trading Bot IA"]
        CORE[scheduler.py<br/>Orchestrateur]
        AI_MOD[ai/<br/>vision + strategy + prompts]
        DATA_MOD[data/<br/>calendar + database + models]
        MT5_MOD[mt5/<br/>bridge + executor + indicators + screenshots]
        UTILS[utils/<br/>logger]
        CFG[config.py<br/>Settings pydantic]
    end

    CORE --> AI_MOD
    CORE --> DATA_MOD
    CORE --> MT5_MOD
    AI_MOD --> CFG
    MT5_MOD --> CFG
    DATA_MOD --> CFG
    UTILS --> CFG
```

## Modules internes v2.1

### `src/config.py`
Configuration centralisee via `pydantic-settings`. Charge le `.env`, chemins isoles par symbole.

### `src/mt5/` - Bridge MT5 + Indicateurs + Charts

| Fichier | Responsabilite |
|---|---|
| `bridge.py` | Connexion MT5, OHLCV, infos compte, verification marche |
| `executor.py` | Ordres BUY/SELL/CLOSE, calcul position size, modification SL |
| `indicators.py` | RSI, MACD, ADX, Ichimoku Kinko Hyo, Pivot Points, Bollinger, ATR, patterns chandeliers, structure marche (HH/HL) |
| `chart_renderer.py` | **v2.1** - Generation chart professionnel (Ichimoku, EMA, BB, Pivots) via mplfinance |
| `screenshots.py` | Capture ecran debug via mss |

### `src/ai/` - Intelligence Artificielle (v2.1)

| Fichier | Responsabilite |
|---|---|
| `ocr.py` | **v2.0** - GPT-4o-mini Vision: extraction visuelle du chart (niveaux S/R, patterns, phase) |
| `analyzer.py` | **v2.0** - DeepSeek V4 Pro: decision finale avec contexte 1M tokens + memoire |
| `prompts.py` | Construction prompts (OCR + Decision + Memoire + Performance) |
| `strategy.py` | Risk management + **v2.0** position management (breakeven, trailing stop, time exit) |
| `vision.py` | Legacy - fallback GPT-4o-mini (remplace par ocr.py + analyzer.py) |

### `src/data/` - Donnees

| Fichier | Responsabilite |
|---|---|
| `calendar.py` | Scraping ForexFactory avec cache SQLite 4h |
| `database.py` | SQLite thread-safe, CRUD trades/analysis, bot_state, calendar_cache |
| `models.py` | Dataclasses Trade, AnalysisLog |

### `src/scheduler/` - Orchestrateur

| Fichier | Responsabilite |
|---|---|
| `scheduler.py` | Pipeline complet: gestion positions → reconciliation → indicateurs multi-TF → chart genere → OCR → Decision DeepSeek → execution |
|---|---|
| `bridge.py` | Connexion/deconnexion MT5, recuperation OHLCV, infos compte et symbole |
| `executor.py` | Ordres de trading (ouverture, fermeture), calcul de volume, position sizing |
| `indicators.py` | Calcul des indicateurs techniques (RSI, MACD, Bollinger, ATR, SMA) |
| `screenshots.py` | Capture d'ecran du graphique, nettoyage des fichiers obsoletes |

### `src/ai/` - Intelligence Artificielle

| Fichier | Responsabilite |
|---|---|
| `vision.py` | Appel API GPT-4o-mini Vision, encodage base64, parsing JSON, validation |
| `strategy.py` | Moteur de strategie : verification des regles de risque, execution |
| `prompts.py` | Construction du prompt envoye a l'IA |

### `src/data/` - Donnees

| Fichier | Responsabilite |
|---|---|
| `calendar.py` | Scraping ForexFactory, filtrage par devise |
| `database.py` | Connexion SQLite singleton, creation des tables, fonctions CRUD |
| `models.py` | Dataclasses `Trade` et `AnalysisLog` |

### `src/scheduler/scheduler.py`

Orchestrateur principal. Contient `run_once()` (cycle unique) et `run_forever()` (boucle infinie).

### `src/utils/logger.py`

Configuration du logger Loguru avec sortie console coloree et fichier avec rotation.

## Arbre des dependances

```mermaid
flowchart TD
    run --> scheduler
    scheduler --> bridge
    scheduler --> screenshots
    scheduler --> indicators
    scheduler --> executor
    scheduler --> calendar
    scheduler --> database
    scheduler --> vision
    scheduler --> strategy
    vision --> prompts
    vision --> config
    strategy --> bridge
    strategy --> executor
    strategy --> database
    strategy --> config
    database --> config
    bridge --> config
    executor --> config
    screenshots --> config
    indicators --> config
    calendar --> config
    logger --> config
```
