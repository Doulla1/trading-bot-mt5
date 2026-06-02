# Strategie de tests

## Vue d'ensemble

Les tests sont organises dans le dossier `tests/` et utilisent **pytest** avec couverture de code.

## Configuration

**Fichier** : `pyproject.toml`

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Dependances dev** :

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]
```

Installation : `pip install -e ".[dev]"`

## Execution des tests

```bash
# Tous les tests
pytest

# Avec couverture
pytest --cov=src --cov-report=term --cov-report=html

# Test specifique
pytest tests/test_strategy.py -v

# Mode verbose
pytest -v
```

## Perimetre de test

### Tests implementes (v1.1)

| Fichier | Tests | Status |
|---|---|---|
| `tests/test_executor.py` | 8 tests : calcul position size (6) + TradeResult (2) | 8/8 passent |
| `tests/test_vision.py` | 7 tests : validation reponses IA (decision valide, confiance out-of-range, SL trop petit, TP < 1.5x SL, risk level invalide, action invalide, champ manquant) | 7/7 passent |

### Tests a implementer (priorite)

| Module | Ce qu'il faut tester | Priorite |
|---|---|---|
| `indicators.py` | Calcul RSI, MACD, Bollinger, ATR sur donnees connues | Haute |
| `strategy.py` | Regles de risque : limite perte, circuit breaker, spread filter | Haute |
| `database.py` | CRUD, statistiques, singleton thread-safe | Haute |
| `backtest/rules_engine.py` | Scoring 20 signaux, seuils BUY/SELL/HOLD, calcul SL/TP | Haute |
| `backtest/strategy_adapter.py` | Circuit breaker, daily loss limit, position sizing | Haute |
| `backtest/simulated_executor.py` | Ouverture/fermeture positions, slippage, commission | Moyenne |
| `backtest/engine.py` | Boucle barre-par-barre, integration des composants | Moyenne |
| `backtest/data_source.py` | Lecture CSV, indexation par datetime | Moyenne |
| `backtest/report.py` | Calcul Sharpe, Sortino, drawdown, profit factor | Moyenne |
| `backtest/optimizer.py` | Grid search, classement par metrique | Basse |
| `models.py` | Creation des dataclasses | Basse |
| `config.py` | Chargement .env, chemins relatifs | Moyenne |
| `screenshots.py` | Nettoyage vieux fichiers | Moyenne |
| `calendar.py` | Parsing HTML ForexFactory (avec fixtures) | Moyenne |
| `prompts.py` | Formatage du prompt (pas de test API) | Basse |

### Tests d'integration (optionnels)

| Test | Description |
|---|---|
| `bridge.connect()` avec identifiants valides | Necessite MT5 installe |
| `bridge.get_rates()` | Verifie que les donnees OHLCV sont coherentes |
| `vision.analyze()` | Necessite cle API OpenAI valide (test manuel) |

### Tests manuels (hors CI)

- Execution de `run.py --once` avec compte demo
- Verification des logs dans `logs/trading-bot.log`
- Verification de la base SQLite avec un client SQLite
- Verification des screenshots dans `data/screenshots/`

## Exemple de test : indicateurs

```python
# tests/test_indicators.py
import pandas as pd
import numpy as np
from src.mt5.indicators import compute_all

def test_rsi_calculation():
    """RSI doit etre entre 0 et 100."""
    dates = pd.date_range("2024-01-01", periods=200, freq="15min")
    df = pd.DataFrame({
        "open": np.random.uniform(1.08, 1.09, 200),
        "high": np.random.uniform(1.08, 1.09, 200),
        "low": np.random.uniform(1.08, 1.09, 200),
        "close": np.random.uniform(1.08, 1.09, 200),
    }, index=dates)
    result = compute_all(df)
    assert result["rsi_14"] is not None
    assert 0 <= result["rsi_14"] <= 100
```

## Exemple de test : risk management

```python
# tests/test_strategy.py
from src.ai.strategy import _get_daily_pnl

def test_daily_pnl_empty_db():
    """Avec une base vide, le P&L quotidien doit etre 0."""
    pnl = _get_daily_pnl()
    assert pnl == 0.0
```

## Exemple de test : position sizing

```python
# tests/test_executor.py
from src.mt5.executor import calculate_position_size

def test_position_size():
    """Verifie le calcul du volume."""
    result = calculate_position_size(
        account_balance=10000,
        stop_loss_pips=20,
        symbol_info={"trade_tick_value": 1.0, "point": 0.00001},
        risk_pct=1.0,
    )
    assert result >= 0.01
    assert result <= 10.0  # max raisonnable
```

## Couverture cible

- **Minimum** : 70% de couverture globale
- **Cible** : 80% sur les modules critiques (`indicators`, `strategy`, `executor`, `database`)
- **Niveau de confiance** : le bot etant experimental, la priorite est a la justesse des calculs et a la robustesse du risk management

## Outils de qualite

```bash
# Linting
ruff check src/

# Typage statique
mypy src/
```
