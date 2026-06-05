# Configuration

Le bot est configure via un fichier `.env` a la racine du projet. Les parametres sont charges par `src/config.py` qui utilise `pydantic-settings` pour la validation type-safe.

## Parametres SL/TP par symbole (v4.1)

Les parametres de stop loss et take profit sont definis dans `src/ai/strategy.py` - `_ATR_SL_CONFIG` et ne sont **pas** configurables via `.env`. Ils sont ajustes manuellement en fonction des caracteristiques de chaque symbole.

| Symbole | atr_mult | min_sl (pips) | min_tp (pips) | tp_ratio |
|---|---:|---:|---:|---:|
| XAUUSD | 0.5 | 150 | 300 | 2.0 |
| EURUSD | 1.5 | 15 | 30 | 2.0 |
| GBPUSD | 1.8 | 25 | 50 | 2.0 |
| AUDUSD | 1.5 | 15 | 30 | 2.0 |
| USDJPY | 1.8 | 30 | 60 | 2.0 |
| USDCHF | 1.5 | 15 | 30 | 2.0 |

**Changements v4.1** :
- GBPUSD : `min_sl` 18 → 25, `atr_mult` 1.5 → 1.8
- USDJPY : `min_sl` 20 → 30, `atr_mult` 1.5 → 1.8

## Parametres anti-range (v4.1)

Definis dans `src/ai/strategy.py` :

| Parametre | Valeur | Description |
|---|---|---|
| `_RANGING_ADX_THRESHOLD` | 25.0 | Seuil ADX en dessous duquel le marche est sans tendance |
| `_RANGING_CONSECUTIVE_BARS` | 3 | Nombre de periodes consecutives avant blocage |

## Symboles desactives (v4.1)

Defini dans `src/ai/strategy.py` :

```python
_DISABLED_SYMBOLS: set[str] = {"XAUUSD"}
```

Ajouter ou retirer des symboles en modifiant ce set. Les symboles desactives ne recoivent pas d'ordres BUY/SELL mais continuent d'etre analyses.

## Fichier `.env`

Creez un fichier `.env` a la racine du projet en copiant l'exemple ci-dessous :

```env
# === IA Decision (v4.0: multi-provider) ===
# Cle API (remplace DEEPSEEK_API_KEY, garde la retrocompatibilite)
AI_API_KEY=sk-votre-cle-api
# Modele principal pour les decisions de trading
AI_MODEL=deepseek-v4-pro
# Modele rapide pour les cycles de confirmation
AI_FAST_MODEL=deepseek-v4-flash
# URL de base de l'API (change selon le fournisseur)
AI_BASE_URL=https://api.deepseek.com/v1
# Nom du fournisseur pour les logs (cosmetique)
AI_PROVIDER=deepseek

# === OpenAI (OCR du chart) ===
OPENAI_API_KEY=sk-votre-cle-api-openai

# === Retrocompatibilite (deprecated - utiliser AI_API_KEY) ===
# DEEPSEEK_API_KEY=sk-ancienne-cle

# === MetaTrader 5 ===
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=FusionMarkets-Demo
MT5_MAGIC_NUMBER=123456

# === Trading ===
TRADING_SYMBOL=EURUSD
TRADING_TIMEFRAME=M15

# === Gestion des risques ===
MAX_RISK_PER_TRADE_PCT=1.0
MAX_DAILY_LOSS_PCT=3.0
MAX_OPEN_POSITIONS=1
MIN_CONFIDENCE_THRESHOLD=70

# === Scheduler ===
ANALYSIS_INTERVAL_MINUTES=15

# === Chemins (optionnels, valeurs par defaut) ===
DATABASE_PATH=data/trading.db
LOG_LEVEL=INFO
LOG_FILE=logs/trading-bot.log
```

## Variables detaillees

