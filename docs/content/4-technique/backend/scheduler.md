# Module Scheduler : scheduler.py

**Fichier** : `src/scheduler/scheduler.py`

## Vue d'ensemble

Le scheduler est l'orchestrateur du bot. Il coordonne l'execution des cycles d'analyse et de trading, soit en mode unique, soit en boucle continue.

```mermaid
flowchart TD
    run[run.py] --> run_forever
    run --> run_once
    run_forever -->|APScheduler toutes les N min| run_once
    run_once --> reconcile[reconcile_closed_positions]
    reconcile --> bridge_connect[bridge.connect()]
    bridge_connect --> is_open{is_market_open?}
    is_open -->|Non| return[Retour]
    is_open -->|Oui| capture[screenshots.capture_chart]
    capture --> rates[bridge.get_rates]
    rates --> indicators[indicators.compute_all]
    indicators --> calendar[calendar.fetch_events]
    calendar --> news{News HIGH impact ?}
    news -->|Oui| return
    news -->|Non| ai[ai_vision.analyze]
    ai --> strategy[strategy.execute_decision]
    strategy --> log[database.log_analysis]
    log --> disconnect[bridge.disconnect]
    disconnect --> cleanup[screenshots.cleanup_old_screenshots]
```

## Fonctions

### `run_once() -> None`

Execute un cycle complet d'analyse et de trading.

**Etapes** :

1. **Reconciliation** - `reconcile_closed_positions(sym)` (v1.1)
2. **Connexion MT5** - `bridge.connect()`
3. **Verification marche** - `bridge.is_market_open()`
4. **Capture screenshot** - `screenshots.capture_chart(sym)`
5. **Calcul indicateurs** - `bridge.get_rates()` + `indicators.compute_all()`
6. **Scraping calendrier** - `calendar.fetch_events()` + `filter_relevant_events()`
7. **Blocage news HIGH** - `_has_high_impact_news_soon()` (v1.1)
8. **Positions et compte** - `executor.get_open_positions()` + `bridge.get_account_info()`
9. **Analyse IA** - `vision.analyze(...)` (si cle API presente et screenshot reussi)
10. **Execution strategique** - `strategy.execute_decision(decision)` + `database.log_trade_open(...)` avec flag `was_executed` corrige APRES execution
11. **Log de l'analyse** - `database.log_analysis(...)` avec `was_executed` reel
12. **Deconnexion et nettoyage** - `bridge.disconnect()` + `screenshots.cleanup_old_screenshots(48h)`

**Gestion d'erreurs** :

```python
try:
    # ... tout le cycle ...
except Exception as e:
    logger.exception(f"Erreur durant le cycle: {e}")
finally:
    bridge.disconnect()
    screenshots.cleanup_old_screenshots(max_age_hours=48)
```

- Toute exception est capturee et logguee
- La deconnexion MT5 et le nettoyage des screenshots ont toujours lieu

### `run_forever() -> None`

Boucle planifiee via APScheduler, alignee sur les clotures de bougies (v1.1).

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BlockingScheduler(timezone="UTC")
scheduler.add_job(
    run_once,
    IntervalTrigger(minutes=settings.analysis_interval_minutes),
    max_instances=1,
    misfire_grace_time=60,
)
scheduler.start()
```

- **Intervalle** : `ANALYSIS_INTERVAL_MINUTES` (defaut 15 minutes)
- **Max instances** : 1 (pas d'execution concurrente)
- **Misfire grace** : 60 secondes (si le cycle precedent a depasse l'intervalle)
- Arret propre sur `Ctrl+C` (KeyboardInterrupt)
- Les erreurs fatales dans `run_once()` sont capturees et logguees, la boucle continue

## Point d'entree (`run.py`)

**Fichier** : `run.py`

Trois modes de lancement :

```bash
python run.py              # Mode continu (boucle infinie)
python run.py --once       # Execution unique + statistiques
python run.py --stats      # Affiche les statistiques uniquement
```

**Banniere de demarrage** (mode continu) :

```
  🤖 TRADING BOT IA - Fusion Markets / MT5
  --------------------------------------------------
  Symbole: EURUSD | Timeframe: M15
  Intervalle: 15 min | Confiance min: 70%
  Risque/trade: 1.0% | Perte/jour max: 3.0%
  --------------------------------------------------
```

**Affichage des statistiques** (mode `--once` ou `--stats`) :

```
┌────────────────────────┬─────────┐
│ Metrique               │ Valeur  │
├────────────────────────┼─────────┤
│ total_closed           │ 15      │
│ wins                   │ 9       │
│ losses                 │ 6       │
│ win_rate               │ 60.0    │
│ total_profit           │ 125.50  │
│ avg_confidence         │ 74.3    │
└────────────────────────┴─────────┘
```
