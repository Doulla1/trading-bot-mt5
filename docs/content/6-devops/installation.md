# Installation

## Prerequis

| Logiciel | Version | Raison |
|---|---|---|
| **Windows 10/11** | - | MT5 est une application Windows uniquement |
| **MetaTrader 5** | Derniere version | Plateforme de trading. Telechargement : [fusionmarkets.com](https://fusionmarkets.com) |
| **Compte Fusion Markets** | Demo ou Reel | Necessite un compte ouvert pour les identifiants MT5 |
| **Python** | >= 3.11 | Le projet utilise les dernieres fonctionnalites Python |
| **Git** | (optionnel) | Pour le controle de version |

## Etape 1 : Installer MetaTrader 5

1. Ouvrir un compte demo sur [Fusion Markets](https://fusionmarkets.com)
2. Telecharger et installer MetaTrader 5 depuis votre espace client Fusion Markets
3. Connecter MT5 avec vos identifiants (login, mot de passe, serveur)
4. Ajouter les paires dans MarketWatch : EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD
5. Activer le trading algorithmique : `Outils` → `Options` → `Expert Advisors` → cocher **"Allow Algo Trading"**

## Etape 2 : Installer Python 3.11+

```powershell
python --version
```

## Etape 3 : Cloner et creer l'environnement

```powershell
git clone https://github.com/Doulla1/trading-bot-mt5.git
cd trading-bot
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## Etape 4 : Installer les dependances

```powershell
pip install -e ".[dev]"
```

Dependances : `MetaTrader5`, `openai`, `apscheduler`, `mplfinance`, `mss`, `loguru`, `pydantic-settings`, `tenacity`, `rich`.

## Etape 5 : Configurer le .env

```env
# API IA
OPENAI_API_KEY=sk-votre-cle-openai
DEEPSEEK_API_KEY=sk-votre-cle-deepseek

# MT5
MT5_LOGIN=371699
MT5_PASSWORD=votre-mot-de-passe
MT5_SERVER=FusionMarkets-Demo
MT5_MAGIC_NUMBER=73456

# Trading
TRADING_SYMBOL=EURUSD
TRADING_TIMEFRAME=M15

# Risques
MAX_RISK_PER_TRADE_PCT=1.0
MAX_DAILY_LOSS_PCT=3.0
MAX_OPEN_POSITIONS=1
MIN_CONFIDENCE_THRESHOLD=70
```
```

Voir [Configuration](../4-technique/configuration.md) pour la liste complete des variables.

## Verification de l'installation

```powershell
# Verifier que les modules s'importent
python -c "from src.config import settings; print(settings.trading_symbol)"

# Afficher les statistiques (base vide)
python run.py --stats
```

Si tout est correct, vous etes pret pour le [Demarrage rapide](.../7-guides/quickstart.md).
