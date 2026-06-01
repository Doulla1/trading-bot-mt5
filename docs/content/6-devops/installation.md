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
4. Verifier que le graphique EURUSD s'affiche correctement
5. (Optionnel) Ajouter d'autres paires de devises dans MarketWatch

> **Important** : Le bot utilise l'API Python de MT5. Aucune configuration speciale n'est requise dans MT5 lui-meme. Le terminal doit etre **lance** (pas besoin qu'il soit au premier plan).

## Etape 2 : Installer Python 3.11+

```powershell
# Verifier la version
python --version

# Si python 3.11+ est installe, vous devriez voir :
# Python 3.11.x

# Sinon, telecharger depuis python.org
```

## Etape 3 : Cloner le projet et creer l'environnement virtuel

```powershell
# Cloner (ou copier) le projet
cd C:\Users\votre-nom
git clone <url-du-depot> trading-bot
cd trading-bot

# Creer l'environnement virtuel
python -m venv .venv

# Activer l'environnement virtuel
.venv\Scripts\Activate.ps1

# Vous devriez voir (.venv) dans le prompt
```

## Etape 4 : Installer les dependances

```powershell
# Installation en mode editable (recommande)
pip install -e .

# Avec les dependances de developpement (tests, linting)
pip install -e ".[dev]"
```

## Etape 5 : Configurer le fichier .env

```powershell
# Creer le fichier .env a partir du template
# (copier manuellement ou creer avec notepad)
notepad .env
```

Contenu minimum :

```env
OPENAI_API_KEY=sk-votre-cle-api
MT5_LOGIN=12345678
MT5_PASSWORD=votre-mot-de-passe
MT5_SERVER=FusionMarkets-Demo
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
