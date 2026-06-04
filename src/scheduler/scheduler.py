"""Orchestrateur : boucle principale de trading avec reconciliation et APScheduler.

v2.0: Pipeline multi-TF + OCR (GPT-4o-mini) + Analyzer (DeepSeek V4 Pro)
      + Gestion active des positions (breakeven, trailing, time exit)."""

from pathlib import Path
from datetime import datetime
from loguru import logger
import MetaTrader5 as mt5

from src.config import settings
from src.mt5 import bridge, screenshots, indicators, executor, chart_renderer
from src.ai.ocr import extract_chart_structure
from src.ai.analyzer import make_decision, make_decision_fast
from src.ai.strategy import execute_decision, manage_open_positions
from src.data.calendar import fetch_events, filter_relevant_events
from src.data.database import get_db, log_analysis, log_trade_open, log_trade_close, get_recent_trades, get_statistics, log_trade_close


def reconcile_closed_positions(sym: str) -> int:
    """Detecte et log les fermetures SL/TP survenues dans MT5 (CRITICAL-05, HIGH-05)."""
    try:
        db = get_db()
        open_tickets = db.execute(
            "SELECT ticket FROM trades WHERE closed_at IS NULL AND symbol = ?", [sym]
        ).fetchall()
        reconciled = 0
        for row in open_tickets:
            deal_ticket = row[0]
            positions = mt5.positions_get(ticket=deal_ticket)
            if positions is None or len(positions) == 0:
                # La position a ete fermee (SL, TP, ou manuellement)
                # BUG-FIX: deal_ticket est un deal ticket, pas un position ID.
                # On doit d'abord retrouver le position_id via le deal, puis
                # chercher les deals de cette position.
                deal_info = mt5.history_deals_get(ticket=deal_ticket)
                if deal_info and len(deal_info) > 0:
                    pos_id = deal_info[0].position_id
                    deals = mt5.history_deals_get(position=pos_id)
                else:
                    deals = None

                if deals and len(deals) > 0:
                    # Chercher specifiquement le deal de SORTIE (entry=1 = OUT)
                    close_deal = next((d for d in deals if d.entry == 1), None)
                    if close_deal:
                        log_trade_close(deal_ticket, close_deal.price, close_deal.profit)
                    else:
                        # Fallback: prendre le dernier deal (souvent le OUT)
                        last_deal = deals[-1]
                        log_trade_close(deal_ticket, last_deal.price, last_deal.profit)
                    reconciled += 1
                else:
                    # Position disparue sans historique: marquer comme fermee
                    log_trade_close(deal_ticket, 0.0, 0.0)
                    reconciled += 1
        if reconciled:
            logger.info(f"Reconciliation: {reconciled} trade(s) ferme(s) mis a jour")
        return reconciled
    except Exception as e:
        logger.error(f"Erreur reconciliation: {e}")
        return 0


def _has_high_impact_news_soon(events: list, _minutes_buffer: int = 30) -> bool:
    """Verifie si une news HIGH impact approche dans les N prochaines minutes.

    Les heures des evenements sont en UTC (converties par investing_calendar
    ou fournies en UTC par les autres sources). On compare avec datetime.utcnow()
    pour eviter tout decalage de fuseau horaire.
    """
    try:
        now_utc = datetime.utcnow()
        for ev in events:
            if ev.get("impact") != "high":
                continue
            event_time_str = ev.get("time", "")
            if not event_time_str or event_time_str == "All day":
                logger.debug(f"News HIGH sans heure precise: {ev.get('event')}")
                continue
            try:
                # Format attendu: "HH:MM" (toujours en UTC)
                parts = event_time_str.split(":")
                event_hour = int(parts[0])
                event_minute = int(parts[1]) if len(parts) > 1 else 0
                ev_date = ev.get("date", now_utc.strftime("%Y-%m-%d"))
                if ev_date != now_utc.strftime("%Y-%m-%d"):
                    continue
                event_dt = now_utc.replace(hour=event_hour, minute=event_minute, second=0, microsecond=0)
                minutes_until = (event_dt - now_utc).total_seconds() / 60
                if 0 < minutes_until <= _minutes_buffer:
                    logger.info(f"News HIGH dans {minutes_until:.0f} min UTC: {ev.get('event')} - pas d'execution")
                    return True
                elif -5 < minutes_until <= 0:
                    logger.info(f"News HIGH en cours/recente: {ev.get('event')} - pas d'execution")
                    return True
            except (ValueError, TypeError):
                continue
        return False
    except Exception:
        return False


def _get_session_context() -> dict:
    """Contexte de session: heure UTC, jour, session de marche (v2.0)."""
    now_utc = datetime.utcnow()
    # Sessions forex en UTC (aligne avec run_multi.py - INC-A fix):
    #   Asian:          22:00-08:00 UTC
    #   London:         08:00-13:00 UTC
    #   London_NY_ovlp: 13:00-17:00 UTC  (periode la plus liquide)
    #   New_York:       17:00-22:00 UTC
    hour_utc = now_utc.hour
    if 22 <= hour_utc or hour_utc < 8:
        session = "Asian"
    elif 8 <= hour_utc < 13:
        session = "London"
    elif 13 <= hour_utc < 17:
        session = "London_New_York_overlap"
    elif 17 <= hour_utc < 22:
        session = "New_York"
    else:
        session = "Low_liquidity"
    return {
        "datetime": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "session": session,
        "day_of_week": now_utc.strftime("%A"),
        "hour": hour_utc,
    }


