# Deploiement et execution v2.1

## Mode de fonctionnement

Le bot est concu pour tourner sur une machine Windows **de bureau** ou **serveur** avec MetaTrader 5.

## Execution multi-symboles (recommande)

```powershell
# Tout lancer (detache, pas de fenetre)
.\scripts\start-all.ps1

# Voir l'etat
.\scripts\start-all.ps1 -Status

# Arreter
.\scripts\start-all.ps1 -Stop
```

Un seul processus (`run_multi.py`) gere les 6 actifs sequentiellement :

```
ROUND X (~7 min pour 6 symboles):
  EURUSD (M15) → Analyse ~70s
  GBPUSD (M15) → Analyse ~70s
  AUDUSD (M15) → Analyse ~70s
  USDJPY (M15) → Analyse ~70s
  USDCHF (M15) → Analyse ~70s
  XAUUSD (H1)  → Analyse toutes les 4 rondes (~60 min)
```

## Execution symbole unique

```powershell
python run.py --symbol EURUSD              # Mode continu
python run.py --symbol GBPUSD --once       # Execution unique
python run.py --stats                      # Statistiques
```

## Logs

Rotation **journaliere**, retention **15 jours**, par symbole :

```
logs/
  eurusd/
    trading-bot.2026-06-01.log
    trading-bot.2026-06-02.log
    ... (supprimes apres 15 jours)
  gbpusd/
    ...
  xauusd/
    ...
```

```powershell
# Surveiller en temps reel
Get-Content logs\eurusd\trading-bot.2026-06-01.log -Tail 20 -Wait

# Dernieres lignes
Get-Content logs\eurusd\trading-bot.2026-06-01.log -Tail 50
```

## Auto-start Windows

```powershell
# Executer EN TANT QU'ADMINISTRATEUR :
scripts\install-autostart.bat
```

Cree une tache planifiee `TradingBot-IA` qui lance les 6 actifs au demarrage.

```powershell
# Supprimer l'auto-start
schtasks /Delete /TN "TradingBot-IA" /F
```

## Base de donnees

Chaque symbole a sa propre base isolee :

| Symbole | Emplacement |
|---|---|
| EURUSD | `data/eurusd/trading.db` |
| GBPUSD | `data/gbpusd/trading.db` |
| XAUUSD | `data/xauusd/trading.db` |
   - **Déclencheur** : Au demarrage
   - **Action** : Demarrer un programme
   - **Programme** : `C:\Users\...\trading-bot\.venv\Scripts\python.exe`
   - **Arguments** : `run.py`
   - **Repertoire** : `C:\Users\...\trading-bot`

## Maintenance

### Taches quotidiennes

- Verifier les logs pour les erreurs
- Surveiller le fichier de base de donnees (taille)
- Verifier que MT5 est toujours connecte

### Taches hebdomadaires

- Nettoyer les vieux screenshots (automatique, retention 48h)
- Verifier le solde du compte

### Taches mensuelles

- Verifier la consommation de l'API OpenAI (quota et cout)
- Archiver la base de donnees si necessaire
- Mettre a jour les dependances : `pip install --upgrade -e .`

## Redemarrage

```powershell
# Arret propre
Ctrl+C

# Redemarrage
python run.py
```

Le bot reprend automatiquement : les positions ouvertes restent en place, la base conserve l'historique.
