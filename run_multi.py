#!/usr/bin/env python3
"""Lanceur multi-symboles - une seule instance, tous les actifs en sequentiel.

Resout le probleme MT5 (connexion unique) et gere intelligemment
les timeframes (M15 pour le forex, H1 pour XAUUSD)."""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
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


# Configuration des symboles (Majeures + Crosses pour diversification)
SYMBOLS = [
    {"symbol": "EURUSD", "timeframe": "M15", "magic": 73456, "interval_min": 15},
    {"symbol": "GBPUSD", "timeframe": "M15", "magic": 73457, "interval_min": 15},
    {"symbol": "AUDUSD", "timeframe": "M15", "magic": 73458, "interval_min": 15},
    {"symbol": "USDJPY", "timeframe": "M15", "magic": 73459, "interval_min": 15},
    {"symbol": "USDCHF", "timeframe": "M15", "magic": 73460, "interval_min": 15},
    {"symbol": "XAUUSD", "timeframe": "H1",   "magic": 73461, "interval_min": 60},
    # --- CROSSES NON-USD ---
    {"symbol": "EURGBP", "timeframe": "M15", "magic": 73462, "interval_min": 15},
    {"symbol": "EURJPY", "timeframe": "M15", "magic": 73463, "interval_min": 15},
    {"symbol": "GBPJPY", "timeframe": "M15", "magic": 73464, "interval_min": 15},
]

# Compteurs pour savoir quel symbole doit tourner a chaque round
_cycle_counts = {s["symbol"]: 0 for s in SYMBOLS}


def _should_run(cfg: dict, current_round: int) -> bool:
    """Decide si un symbole doit etre analyse ce round (en fonction de sa periodicite)."""
    interval_rounds = max(1, cfg["interval_min"] // 15)  # M15=1, H1=4
    return current_round % interval_rounds == 0


def _get_session_context() -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # BUG-4: utilise UTC
    hour = now.hour
    # Bornes UTC correctes: Asie 22-08, Londres 08-16, New York 13-22
    if hour >= 22 or hour < 8:
        session = "Asian"
    elif 8 <= hour < 13:
        session = "London"
    elif 13 <= hour < 17:
        session = "London_New_York_overlap"
    elif 17 <= hour < 22:
        session = "New_York"
    else:
        session = "Low_liquidity"
    return {"datetime": now.strftime("%Y-%m-%d %H:%M UTC"), "session": session, "day_of_week": now.strftime("%A"), "hour": hour}


def _reconcile_closed_positions(sym: str) -> None:
    """Reconciliation des trades fermes (BUG-2: utiliser history_deals_get(position=) et chercher le deal de sortie)."""
    import MetaTrader5 as mt5
    from datetime import datetime, timedelta
    try:
        db = get_db()
        open_tickets = db.execute(
            "SELECT ticket FROM trades WHERE closed_at IS NULL AND symbol = ?", [sym]
        ).fetchall()
        
        if not open_tickets:
            return
            
        # Charger l'historique MT5 pour le mois courant pour remplir le cache
        now = datetime.now()
        mt5.history_deals_get(now - timedelta(days=30), now + timedelta(days=1))
        
        for row in open_tickets:
            ticket = row[0]
            if mt5.positions_get(ticket=ticket) is None or len(mt5.positions_get(ticket=ticket)) == 0:
                # Position fermee - recuperer le deal de SORTIE (entry=1 = OUT)
                deals = mt5.history_deals_get(position=ticket)
                close_deal = None
                if deals:
                    close_deal = next((d for d in deals if d.entry == 1), None)
                if close_deal:
                    total_profit = close_deal.profit + close_deal.commission + close_deal.swap
                    
                    # Determiner la raison via le commentaire MT5 (souvent "sl", "tp", ou vide)
                    reason = "EXPERT"
                    comment = close_deal.comment.lower() if close_deal.comment else ""
                    if "sl" in comment:
                        reason = "SL"
                    elif "tp" in comment:
                        reason = "TP"
                        
                    log_trade_close(ticket, close_deal.price, total_profit, reason=reason, symbol=sym)
                else:
                    # Ne pas logguer 0.0 si on ne trouve pas le deal ! Reessayer plus tard
                    logger.warning(f"Position {ticket} fermee mais deal introuvable, tentative differee")
    except Exception as e:
        logger.error(f"Erreur reconciliation pour {sym}: {e}")


def _has_high_impact_news_soon(events: list) -> bool:
    """Blocage news HIGH <30 min (BUG-4: utilise UTC pour comparer avec les events UTC)."""
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC
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
            rotation="00:00",
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

    # Indicateurs M15 + H1 + H4
    df_m15 = bridge.get_rates(sym, "M15", count=200)
    df_h1 = bridge.get_rates(sym, tf if tf == "H1" else "H1", count=100) if tf != "H1" else None
    df_h4 = bridge.get_rates(sym, "H4", count=50) if tf != "H4" and tf != "H1" else None
    ind_data = indicators.compute_all(df_m15, df_h1, df_h4)

    # Calendrier
    all_events = fetch_events()
    relevant = filter_relevant_events(all_events, sym)

    if _has_high_impact_news_soon(relevant):
        logger.warning(f"[{sym}] News HIGH imminente (<30 min) - Mode protection active")
        
        # Liquidation d'urgence des positions ouvertes pour eviter le slippage
        open_pos = executor.get_open_positions(sym)
        if open_pos:
            logger.warning(f"[{sym}] Cloture d'urgence de {len(open_pos)} position(s) ouverte(s) avant l'annonce !")
            for pos in open_pos:
                res = executor.close_position(pos["ticket"])
                if res.success:
                    logger.info(f"[{sym}] Trade {pos['ticket']} securise (Ferme avant News)")
                    # Force la reconciliation immediate pour eviter le log 0.0
                    _reconcile_closed_positions(sym)
        
        logger.info(f"[{sym}] Pas d'execution (pause pendant la tempete)")
        return

    # Chart genere et OCR (Rendu optionnel via USE_VISION_OCR pour eviter hallucinations et latence)
    chart_path = None
    ocr_data = None
    if settings.use_vision_ocr:
        chart_path = chart_renderer.render_analysis_chart(df_m15, ind_data, sym)
        if chart_path:
            ocr_data = extract_chart_structure(chart_path, sym, tf)
    else:
        logger.debug(f"[{sym}] OCR desactive (settings.use_vision_ocr=False)")

    # DeepSeek
    open_positions = executor.get_open_positions(sym)
    account_info = bridge.get_account_info() or {}
    trade_history = get_recent_trades(limit=20, symbol=sym)
    perf_stats = get_statistics(symbol=sym)
    session_ctx = _get_session_context()

    decision = make_decision(
        indicators=ind_data, ocr_data=ocr_data,
        calendar_events=relevant, open_positions=open_positions,
        account_info=account_info, trade_history=trade_history,
        session_context=session_ctx, performance_stats=perf_stats,
    )

    if decision:
        # Enrichir la decision avec les indicateurs pour les filtres (PROB-8)
        decision["indicators"] = ind_data
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
