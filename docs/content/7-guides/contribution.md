# Guide de contribution

## Structure du projet

```
trading-bot/
  run.py                  # Point d'entree
  .env                    # Configuration (ne pas commit)
  pyproject.toml          # Dependances et configuration outils
  src/
    config.py             # Configuration pydantic-settings
    ai/                   # Intelligence Artificielle
      vision.py           # Appel API GPT-4o-mini
      strategy.py         # Regles de trading et risk management
      prompts.py          # Templates de prompts
    data/                 # Donnees
      calendar.py         # Scraping ForexFactory
      database.py         # SQLite
      models.py           # Dataclasses
    mt5/                  # Interface MetaTrader 5
      bridge.py           # Connexion et donnees
      executor.py         # Ordres
      indicators.py       # Calculs techniques
      screenshots.py      # Capture d'ecran
    scheduler/
      scheduler.py        # Orchestrateur
    utils/
      logger.py           # Loguru
  tests/                  # Tests pytest
  data/                   # Screenshots + DB (genere)
  logs/                   # Fichier de logs (genere)
  docs/                   # Documentation
```

## Comment contribuer

### Signaler un bug

Ouvrez une issue avec :
- La sortie de `python run.py --once`
- Les 50 dernieres lignes de `logs/trading-bot.log`
- Votre configuration (masquez les secrets)
- La version de Python et MT5

### Proposer une amelioration

Idees bienvenues :
- Nouveaux indicateurs techniques (ajouter dans `indicators.py`)
- Amelioration du prompt IA (modifier `prompts.py`)
- Support de plusieurs paires simultanement
- Interface web (streamlit, dashboard)
- Alertes (email, Telegram, Discord)
- Backtesting sur donnees historiques

### Workflow de developpement

1. **Fork** le depot
2. **Creez une branche** : `git checkout -b feature/ma-fonctionnalite`
3. **Developpez** en suivant les conventions
4. **Testez** : `pytest --cov=src`
5. **Lint** : `ruff check src/`
6. **Typecheck** : `mypy src/`
7. **Commit** : messages conventionnels (voir ci-dessous)
8. **Push** et ouvrez une Pull Request

## Conventions de code

### Python

- **Line length** : 100 caracteres (configure dans `pyproject.toml`)
- **Format** : black-compatible (utilisez `ruff format`)
- **Typage** : annotations pour toutes les fonctions publiques
- **Docstrings** : docstring pour les modules, classes et fonctions publiques

### Style

```python
# Bien
def calculate_position_size(balance: float, stop_loss_pips: int, symbol_info: dict) -> float:
    """Calcule la taille de position en lots."""
    ...

# Eviter
def calc(b, sl, si):
    return ...
```

### Nommage

- Modules : `snake_case.py`
- Classes : `PascalCase`
- Fonctions/variables : `snake_case`
- Constantes : `UPPER_SNAKE_CASE`
- Privat : prefixe `_`

## Messages de commit

Utiliser les [Conventional Commits](https://www.conventionalcommits.org/) :

```
feat(strategy): ajouter filtrage par spread maximum
fix(executor): corriger le calcul du volume pour les paires JPY
docs(installation): ajouter etape de verification MT5
test(indicators): ajouter test RSI avec donnees connues
refactor(database): extraire la logique de connexion
```

## Tests

- Toujours ecrire des tests pour les nouvelles fonctionnalites
- Couverture minimale : 70%
- Les tests ne doivent pas necessiter de connexion MT5 ou OpenAI
- Utiliser des fixtures pytest pour les donnees de test

```bash
# Executer les tests
pytest -v

# Avec couverture
pytest --cov=src --cov-report=term

# Linting
ruff check src/

# Typage
mypy src/
```

## Documentation

- La documentation est en **francais**
- Les nouveaux modules doivent etre documentes dans `docs/content/`
- Les ADRs doivent etre crees pour les decisions architecturales importantes
- Les prompts IA doivent rester synchronises entre `prompts.py` et la documentation
