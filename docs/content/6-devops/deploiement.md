# Deploiement et execution

## Mode de fonctionnement

Le bot est concu pour tourner sur une machine Windows **de bureau** ou **serveur** (Windows Server) avec MetaTrader 5 installe. Il n'est pas concu pour le cloud (necessite MT5 avec interface graphique).

## Execution

### Mode continu (boucle infinie)

```powershell
# Activer l'environnement virtuel
.venv\Scripts\Activate.ps1

# Lancer le bot
python run.py
```

Le bot tourne jusqu'a `Ctrl+C`. Il execute un cycle toutes les `ANALYSIS_INTERVAL_MINUTES` (defaut 15 min).

### Mode execution unique

```powershell
python run.py --once
```

Utile pour :
- Tester le bot sans engagement
- Deboguer un probleme
- Execution planifiee via le Planificateur de taches Windows

### Affichage des statistiques

```powershell
python run.py --stats
```

Affiche les statistiques de la base SQLite sans lancer d'analyse.

## Logs

Les logs sont geres par **Loguru** :

| Sortie | Emplacement | Format |
|---|---|---|
| Console | Stderr | `HH:MM:SS | NIVEAU | message` (colore) |
| Fichier | `logs/trading-bot.log` | `YYYY-MM-DD HH:mm:ss.SSS | NIVEAU | module:fonction:ligne | message` |

Configuration :
- Rotation : 10 MB par fichier
- Retention : 7 jours
- Niveau : configurable via `LOG_LEVEL` dans le `.env`

```powershell
# Surveiller les logs en temps reel (PowerShell)
Get-Content logs/trading-bot.log -Tail 20 -Wait

# Ou avec tail pour Windows
Get-Content logs/trading-bot.log -Tail 50
```

## Base de donnees

**Emplacement** : `data/trading.db` (configurable via `DATABASE_PATH`)

Le bot cree et maintient automatiquement la base. Pour inspecter :

```powershell
# Avec SQLite (si installe)
sqlite3 data/trading.db "SELECT * FROM trades ORDER BY opened_at DESC LIMIT 10;"

# Ou avec un outil graphique (DB Browser for SQLite, DBeaver)
```

## Planification automatique (Windows Task Scheduler)

Pour lancer le bot automatiquement au demarrage de Windows :

1. Ouvrir le Planificateur de taches
2. Creer une tache :
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
