# Trading Bot IA - Vue d'ensemble

> **Avertissement** : Ce bot est un **projet experimental et educatif**. Il ne constitue pas un conseil financier. L'utilisation en trading reel est **deconseillee** sans supervision humaine. Vous etes seul responsable de vos decisions de trading.

## Qu'est-ce que le Trading Bot IA ?

Le **Trading Bot IA** est un bot de trading forex automatise qui utilise l'API **GPT-4o-mini Vision** d'OpenAI pour analyser visuellement les graphiques MetaTrader 5 (MT5), croiser les donnees avec des indicateurs techniques et le calendrier economique, puis executer des trades de maniere autonome sur le broker **Fusion Markets**.

Le bot fonctionne en cycle continu :

1. **Capture** - Screenshot du graphique MT5 (800x600)
2. **Calcul** - Indicateurs techniques (RSI, MACD, Bollinger, ATR, SMA) sur 200 bougies OHLCV
3. **Scraping** - Evenements economiques via ForexFactory
4. **Analyse IA** - GPT-4o-mini Vision combine screenshot + donnees pour une decision JSON
5. **Risk Management** - Verification des limites avant execution
6. **Execution** - Ordre MT5 (BUY/SELL/CLOSE/HOLD)
7. **Logging** - Tout est enregistre dans une base SQLite

## A qui s'adresse ce projet ?

- **Developpeurs Python** souhaitant explorer l'IA appliquee au trading
- **Traders algorithmiques** cherchant a prototyper un systeme de trading visuel
- **Chercheurs en IA** interesses par l'utilisation de modeles de vision pour l'analyse financiere
- **Curieux** voulant comprendre comment chainer OpenAI Vision + MT5 + indicateurs techniques

## Capacites cles

| Fonctionnalite | Description |
|---|---|
| **Analyse visuelle** | GPT-4o-mini analyse les chandeliers, supports/resistances, patterns graphiques |
| **Indicateurs techniques** | RSI, MACD, Bandes de Bollinger, ATR, SMA (20 et 50) |
| **Calendrier economique** | Scraping ForexFactory, filtre par devise, impact HIGH/MEDIUM |
| **Gestion des risques** | Stop loss, limite perte journaliere, confiance minimale, max 1 position |
| **Base de donnees** | SQLite avec historiques des trades et analyses |
| **Execution MT5** | Ordres BUY/SELL/CLOSE via MetaTrader 5 |
| **Logs** | Loguru avec rotation 10MB, retention 7 jours |
| **Configuration** | Variables d'environnement via pydantic-settings (.env) |

## Technologies utilisees

| Technologie | Role |
|---|---|
| **Python 3.11+** | Langage principal |
| **MetaTrader 5** | Plateforme de trading |
| **OpenAI GPT-4o-mini** | Analyse visuelle et decision |
| **Pandas / NumPy** | Calculs indicateurs techniques |
| **SQLite** | Base de donnees locale |
| **BeautifulSoup / httpx** | Scraping ForexFactory |
| **Loguru** | Logging structure |
| **Pydantic** | Configuration type-safe |
| **Tenacity** | Retry automatique appels API |
| **Rich** | Affichage console |

## Structure du projet

```
trading-bot/
  run.py                  # Point d'entree
  .env                    # Configuration
  pyproject.toml          # Dependances
  src/
    config.py             # Configuration (pydantic-settings)
    ai/
      vision.py           # Analyse GPT-4o-mini Vision
      strategy.py         # Moteur de decision + risk management
      prompts.py          # Templates de prompts
    data/
      calendar.py         # Scraping ForexFactory
      database.py         # SQLite singleton
      models.py           # Dataclasses (Trade, AnalysisLog)
    mt5/
      bridge.py           # Connexion MT5, donnees OHLCV
      executor.py         # Ordres de trading
      indicators.py       # Calculs techniques
      screenshots.py      # Capture d'ecran charts
    scheduler/
      scheduler.py        # Orchestrateur boucle principale
    utils/
      logger.py           # Configuration loguru
  data/
    screenshots/          # Screenshots PNG
    trading.db            # Base SQLite
  logs/
    trading-bot.log       # Fichier de logs
  tests/                  # Tests unitaires
```
