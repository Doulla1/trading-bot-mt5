# Trading Bot IA - Fusion Markets / MT5

Bot de trading forex automatise utilisant l'IA (GPT-4o-mini Vision) pour analyser les charts MT5, les indicateurs techniques et le calendrier economique, puis executer des trades automatiquement.

> **AVERTISSEMENT** : Ce bot est en phase experimentale. Utilisez-le UNIQUEMENT sur un compte demo ou avec de tres petits montants. Le trading forex comporte des risques eleves.

## Documentation complete

La documentation complete du projet se trouve dans `docs/content/` :

| Section | Description |
|---|---|
| [1 - Produit](docs/content/1-produit/README.md) | Vue d'ensemble, personas, glossaire |
| [2 - Fonctionnel](docs/content/2-fonctionnel/cycle-analyse.md) | Cycle d'analyse, regles de risque, scenarios metier |
| [3 - Architecture](docs/content/3-architecture/architecture-globale.md) | Architecture, flux de donnees, ADRs |
| [4 - Technique](docs/content/4-technique/configuration.md) | Configuration, API, modules backend |
| [5 - Tests](docs/content/5-tests/strategie-tests.md) | Strategie de test |
| [6 - DevOps](docs/content/6-devops/installation.md) | Installation, deploiement |
| [7 - Guides](docs/content/7-guides/quickstart.md) | Demarrage rapide, contribution, depannage |

## Architecture

```
Screenshot MT5 ──┐
Indicateurs    ──┼──▶ GPT-4o-mini Vision ──▶ Decision JSON ──▶ Execution MT5
Calendrier eco ──┘
                        ▲
                   Risk Management
                 (stop loss, limites)
```

## Prérequis

- **Windows** avec MetaTrader 5 installe et connecte a Fusion Markets
- **Python 3.11+**
- Compte OpenAI avec acces API (GPT-4o-mini)

## Installation

```bash
cd trading-bot

# Environnement virtuel
python -m venv .venv
.venv\Scripts\activate

# Installation
pip install -e .

# Configuration
copy .env.example .env
# Editer .env avec vos cles API et parametres MT5
```

## Configuration (.env)

```env
OPENAI_API_KEY=sk-votre-cle
MT5_LOGIN=12345678
MT5_PASSWORD=votre_mdp
MT5_SERVER=FusionMarkets-Demo
TRADING_SYMBOL=EURUSD
TRADING_TIMEFRAME=M15
MAX_RISK_PER_TRADE_PCT=1.0
ANALYSIS_INTERVAL_MINUTES=15
```

## Utilisation

```bash
python run.py              # Boucle infinie
python run.py --once       # Un seul cycle
python run.py --stats      # Statistiques
```

## Risk Management

- Max 1% du capital risque par trade
- Stop loss obligatoire sur chaque position
- Limite de perte journaliere (3% par defaut)
- Max 1 position ouverte a la fois
- Seuil de confiance minimum (70%) avant execution

## Structure

```
trading-bot/
├── run.py                  # Point d'entree
├── src/
│   ├── config.py           # Configuration (pydantic-settings)
│   ├── mt5/
│   │   ├── bridge.py       # Connexion MT5, OHLCV
│   │   ├── screenshots.py  # Capture d'ecran chart
│   │   ├── indicators.py   # RSI, MACD, Bollinger, ATR
│   │   └── executor.py     # Ordres buy/sell/close
│   ├── ai/
│   │   ├── vision.py       # GPT-4o-mini Vision API
│   │   ├── strategy.py     # Decision + risk mgmt
│   │   └── prompts.py      # Templates de prompts
│   ├── data/
│   │   ├── calendar.py     # ForexFactory scraping
│   │   ├── database.py     # SQLite (trades + analyses)
│   │   └── models.py       # Dataclasses
│   ├── scheduler/
│   │   └── scheduler.py    # Boucle principale
│   └── utils/
│       └── logger.py       # Configuration loguru
├── data/                   # SQLite + screenshots (auto)
├── logs/                   # Logs (auto)
├── pyproject.toml
└── .env.example
```

## Cout estime API

GPT-4o-mini : ~0.002€ par analyse (screenshot 800x600 + texte).
A 4 analyses/heure, 24h/24 : ~5.75€ / mois.

## Licence

MIT - Usage experimental uniquement.