### OpenAI (OCR du chart)

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | `str` | `""` | Cle API OpenAI pour GPT-4o-mini (OCR visuel). Obtenable sur [platform.openai.com](https://platform.openai.com/api-keys) |

### IA Decision (v4.0: multi-provider)

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `AI_API_KEY` | `str` | `""` | Cle API pour l'IA de decision. **Remplace `DEEPSEEK_API_KEY`** (toujours supporte en fallback). |
| `AI_MODEL` | `str` | `deepseek-v4-pro` | Modele utilise pour les decisions principales. Ex: `gpt-5`, `claude-sonnet-4-20250514` (via OpenRouter) |
| `AI_FAST_MODEL` | `str` | `deepseek-v4-flash` | Modele plus leger pour les cycles de confirmation |
| `AI_BASE_URL` | `str` | `https://api.deepseek.com/v1` | URL de base de l'API OpenAI-compatible. Change selon le fournisseur |
| `AI_PROVIDER` | `str` | `deepseek` | Nom du fournisseur (cosmetique, apparait dans les logs) |

> **Comment changer de fournisseur** : voir le guide [Comment changer d'IA](comment-changer-ia.md)

### OpenAI (OCR du chart)

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | `str` | `""` | Cle API OpenAI pour GPT-4o (OCR visuel). Obtenable sur [platform.openai.com](https://platform.openai.com/api-keys) |

### Retrocompatibilite

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | `str` | `""` | **Deprecated.** Utilisez `AI_API_KEY`. Si `AI_API_KEY` est vide, cette valeur est utilisee comme fallback. |

### MetaTrader 5

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `MT5_LOGIN` | `int` | `0` | Numero de compte MT5 (ex: 12345678) |
| `MT5_PASSWORD` | `str` | `""` | Mot de passe du compte MT5 |
| `MT5_SERVER` | `str` | `"FusionMarkets-Demo"` | Serveur MT5. Pour Fusion Markets : demo = `FusionMarkets-Demo`, reel = `FusionMarkets-Live` |
| `MT5_MAGIC_NUMBER` | `int` | `123456` | Magic number pour identifier les ordres du bot |

### Trading

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `TRADING_SYMBOL` | `str` | `"EURUSD"` | Paire de devises a trader. Toute paire disponible sur MT5 (GBPUSD, USDJPY, EURGBP, etc.) |
| `TRADING_TIMEFRAME` | `str` | `"M15"` | Timeframe du graphique. Valeurs : `M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`, `W1` |

### Gestion des risques

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `MAX_RISK_PER_TRADE_PCT` | `float` | `1.0` | Pourcentage du capital risque par trade. 1.0 = 1% |
| `MAX_DAILY_LOSS_PCT` | `float` | `3.0` | Perte journaliere maximale. Au-dela, tous les trades sont bloques |
| `MAX_OPEN_POSITIONS` | `int` | `1` | Nombre maximum de positions simultanees |
| `MIN_CONFIDENCE_THRESHOLD` | `int` | `70` | Confiance minimale de l'IA (0-100) pour executer un BUY/SELL |

### Scheduler

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `ANALYSIS_INTERVAL_MINUTES` | `int` | `15` | Intervalle entre chaque cycle d'analyse (en minutes) |

### Rapport journalier par email

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `MAILER_API_SECRET` | `str` | `""` | Cle API pour l'envoi d'email via `mailing.weltaare-tech.com`. Requis pour les rapports. |
| `MAILER_API_URL` | `str` | `https://mailing.weltaare-tech.com/api/v1/emails` | URL de l'API d'envoi d'email |
| `REPORT_RECIPIENT_EMAIL` | `str` | `dialloabdoul99c@gmail.com` | Adresse email du destinataire du rapport |
| `REPORT_RECIPIENT_NAME` | `str` | `""` | Nom du destinataire (optionnel, apparait dans l'email) |
| `REPORT_SENDER_NAME` | `str` | `Trading Bot MT5` | Nom de l'expediteur dans l'email |
| `REPORT_SEND_HOUR_UTC` | `int` | `23` | Heure d'envoi du rapport en UTC (0-23) |
| `REPORT_SEND_MINUTE_UTC` | `int` | `0` | Minute d'envoi du rapport en UTC (0-59) |

### Chemins et logs

| Variable | Type | Defaut | Description |
|---|---|---|---|
| `DATABASE_PATH` | `str` | `"data/trading.db"` | Chemin de la base SQLite (relatif ou absolu) |
| `LOG_LEVEL` | `str` | `"INFO"` | Niveau de log. Valeurs : `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | `str` | `"logs/trading-bot.log"` | Chemin du fichier de logs (rotation 10MB, retention 7 jours) |

## Module de configuration

**Fichier** : `src/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    # ... toutes les variables ...
```

### Proprietes calculees

Le `Settings` expose des proprietes pour les chemins de fichiers :

```python
@property
def project_root(self) -> Path:
    return Path(__file__).resolve().parent.parent

@property
def db_path(self) -> Path:
    p = Path(self.database_path)
    if not p.is_absolute():
        p = self.project_root / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

@property
def log_path(self) -> Path:
    # ... meme logique ...

@property
def screenshots_dir(self) -> Path:
    p = self.project_root / "data" / "screenshots"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

- Les chemins relatifs sont resolus par rapport a la racine du projet
- Les dossiers sont crees automatiquement s'ils n'existent pas
- Singleton : `settings = Settings()` est instancie une fois et importe partout

### Utilisation dans le code

```python
from src.config import settings

# Partout dans le code
api_key = settings.openai_api_key
symbol = settings.trading_symbol
timeframe = settings.trading_timeframe
db_path = settings.db_path
```

## Multi-instances (v1.1)

Depuis la version 1.1, le bot supporte le lancement parallele de plusieurs instances via `--symbol` :

```bash
python run.py --symbol EURUSD   # data/eurusd/trading.db
python run.py --symbol GBPUSD   # data/gbpusd/trading.db
```

Les chemins de donnees sont automatiquement isoles par symbole :

| Ressource | Avec `--symbol EURUSD` | Avec `--symbol GBPUSD` |
|---|---|---|
| Base de donnees | `data/eurusd/trading.db` | `data/gbpusd/trading.db` |
| Logs | `logs/eurusd/trading-bot.log` | `logs/gbpusd/trading-bot.log` |
| Screenshots | `data/eurusd/screenshots/` | `data/gbpusd/screenshots/` |

Si le fichier `.env` contient deja `TRADING_SYMBOL=EURUSD`, l'argument `--symbol` le surcharge pour l'instance lancee.
