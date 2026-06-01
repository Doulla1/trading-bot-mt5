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

Pour plus de details, voir le [guide de depannage](depannage.md).
