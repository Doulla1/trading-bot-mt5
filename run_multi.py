#!/usr/bin/env python3
"""Lanceur multi-symboles - une seule instance, tous les actifs en sequentiel.

Resout le probleme MT5 (connexion unique) et gere intelligemment
les timeframes (M15 pour le forex, H1 pour XAUUSD)."""

import os
import sys
import time
from pathlib import Path
from datetime import datetime
from loguru import logger
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.logger import setup_logger
from src.mt5 import bridge, screenshots, indicators, executor, chart_renderer
from src.ai.ocr import extract_chart_structure
from src.ai.analyzer import make_decision
from src.ai.strategy import execute_decision, manage_open_positions
from src.data.calendar import fetch_events, filter_relevant_events
from src.data.database import get_db, log_analysis, log_trade_open, log_trade_close, get_recent_trades, get_statistics


# Configuration des 6 symboles
SYMBOLS = [
    {"symbol": "EURUSD", "timeframe": "M15", "magic": 73456, "interval_min": 15},
    {"symbol": "GBPUSD", "timeframe": "M15", "magic": 73457, "interval_min": 15},
    {"symbol": "AUDUSD", "timeframe": "M15", "magic": 73458, "interval_min": 15},
    {"symbol": "USDJPY", "timeframe": "M15", "magic": 73459, "interval_min": 15},
    {"symbol": "USDCHF", "timeframe": "M15", "magic": 73460, "interval_min": 15},
    {"symbol": "XAUUSD", "timeframe": "H1",   "magic": 73461, "interval_min": 60},
]

# Compteurs pour savoir quel symbole doit tourner a chaque round
_cycle_counts = {s["symbol"]: 0 for s in SYMBOLS}


