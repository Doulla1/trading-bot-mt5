# Architecture globale

## Diagramme C4 - Niveau 1 (Contexte Systeme)

```mermaid
flowchart TD
    subgraph MT5["MetaTrader 5 (Fusion Markets)"]
        CHART[Chart OHLCV - 200 bougies]
        EXEC[Trade Execution - ordres]
        ACCT[Account Info - balance, positions]
    end
    subgraph BOT["Trading Bot IA"]
        BRIDGE[bridge.py - Connexion MT5]
        INDIC[indicators.py - RSI, MACD, Bollinger...]
        SCR[screenshots.py - Capture 800x600]
        CAL[calendar.py - ForexFactory]
        DB[database.py - SQLite locale]
        AI[vision.py - GPT-4o-mini Vision]
        STRAT[strategy.py - Risk Management]
        SCHED[scheduler.py - Orchestrateur]
    end
    subgraph AI_SVC["OpenAI API"]
        GPT[GPT-4o-mini - Vision + NLP]
    end
    subgraph WEB["Web (ForexFactory)"]
        FF[Calendrier economique]
    end

    MT5 <-->|"OHLCV + Positions + Ordres"| BRIDGE
    MT5 -->|"Screenshot PNG"| SCR
    BRIDGE -->|"DataFrame pandas"| INDIC
    SCR -->|"Image base64"| AI
    INDIC -->|"dict indicateurs"| AI
    CAL -->|"list[dict] evenements"| AI
    FF -->|"HTTP GET + BeautifulSoup"| CAL
    AI -->|"JSON request (image+prompt)"| GPT
    GPT -->|"JSON decision"| AI
    AI -->|"action, confidence, SL, TP"| STRAT
    STRAT -->|"ordre MT5"| EXEC
    SCHED -->|"run_once() cycle"| BRIDGE
    SCHED -->|"capture_chart()"| SCR
    SCHED -->|"fetch_events()"| CAL
    SCHED -->|"analyze()"| AI
    SCHED -->|"execute_decision()"| STRAT
    DB -->|"log_analysis() + log_trade()"| SCHED
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

## Modules internes

### `src/config.py`

Configuration centralisee via `pydantic-settings`. Charge le fichier `.env` et expose les parametres sous forme de proprietes type-safe (voir [Configuration](../4-technique/configuration.md)).

### `src/mt5/` - Bridge MT5

| Fichier | Responsabilite |
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