def run_once() -> None:
    """Execute un cycle complet d'analyse et trading (v2.0)."""
    cycle_start = datetime.now()
    logger.info(f"=== CYCLE {cycle_start.strftime('%H:%M:%S')} ===")

    if not bridge.connect():
        logger.error("Echec connexion MT5 - cycle annule")
        return

    try:
        sym = settings.trading_symbol
        tf = settings.trading_timeframe

        # 0. Gestion active des positions (breakeven, trailing, time exit) v2.0
        manage_open_positions()

        # 1. Reconciliation des trades fermes par SL/TP
        reconcile_closed_positions(sym)

        if not bridge.is_market_open():
            logger.info(f"Marche ferme pour {sym} - pas d'analyse")
            return

        # 2. Indicateurs multi-TF v2.0
        df_m15 = bridge.get_rates(sym, "M15", count=200)
        df_h1 = bridge.get_rates(sym, "H1", count=100)
        indicators_data = indicators.compute_all(df_m15, df_h1)

        # 3. Screenshot (debug) + Chart genere pour OCR v2.1
        screenshot_path = screenshots.capture_chart(sym)
        screenshot_str = str(screenshot_path) if screenshot_path else ""
        chart_path = chart_renderer.render_analysis_chart(df_m15, indicators_data, sym)

        # 4. Calendrier
        all_events = fetch_events()
        relevant_events = filter_relevant_events(all_events, sym)

        if _has_high_impact_news_soon(relevant_events):
            logger.info("News HIGH impact imminente - pas d'execution ce cycle")
            return

        # 5. Contexte de session
        session_context = _get_session_context()

        # 6. Positions + compte + historique + stats de performance v2.1
        open_positions = executor.get_open_positions(sym)
        account_info = bridge.get_account_info() or {}
        trade_history = get_recent_trades(limit=20)
        performance_stats = get_statistics(symbol=sym)  # stats filtrees par symbole (INC-B fix)

        # 7. OCR du chart via GPT-4o-mini (utilise le chart genere) v2.1
        ocr_data = None
        if settings.openai_api_key and chart_path:
            ocr_data = extract_chart_structure(chart_path, sym, tf)

        # 8. Decision via l'IA configuree dans .env (v4.0)
        decision = None
        if settings.ai_api_key_resolved:
            decision = make_decision(
                indicators=indicators_data, ocr_data=ocr_data,
                calendar_events=relevant_events, open_positions=open_positions,
                account_info=account_info, trade_history=trade_history,
                session_context=session_context,
                performance_stats=performance_stats,
            )
        elif settings.openai_api_key and screenshot_path:
            # Fallback: GPT-4o-mini Vision (ancien pipeline)
            from src.ai.vision import analyze as ai_analyze
            decision = ai_analyze(
                screenshot_path=screenshot_path, symbol=sym, timeframe=tf,
                indicators=indicators_data, calendar_events=relevant_events,
                open_positions=open_positions, account_info=account_info,
            )
        else:
            logger.warning("Analyse IA impossible (pas de cle API)")

        # 9. Log + execution
        if decision:
            # BUG-A: enrichir la decision avec les indicateurs pour les filtres RSI/BB (PROB-8)
            decision["indicators"] = indicators_data
            strat_result = execute_decision(decision)
            was_exec = strat_result.trade_result is not None and strat_result.trade_result.success
            log_analysis(sym, tf, decision, screenshot_str, indicators_data, relevant_events, was_exec)

            if was_exec:
                tr = strat_result.trade_result
                log_trade_open(tr.ticket, sym, decision["action"], tr.volume,
                               tr.price, tr.stop_loss, tr.take_profit,
                               decision["confidence"], decision.get("reasoning", ""))
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
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            run_once,
            IntervalTrigger(minutes=settings.analysis_interval_minutes),
            id="trading_cycle",
            name="Cycle de trading",
            max_instances=1,
            misfire_grace_time=60,
        )

        # Job rapport journalier a l'heure configuree (defaut 23:00 UTC)
        try:
            from src.reports.daily_report import send_daily_report
            scheduler.add_job(
                send_daily_report,
                CronTrigger(hour=settings.report_send_hour_utc, minute=settings.report_send_minute_utc),
                id="daily_report",
                name="Rapport journalier par email",
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info(
                f"Rapport journalier programme a {settings.report_send_hour_utc:02d}:{settings.report_send_minute_utc:02d} UTC"
            )
        except Exception as e:
            logger.warning(f"Impossible de programmer le rapport journalier: {e}")

        logger.info(f"APScheduler demarre - cycle toutes les {settings.analysis_interval_minutes} minutes")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Arret demande par l'utilisateur")
    except Exception as e:
        logger.exception(f"Erreur fatale dans le scheduler: {e}")