def _should_run(cfg: dict, current_round: int) -> bool:
    """Decide si un symbole doit etre analyse ce round (en fonction de sa periodicite)."""
    interval_rounds = max(1, cfg["interval_min"] // 15)  # M15=1, H1=4
    return current_round % interval_rounds == 0


def _get_session_context() -> dict:
    now = datetime.now()
    hour = now.hour
    session = "Asian" if 2 <= hour < 8 else "London" if 8 <= hour < 15 else "New_York" if 15 <= hour < 21 else "Low_liquidity"
    return {"datetime": now.strftime("%Y-%m-%d %H:%M UTC"), "session": session, "day_of_week": now.strftime("%A"), "hour": hour}


def _reconcile_closed_positions(sym: str) -> None:
    """Reconciliation des trades fermes."""
    import MetaTrader5 as mt5
    try:
        db = get_db()
        open_tickets = db.execute(
            "SELECT ticket FROM trades WHERE closed_at IS NULL AND symbol = ?", [sym]
        ).fetchall()
        for row in open_tickets:
            ticket = row[0]
            if mt5.positions_get(ticket=ticket) is None or len(mt5.positions_get(ticket=ticket)) == 0:
                deals = mt5.history_deals_get(ticket=ticket)
                if deals and len(deals) > 0:
                    log_trade_close(ticket, deals[-1].price, deals[-1].profit)
                else:
                    log_trade_close(ticket, 0.0, 0.0)
    except Exception:
        pass


def _has_high_impact_news_soon(events: list) -> bool:
    """Blocage news HIGH <30 min."""
    try:
        now = datetime.now()
        for ev in events:
            if ev.get("impact") != "high":
                continue
            ev_date = ev.get("date", now.strftime("%Y-%m-%d"))
            if ev_date != now.strftime("%Y-%m-%d"):
                continue
            try:
                parts = ev.get("time", "").split(":")
                if len(parts) < 2:
                    continue
                event_dt = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
                mins = (event_dt - now).total_seconds() / 60
                if 0 < mins <= 30 or (-5 < mins <= 0):
                    return True
            except (ValueError, TypeError):
                continue
        return False
    except Exception:
        return False


def run_symbol(cfg: dict) -> None:
    """Execute un cycle complet pour un symbole."""
    sym = cfg["symbol"]
    tf = cfg["timeframe"]
    magic = cfg["magic"]

    # Surcharger les settings pour ce symbole
    from src.config import settings
    previous_symbol = settings.trading_symbol
    settings.trading_symbol = sym
    settings.trading_timeframe = tf
    settings.mt5_magic_number = magic

    # Reconfigurer le logger pour ecrire dans le bon dossier de symbole
    if sym != previous_symbol:
        from loguru import logger as loguru_logger
        loguru_logger.remove()  # supprime les handlers existants
        loguru_logger.add(
            sys.stderr,
            level=settings.log_level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            colorize=True,
        )
        loguru_logger.add(
            str(settings.log_path),
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="1 day",
            retention="15 days",
            encoding="utf-8",
        )
        logger.info(f"Logger reconfigure pour {sym} -> {settings.log_path}")

    logger.info(f"--- {sym} {tf} ---")

    # Gestion positions
    manage_open_positions()

    # Reconciliation
    _reconcile_closed_positions(sym)

    if not bridge.is_market_open():
        logger.info(f"[{sym}] Marche ferme")
        return

    # Indicateurs M15 + H1
    df_m15 = bridge.get_rates(sym, "M15", count=200)
    df_h1 = bridge.get_rates(sym, tf if tf == "H1" else "H1", count=100) if tf != "H1" else None
    ind_data = indicators.compute_all(df_m15, df_h1)

    # Chart genere
    chart_path = chart_renderer.render_analysis_chart(df_m15, ind_data, sym)

    # Calendrier
    all_events = fetch_events()
    relevant = filter_relevant_events(all_events, sym)

    if _has_high_impact_news_soon(relevant):
        logger.info(f"[{sym}] News HIGH - pas d'execution")
        return

    # OCR
    ocr_data = None
    if chart_path:
        ocr_data = extract_chart_structure(chart_path, sym, tf)

    # DeepSeek
    open_positions = executor.get_open_positions(sym)
    account_info = bridge.get_account_info() or {}
    trade_history = get_recent_trades(limit=20)
    perf_stats = get_statistics()
    session_ctx = _get_session_context()

    decision = make_decision(
        indicators=ind_data, ocr_data=ocr_data,
        calendar_events=relevant, open_positions=open_positions,
        account_info=account_info, trade_history=trade_history,
        session_context=session_ctx, performance_stats=perf_stats,
    )

    if decision:
        strat_result = execute_decision(decision)
        was_exec = strat_result.trade_result is not None and strat_result.trade_result.success
        log_analysis(sym, tf, decision, str(chart_path) if chart_path else "",
                     ind_data, relevant, was_exec)
        if was_exec:
            tr = strat_result.trade_result
            log_trade_open(tr.ticket, sym, decision["action"], tr.volume,
                           tr.price, tr.stop_loss, tr.take_profit,
                           decision["confidence"], decision.get("reasoning", ""))
    else:
        logger.info(f"[{sym}] Pas de decision")


def run_all() -> None:
    """Boucle principale: tous les symboles, toutes les 15 min."""
    logger.info("=== DEMARRAGE MULTI-SYMBOLES ===")
    logger.info(f"Symboles: {', '.join(s['symbol'] for s in SYMBOLS)}")
    logger.info(f"Periodicite: 15 min (forex), 60 min (XAUUSD)")

    round_num = 0
    while True:
        try:
            round_num += 1
            logger.info(f"=== ROUND {round_num} ===")

            if not bridge.connect():
                logger.error("Echec connexion MT5")
                time.sleep(60)
                continue

            try:
                for cfg in SYMBOLS:
                    if _should_run(cfg, round_num):
                        run_symbol(cfg)
                    else:
                        logger.debug(f"[{cfg['symbol']}] Saute (periodicite {cfg['interval_min']}min)")
            finally:
                bridge.disconnect()
                screenshots.cleanup_old_screenshots(max_age_hours=48)

            logger.info(f"=== FIN ROUND {round_num} ===")

        except KeyboardInterrupt:
            logger.info("Arret demande")
            break
        except Exception as e:
            logger.exception(f"Erreur fatale: {e}")

        time.sleep(15 * 60)  # 15 min entre chaque round


if __name__ == "__main__":
    setup_logger()
    run_all()
