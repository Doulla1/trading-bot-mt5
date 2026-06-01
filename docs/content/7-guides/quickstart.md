# Demarrage rapide

Ce guide vous permet de lancer le bot en moins de 5 minutes si les prerequis sont installes.

## Prerequis

- [X] MetaTrader 5 installe et connecte a Fusion Markets (demo OK)
- [X] Python 3.11+ installe
- [X] Environnement virtuel cree et dependances installees
- [X] Fichier `.env` configure avec cle API OpenAI et identifiants MT5

> Si ce n'est pas le cas, suivez le [guide d'installation](../6-devops/installation.md) d'abord.

## 1. Lancement rapide (mode unique)

```powershell
.venv\Scripts\Activate.ps1
python run.py --once
```

Ce mode execute **un seul cycle** d'analyse et de trading, puis affiche les statistiques et s'arrete.

**Ce que vous devriez voir** :

```
2026-06-01 14:30:00 | INFO     | === CYCLE 14:30:00 ===
2026-06-01 14:30:00 | INFO     | MT5 connecte - Compte XXXXX sur FusionMarkets-Demo
2026-06-01 14:30:01 | INFO     | Screenshot sauvegarde : data\screenshots\EURUSD_20260601_143000.png
2026-06-01 14:30:02 | INFO     | Calendrier: 12 evenements recuperes
2026-06-01 14:30:02 | INFO     | Envoi analyse a GPT-4o-mini pour EURUSD...
2026-06-01 14:30:05 | INFO     | Decision IA: HOLD | Confiance: 45% | SL: 20pips | TP: 35pips
2026-06-01 14:30:05 | INFO     | Decision HOLD (confiance 45%) - pas executee
2026-06-01 14:30:05 | INFO     | MT5 deconnecte
2026-06-01 14:30:05 | INFO     | === FIN CYCLE (5.2s) ===

┌────────────────────────┬─────────┐
│ Metrique               │ Valeur  │
├────────────────────────┼─────────┤
│ total_closed           │ 0       │
│ wins                   │ 0       │
│ losses                 │ 0       │
│ win_rate               │ 0       │
│ total_profit           │ 0.00    │
│ avg_confidence         │ 45.0    │
└────────────────────────┴─────────┘
```

## 2. Mode continu

```powershell
python run.py
```

Le bot tourne en boucle, avec un cycle toutes les 15 minutes. Pour arreter : `Ctrl+C`.

```
  🤖 TRADING BOT IA - Fusion Markets / MT5
  --------------------------------------------------
  Symbole: EURUSD | Timeframe: M15
  Intervalle: 15 min | Confiance min: 70%
  Risque/trade: 1.0% | Perte/jour max: 3.0%
  --------------------------------------------------

2026-06-01 14:30:00 | INFO     | Trading Bot demarre | EURUSD | M15 | Intervalle: 15min
2026-06-01 14:30:00 | INFO     | === CYCLE 14:30:00 ===
...
2026-06-01 14:45:00 | INFO     | Prochain cycle a 14:45:00
```

## 3. Statistiques

```powershell
python run.py --stats
```

Affiche les statistiques cumulees sans lancer d'analyse.

## 4. Verifier les logs

```powershell
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

```bash
# Terminal 1 : EURUSD
python run.py --symbol EURUSD

# Terminal 2 : GBPUSD (base de donnees isolee dans data/gbpusd/)
python run.py --symbol GBPUSD

# Terminal 3 : AUDUSD
python run.py --symbol AUDUSD

# Execution unique sur un actif specifique
python run.py --symbol EURUSD --once
```

**Comment ca marche ?**

- Chaque `--symbol` cree ses propres repertoires isoles :
  - `data/{symbole}/trading.db` (base de donnees)
  - `logs/{symbole}/trading-bot.log` (fichier de logs)
  - `data/{symbole}/screenshots/` (captures d'ecran)
- Les instances sont totalement independantes et peuvent tourner en parallele
- Chaque instance a son propre circuit breaker, sa propre limite de perte journaliere, etc.

> **Note** : Chaque instance necessite un terminal separe (ou un script PowerShell avec `Start-Process`).

## Depannage rapide

| Probleme | Solution |
|---|---|
| `Echec connexion MT5` | Verifier MT5_LOGIN, MT5_PASSWORD, MT5_SERVER dans .env |
| `Pas de JSON dans la reponse IA` | Verifier OPENAI_API_KEY et le quota OpenAI |
| `Marche ferme` | Le marche forex est ferme le week-end. Attendre lundi |
| `Module introuvable` | Verifier que `.venv` est active et `pip install -e .` a ete execute |
| `Base de donnees verrouillee` | Attendre la fin du cycle en cours ou supprimer `data/trading.db` |

Pour plus de details, voir le [guide de depannage](depannage.md).
