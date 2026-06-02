# Demarrage rapide v2.1

Ce guide vous permet de lancer le bot en moins de 5 minutes si les prerequis sont installes.

## Prerequis

- [X] MetaTrader 5 installe et connecte a Fusion Markets (demo OK)
- [X] Python 3.11+ installe
- [X] Environnement virtuel cree et dependances installees
- [X] Fichier `.env` configure avec cle OpenAI + DeepSeek + identifiants MT5

## 1. Lancement rapide (mode unique)

```powershell
python run.py --symbol EURUSD --once
```

Execute **un seul cycle** sur EURUSD (indicateurs, OCR, DeepSeek), puis affiche les stats.

## 2. Mode continu (tous les actifs)

```powershell
# Lancer les 6 actifs en fond (sans fenetre)
.\scripts\start-all.ps1

# Voir l'etat
.\scripts\start-all.ps1 -Status

# Arreter
.\scripts\start-all.ps1 -Stop
```

| Symbole | Timeframe | Magic | Commentaire |
|---|---|---|---|
| EURUSD | M15 | 73456 | Euro/Dollar US |
| GBPUSD | M15 | 73457 | Livre/Dollar |
| AUDUSD | M15 | 73458 | Dollar australien/USD |
| USDJPY | M15 | 73459 | Dollar/Yen |
| USDCHF | M15 | 73460 | Dollar/Franc suisse |
| XAUUSD | H1 | 73461 | Or (H1 car + volatil) |

## 3. Mode continu (symbole unique)

```powershell
python run.py --symbol EURUSD
```

## 4. Auto-start au demarrage Windows

```powershell
# Clic droit → Executer en tant qu'administrateur
scripts\install-autostart.bat
```

## 5. Logs

```powershell
# Rotation journaliere, retention 15 jours
Get-Content logs\eurusd\trading-bot.2026-06-01.log -Tail 20
Get-Content logs\xauusd\trading-bot.2026-06-01.log -Tail 20
```
# Voir les dernieres lignes du fichier de log
Get-Content logs/trading-bot.log -Tail 20
```

## 5. Inspecter la base de donnees

```powershell
# Derniers trades (PowerShell avec sqlite3)
sqlite3 data/trading.db "SELECT * FROM trades ORDER BY opened_at DESC LIMIT 5;"

# Nombre d'analyses effectuees
sqlite3 data/trading.db "SELECT COUNT(*) FROM analysis_logs;"
```

## Lancer plusieurs instances (multi-actifs)

Le bot supporte le lancement parallele de plusieurs instances, une par actif :

## Depannage rapide

| Probleme | Solution |
|---|---|
| `Echec connexion MT5` | Verifier MT5_LOGIN, MT5_PASSWORD, MT5_SERVER dans .env |
| `Pas de JSON dans la reponse` | Verifier OPENAI_API_KEY et DEEPSEEK_API_KEY |
| `Les instances crashent` | MT5 ne supporte qu'un processus - utiliser `run_multi.py` |
| `Rotation non fonctionnelle` | Les nouveaux logs apparaissent apres minuit (rotation journaliere) |
| `Marche ferme` | Le marche forex est ferme le week-end. Attendre lundi |
| `Module introuvable` | Verifier que `.venv` est active et `pip install -e .` a ete execute |
| `Base de donnees verrouillee` | Attendre la fin du cycle en cours ou supprimer `data/trading.db` |

## 6. Envoyer un rapport journalier de test

Le module de rapports genere un email recapitulatif avec les trades du jour et une analyse DeepSeek V4 Pro.

```powershell
# Rapport du jour (aujourd'hui UTC)
python scripts/send_report.py

# Rapport d'une date specifique
python scripts/send_report.py 2026-06-01
```

**Prerequis** : la variable `MAILER_API_SECRET` doit etre configuree dans le `.env` (cle API de `mailing.weltaare-tech.com`).

Le rapport contient :
- Des cartes resume (P&L, win rate, meilleur/pire trade)
- Un tableau par symbole avec tous les trades du jour
- Une analyse DeepSeek V4 Pro (Resume, Forces, Faiblesses, Recommandations)

## 7. Backtesting

Le backtesteur permet de tester les strategies sur des donnees historiques sans cout API et sans risque.

### Export des donnees MT5

```powershell
# Afficher les instructions d'export
python backtest.py --export --symbol EURUSD

# Le CSV genere doit etre place dans data/historical/eurusd/
```

### Lancer un backtest

```powershell
# Backtest simple (1 symbole, 1 mois)
python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31

# Backtest multi-symboles
python backtest.py --multi --from 2026-05-01 --to 2026-05-31

# Avec un fichier de poids personnalise
python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31 --weights my_weights.yaml
```

### Optimiser les parametres

```powershell
# Grid search sur les parametres du RuleEngine
python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31 --optimize --metric sharpe_ratio

# Exporter les resultats d'optimisation
python backtest.py --symbol EURUSD --optimize --metric profit_factor --output best_params.json
```

### Exporter les trades

```powershell
# Export CSV des trades individuels
python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31 --output trades.csv

# Export JSON multi-symboles
python backtest.py --multi --from 2026-05-01 --to 2026-05-31 --output all_trades.json
```

> **Note** : Le backtesteur utilise un moteur de scoring deterministe (RuleEngine) qui approxime le comportement de l'IA. Les resultats peuvent differer de la performance live. Voir [ADR-002](../3-architecture/decision-records/ADR-002-backtesteur-hybride.md) pour les details.

Pour plus de details, voir le [guide de depannage](depannage.md).
