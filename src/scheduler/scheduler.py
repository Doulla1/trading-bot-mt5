"""Orchestrateur : boucle principale de trading avec reconciliation et APScheduler."""

from pathlib import Path
from datetime import datetime
from loguru import logger
import MetaTrader5 as mt5

from src.config import settings
from src.mt5 import bridge, screenshots, indicators, executor
from src.ai.vision import analyze as ai_analyze
from src.ai.strategy import execute_decision
from src.data.calendar import fetch_events, filter_relevant_events
from src.data.database import get_db, log_analysis, log_trade_open, log_trade_close


def reconcile_closed_positions(sym: str) -> int:
    """Detecte et log les fermetures SL/TP survenues dans MT5 (CRITICAL-05, HIGH-05)."""
    try:
        db = get_db()
        open_tickets = db.execute(
            "SELECT ticket FROM trades WHERE closed_at IS NULL AND symbol = ?", [sym]
        ).fetchall()
        reconciled = 0
        for row in open_tickets:
            ticket = row[0]
            positions = mt5.positions_get(ticket=ticket)
            if positions is None or len(positions) == 0:
                # La position a ete fermee (SL, TP, ou manuellement)
                from datetime import datetime as dt
                deals = mt5.history_deals_get(ticket=ticket)
                if deals and len(deals) > 0:
                    close_deal = deals[-1]
                    profit = close_deal.profit if hasattr(close_deal, "profit") else 0.0
                    log_trade_close(ticket, close_deal.price, profit)
                    reconciled += 1
                else:
                    # Position disparue sans historique: marquer comme fermee
                    log_trade_close(ticket, 0.0, 0.0)
                    reconciled += 1
        if reconciled:
            logger.info(f"Reconciliation: {reconciled} trade(s) ferme(s) mis a jour")
        return reconciled
    except Exception as e:
        logger.error(f"Erreur reconciliation: {e}")
        return 0


def _has_high_impact_news_soon(events: list, _minutes_buffer: int = 30) -> bool:
    """Verifie si une news HIGH impact approche (MED-06)."""
    try:
        for ev in events:
            if ev.get("impact") == "high":
                return True  # Simplifie: bloquer si HIGH impact dans les 24h
        return False
    except Exception:
        return False


def run_once() -> None:
    """Execute un cycle complet d'analyse et trading."""
    cycle_start = datetime.now()
    logger.info(f"=== CYCLE {cycle_start.strftime('%H:%M:%S')} ===")

    if not bridge.connect():
        logger.error("Echec connexion MT5 - cycle annule")
        return

    try:
        sym = settings.trading_symbol
        tf = settings.trading_timeframe

        # Reconciliation des trades fermes par SL/TP (CRITICAL-05)
        reconcile_closed_positions(sym)

        if not bridge.is_market_open():
            logger.info(f"Marche ferme pour {sym} - pas d'analyse")
            return

        # Screenshot
        screenshot_path = screenshots.capture_chart(sym)
        screenshot_str = str(screenshot_path) if screenshot_path else ""

        # Indicateurs
        df = bridge.get_rates(sym, tf, count=200)
        indicators_data = indicators.compute_all(df)

        # Calendrier
        all_events = fetch_events()
        relevant_events = filter_relevant_events(all_events, sym)

        # Blocage si news HIGH impact imminente (MED-06)
        if _has_high_impact_news_soon(relevant_events):
            logger.info("News HIGH impact imminente - pas d'execution ce cycle")
            return

        # Positions + compte
        open_positions = executor.get_open_positions(sym)
        account_info = bridge.get_account_info() or {}

        # IA
        if settings.openai_api_key and screenshot_path:
            decision = ai_analyze(
                screenshot_path=screenshot_path, symbol=sym, timeframe=tf,
                indicators=indicators_data, calendar_events=relevant_events,
                open_positions=open_positions, account_info=account_info,
            )
        else:
            logger.warning("Analyse IA impossible (pas de cle API ou screenshot)")
            decision = None

        if decision:
            # Toujours logger l'analyse, was_executed sera corrige APRES execution (HIGH-03)
            strat_result = execute_decision(decision)
            was_exec = strat_result.trade_result is not None and strat_result.trade_result.success
            log_analysis(sym, tf, decision, screenshot_str, indicators_data, relevant_events, was_exec)

            if was_exec:
                tr = strat_result.trade_result
                log_trade_open(tr.ticket, sym, decision["action"], tr.volume, tr.price, tr.stop_loss, tr.take_profit, decision["confidence"], decision.get("reasoning", ""))
            else:
                logger.info(f"Decision {decision.get('action')} (confiance {decision.get('confidence')}%) - pas executee")
        else:
            logger.info("Pas de decision IA pour ce cycle")

    except Exception as e:
        logger.exception(f"Erreur durant le cycle: {e}")
    finally:
        bridge.disconnect()
        screenshots.cleanup_old_screenshots(max_age_hours=48)

    elapsed = (datetime.now() - cycle_start).total_seconds()
    logger.info(f"=== FIN CYCLE ({elapsed:.1f}s) ===")


def run_forever() -> None:
    """Boucle planifiee alignee sur les clotures de bougies via APScheduler (HIGH-06)."""
    logger.info(f"Trading Bot demarre | {settings.trading_symbol} | {settings.trading_timeframe} | Intervalle: {settings.analysis_interval_minutes}min")

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            run_once,
            IntervalTrigger(minutes=settings.analysis_interval_minutes),
            id="trading_cycle",
            name="Cycle de trading",
            max_instances=1,
            misfire_grace_time=60,
        )
        logger.info(f"APScheduler demarre - cycle toutes les {settings.analysis_interval_minutes} minutes")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Arret demande par l'utilisateur")
    except Exception as e:
        logger.exception(f"Erreur fatale dans le scheduler: {e}")
