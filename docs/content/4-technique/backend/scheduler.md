# Module Scheduler : scheduler.py

**Fichier** : `src/scheduler/scheduler.py`

## Vue d'ensemble

Le scheduler est l'orchestrateur du bot. Il coordonne l'execution des cycles d'analyse et de trading, soit en mode unique, soit en boucle continue.

```mermaid
flowchart TD
    run[run.py] --> run_forever
    run --> run_once
    run_forever -->|APScheduler toutes les N min| run_once
    run_once --> manage[manage_open_positions - Breakeven/Trailing/TimeExit]
    manage --> reconcile[reconcile_closed_positions]
    reconcile --> bridge_connect[bridge.connect()]
    bridge_connect --> is_open{is_market_open?}
    is_open -->|Non| return[Retour]
    is_open -->|Oui| rates_m15[bridge.get_rates M15]
    rates_m15 --> rates_h1[bridge.get_rates H1]
    rates_h1 --> indicators[indicators.compute_all M15+H1]
    indicators --> chart[chart_renderer.render - Ichimoku/EMA/BB]
    chart --> calendar[calendar.fetch_events]
    calendar --> news{News HIGH impact ?}
    news -->|Oui| return
    news -->|Non| ocr[ocr.extract_chart_structure - GPT-4o-mini]
    ocr --> session[_get_session_context - Asian/London/NY]
    session --> history[get_recent_trades + get_statistics]
    history --> deepseek[analyzer.make_decision - DeepSeek V4 Pro]
    deepseek --> strategy[strategy.execute_decision]
    strategy --> log[database.log_analysis]
    log --> disconnect[bridge.disconnect]
    disconnect --> cleanup[screenshots.cleanup_old_screenshots]
```

## Fonctions

### `run_once() -> None`

Execute un cycle complet d'analyse et de trading (v2.1).

**Etapes** :

1. **Gestion active positions** - `manage_open_positions()` : breakeven, trailing stop, time exit
2. **Reconciliation** - `reconcile_closed_positions(sym)` : detection fermetures SL/TP
3. **Connexion MT5** - `bridge.connect()`
4. **Verification marche** - `bridge.is_market_open()`
5. **Indicateurs multi-TF** - `bridge.get_rates(M15, 200)` + `bridge.get_rates(H1, 100)` + `indicators.compute_all()`
6. **Chart genere** - `chart_renderer.render_analysis_chart()` : chart pro avec Ichimoku, EMA, Bollinger, Pivots
7. **Screenshot debug** - `screenshots.capture_chart(sym)`
8. **Calendrier** - `calendar.fetch_events()` + `filter_relevant_events()` + cache 4h
9. **Blocage news HIGH** - `_has_high_impact_news_soon()`
10. **Contexte session** - `_get_session_context()` : Asian/London/NY, jour de semaine
11. **Positions + Compte + Historique** - `executor.get_open_positions()` + `bridge.get_account_info()` + `get_recent_trades(20)` + `get_statistics()`
12. **OCR chart** - `ocr.extract_chart_structure(chart_path)` : GPT-4o-mini extrait phases, niveaux, patterns
13. **Decision DeepSeek** - `analyzer.make_decision(...)` : DeepSeek V4 Pro avec tout le contexte (1M tokens)
14. **Execution** - `strategy.execute_decision(decision)` + `database.log_trade_open()`
15. **Log** - `database.log_analysis()` avec `was_executed` reel
16. **Deconnexion** - `bridge.disconnect()` + `screenshots.cleanup_old_screenshots(48h)`

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
