"""Moteur de strategie : combine IA, indicateurs et gestion des risques."""

import MetaTrader5 as mt5
from loguru import logger
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings
from src.mt5.bridge import get_account_info, get_symbol_info, is_market_open
from src.mt5.executor import (
    open_position, close_position, calculate_position_size,
    get_open_positions, count_open_positions, TradeResult,
)
from src.data.database import get_db, log_trade_close


@dataclass
class StrategyResult:
    """Resultat d'un cycle de strategie."""
    decision: dict | None
    trade_result: Optional[TradeResult] = None
    closed_positions: list = field(default_factory=list)


def execute_decision(decision: dict) -> StrategyResult:
    """Execute la decision de l'IA avec les regles de risk management."""
    result = StrategyResult(decision=decision)
    action = decision["action"]

    guard_result = _check_pre_trade_guards(action)
    if guard_result is not None:
        return guard_result

    account = get_account_info()
    symbol_info = get_symbol_info()
    balance = account.get("balance", 0)

    # CLOSE
    if action == "CLOSE":
        for pos in get_open_positions():
            close_res = close_position(pos["ticket"])
            result.closed_positions.append(close_res)
        return result

    # BUY / SELL
    if action in ("BUY", "SELL"):
        sym = settings.trading_symbol
        open_positions = get_open_positions(sym)

        # Si position deja ouverte dans la direction opposee
        if open_positions:
            existing_pos = open_positions[0]
            existing_dir = "BUY" if existing_pos.get("type") == mt5.POSITION_TYPE_BUY else "SELL"
            if existing_dir != action:
                # Signaux opposes: fermer la position, NE PAS inverser immediatement
                # Le prochain cycle decidera si une nouvelle position est justifiee
                logger.info(f"Fermeture {existing_dir} (signaux opposes), pas de reversal immediat")
                close_res = close_position(existing_pos["ticket"])
                result.closed_positions.append(close_res)
                # BUG-D: log immediat pour ne pas attendre la reconciliation
                if close_res.success:
                    deals = mt5.history_deals_get(position=existing_pos["ticket"])
                    close_deal = next((d for d in deals if d.entry == 1), None) if deals else None
                    log_trade_close(
                        existing_pos["ticket"],
                        close_res.price,
                        close_deal.profit if close_deal else 0.0,
                    )
                return result
            else:
                # Meme direction: on garde la position, le trailing/breakeven s'en occupe
                logger.info(f"Deja {existing_dir} - position conservee, gestion active en cours")
                return result

        # Aucune position: filtrer et ouvrir si OK
        if not _passes_trade_filters(decision, symbol_info):
            return result
        # ... reste du code existant ...

        stop_loss_pips = decision["stop_loss_pips"]
        take_profit_pips = decision["take_profit_pips"]
        volume = calculate_position_size(balance, stop_loss_pips, symbol_info)
        point = symbol_info.get("point", 0.00001)
        digits = symbol_info.get("digits", 5)

        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            logger.error(f"Tick introuvable pour {sym}")
            return result

        if action == "BUY":
            entry = tick.ask
            sl_price = round(entry - (stop_loss_pips * 10 * point), digits)
            tp_price = round(entry + (take_profit_pips * 10 * point), digits)
        else:
            entry = tick.bid
            sl_price = round(entry + (stop_loss_pips * 10 * point), digits)
            tp_price = round(entry - (take_profit_pips * 10 * point), digits)

        trade_result = open_position(
            direction=action, volume=volume, stop_loss=sl_price,
            take_profit=tp_price, comment=f"IA confiance={decision['confidence']}%",
        )
        result.trade_result = trade_result
        return result

    logger.info(f"Decision: HOLD (confiance {decision['confidence']}%)")
    return result


def _check_pre_trade_guards(_action: str) -> StrategyResult | None:
    """Verifie les gardes pre-trade: marche ouvert, perte jour, compte, symbole."""
    result = StrategyResult(decision=None)
    if not is_market_open():
        logger.info("Marche ferme - aucune execution")
        return result
    if get_account_info() is None:
        logger.error("Impossible de recuperer les infos du compte")
        return result
    if get_symbol_info() is None:
        logger.error("Impossible de recuperer les infos du symbole")
        return result
    # Daily loss limit
    account = get_account_info()
    balance = account.get("balance", 0)
    daily_pnl = _get_daily_pnl()
    if balance > 0 and daily_pnl < 0 and abs(daily_pnl) / balance * 100 >= settings.max_daily_loss_pct:
        logger.warning(f"LIMITE PERTE JOURNALIERE ATTEINTE: {abs(daily_pnl)/balance*100:.1f}%")
        return result
    return None


def _passes_trade_filters(decision: dict, symbol_info: dict) -> bool:
    """Applique les filtres pre-trade: confiance, max positions, spread, circuit breaker, RSI/BB."""
    confidence = decision["confidence"]
    if confidence < settings.min_confidence_threshold:
        logger.info(f"Confiance {confidence}% < seuil {settings.min_confidence_threshold}%")
        return False
    if count_open_positions() >= settings.max_open_positions:
        logger.info("Max positions atteint - pas d'execution")
        return False
    spread = symbol_info.get("spread", 999)
    if spread > 30:
        logger.warning(f"Spread trop eleve: {spread} points > 30 max")
        return False
    if _circuit_breaker_active():
        logger.info("Circuit breaker actif - pas d'execution")
        return False
    consecutive_losses = _count_consecutive_losses()
    if consecutive_losses >= 4:
        logger.warning(f"CIRCUIT BREAKER: {consecutive_losses} pertes consecutives - pause 4h")
        _set_circuit_breaker_until(hours=4)
        return False
    # v3.0: Filtres RSI/BB conditionnes au regime de marche
    # En tendance forte (ADX > 25), le RSI peut rester surachete/survendu pendant des heures
    # et le prix surfe sur les bandes de Bollinger. On ne bloque PAS ces entrees.
    # En ranging (ADX <= 25), on applique les filtres mean-reversion.
    indicators = decision.get("indicators", {})
    rsi = indicators.get("rsi_14", 50) if indicators else 50
    bb_pos = indicators.get("bb_position_pct", 50) if indicators else 50
    action = decision.get("action", "")
    adx = indicators.get("adx_14", 20) if indicators else 20
    if adx is not None and adx <= 25:
        if action == "BUY" and rsi > 75:
            logger.info(f"Filtre RSI/BB (ranging): BUY bloque (RSI={rsi:.1f} > 75, ADX={adx:.1f})")
            return False
        if action == "SELL" and rsi < 25:
            logger.info(f"Filtre RSI/BB (ranging): SELL bloque (RSI={rsi:.1f} < 25, ADX={adx:.1f})")
            return False
        if action == "BUY" and isinstance(bb_pos, (int, float)) and bb_pos > 100:
            logger.info(f"Filtre RSI/BB (ranging): BUY bloque (BB_position={bb_pos:.0f}%, ADX={adx:.1f})")
            return False
        if action == "SELL" and isinstance(bb_pos, (int, float)) and bb_pos < 0:
            logger.info(f"Filtre RSI/BB (ranging): SELL bloque (BB_position={bb_pos:.0f}%, ADX={adx:.1f})")
            return False
    elif adx is not None and adx > 25:
        logger.debug(f"Filtres RSI/BB desactives: ADX={adx:.1f} > 25 (marche en tendance)")
    return True


def _get_daily_pnl() -> float:
    """Calcule le P&L du jour : trades fermes + floating P&L (CRITICAL-02)."""
    try:
        db = get_db()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        rows = db.execute(
            "SELECT COALESCE(SUM(profit), 0) FROM trades "
            "WHERE DATE(opened_at) = ? AND profit IS NOT NULL", [today]
        ).fetchall()
        realized_pnl = rows[0][0] if rows else 0.0
        # Ajouter le floating P&L des positions ouvertes
        positions = mt5.positions_get()
        floating_pnl = sum(p.profit for p in positions) if positions else 0.0
        return realized_pnl + floating_pnl
    except Exception:
        return 0.0


def _count_consecutive_losses() -> int:
    """Compte les pertes consecutives (HIGH-08)."""
    try:
        db = get_db()
        rows = db.execute(
            "SELECT profit FROM trades WHERE profit IS NOT NULL ORDER BY closed_at DESC LIMIT 10"
        ).fetchall()
        count = 0
        for r in rows:
            if r[0] is not None and r[0] < 0:
                count += 1
            else:
                break
        return count
    except Exception:
        return 0


def _set_circuit_breaker_until(hours: int = 4) -> None:
    """Active le circuit breaker pour N heures (HIGH-08)."""
    try:
        db = get_db()
        from datetime import datetime, timedelta
        until = (datetime.now() + timedelta(hours=hours)).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('circuit_breaker_until', ?)",
            [until],
        )
        db.commit()
    except Exception:
        pass


def _circuit_breaker_active() -> bool:
    """Verifie si le circuit breaker est actif (HIGH-08)."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM bot_state WHERE key = 'circuit_breaker_until'"
        ).fetchone()
        if row is None:
            return False
        from datetime import datetime
        until = datetime.fromisoformat(row[0])
        return datetime.now() < until
    except Exception:
        return False


# ============================================================
# Gestion des positions (breakeven, trailing stop, time exit) v2.0
# ============================================================

def manage_open_positions() -> int:
    """Applique breakeven, trailing stop, time exit aux positions ouvertes.
    Appele au debut de chaque cycle. Retourne le nombre de modifications."""
    sym = settings.trading_symbol
    modifications = 0
    for pos in get_open_positions(sym):
        if _apply_breakeven(pos):
            modifications += 1
        elif _apply_trailing_stop(pos):
            modifications += 1
        if _check_time_exit(pos):
            close_position(pos["ticket"], sym)
            modifications += 1
    return modifications


def _apply_breakeven(pos: dict) -> bool:
    """Deplace le SL au prix d'entree quand le profit >= 1.2x SL initial.
    v3.0: seuil a 1.2R pour couvrir commissions/swaps et laisser respirer le trade."""
    entry_price = pos.get("price_open", 0)
    current_sl = pos.get("sl", 0)
    ticket = pos.get("ticket", 0)
    tick = mt5.symbol_info_tick(settings.trading_symbol)
    sym_info = mt5.symbol_info(settings.trading_symbol)

    if tick is None or sym_info is None or entry_price == 0:
        return False

    if pos.get("type") == mt5.POSITION_TYPE_BUY:
        sl_distance_pips = (entry_price - current_sl) / (10 * sym_info.point) if current_sl else 0
        profit_distance_pips = (tick.bid - entry_price) / (10 * sym_info.point)
        # v3.0: Breakeven a 1.2R (couvre commissions/swaps + marge de respiration)
        if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl < entry_price:
            _modify_sl(ticket, entry_price)
            logger.info(f"BREAKEVEN: ticket {ticket}, SL deplace a l'entree {entry_price}")
            return True
    else:
        sl_distance_pips = (current_sl - entry_price) / (10 * sym_info.point) if current_sl else 0
        profit_distance_pips = (entry_price - tick.ask) / (10 * sym_info.point)
        # v3.0: Breakeven a 1.2R
        if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl > entry_price:
            _modify_sl(ticket, entry_price)
            logger.info(f"BREAKEVEN: ticket {ticket}, SL deplace a l'entree {entry_price}")
            return True
    return False


def _apply_trailing_stop(pos: dict) -> bool:
    """Trailing stop: deplace le SL quand le profit >= 2x le SL initial."""
    entry_price = pos.get("price_open", 0)
    current_sl = pos.get("sl", 0)
    ticket = pos.get("ticket", 0)
    tick = mt5.symbol_info_tick(settings.trading_symbol)
    sym_info = mt5.symbol_info(settings.trading_symbol)

    if tick is None or sym_info is None or entry_price == 0:
        return False

    trail_distance_pips = 15  # distance de trailing en pips
    trail_distance = trail_distance_pips * 10 * sym_info.point
    sl_distance_pips = abs(entry_price - current_sl) / (10 * sym_info.point) if current_sl else 0

    if pos.get("type") == mt5.POSITION_TYPE_BUY:
        profit_distance_pips = (tick.bid - entry_price) / (10 * sym_info.point)
        if profit_distance_pips >= sl_distance_pips * 2:
            new_sl = tick.bid - trail_distance
            new_sl = round(new_sl, sym_info.digits)
            if new_sl > current_sl + sym_info.point:
                _modify_sl(ticket, new_sl)
                logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")
                return True
    else:
        profit_distance_pips = (entry_price - tick.ask) / (10 * sym_info.point)
        if profit_distance_pips >= sl_distance_pips * 2:
            new_sl = tick.ask + trail_distance
            new_sl = round(new_sl, sym_info.digits)
            if new_sl < current_sl - sym_info.point:
                _modify_sl(ticket, new_sl)
                logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")
                return True
    return False


def _check_time_exit(pos: dict) -> bool:
    """Ferme la position si la structure de marche s'inverse contre le trade.
    v3.0: Logique basee sur la structure (SMA20 + HH/HL) au lieu d'un chronometre arbitraire.
    - BUY: ferme si le prix cloture sous SMA20 OU casse la structure de higher lows
    - SELL: ferme si le prix cloture au-dessus SMA20 OU casse la structure de lower highs
    - Securite: stagnation totale >4h (quelle que soit la direction)"""
    try:
        from datetime import datetime as dt
        ticket = pos.get("ticket", 0)
        entry_price = pos.get("price_open", 0)
        pnl = pos.get("profit", 0)

        # Recuperer les indicateurs recents pour juger la structure
        tick = mt5.symbol_info_tick(settings.trading_symbol)
        sym_info = mt5.symbol_info(settings.trading_symbol)
        if tick is None or sym_info is None:
            return False

        # SMA20: recuperer les 20 dernieres bougies M15
        rates = mt5.copy_rates_from_pos(settings.trading_symbol, mt5.TIMEFRAME_M15, 0, 20)
        if rates is None or len(rates) < 20:
            # Fallback: utiliser le chronometre 4h comme securite
            db = get_db()
            row = db.execute("SELECT opened_at FROM trades WHERE ticket = ?", [ticket]).fetchone()
            if row is None:
                return False
            opened = dt.fromisoformat(row[0])
            age_minutes = (dt.now() - opened).total_seconds() / 60
            if age_minutes > 240 and abs(pnl) < 0.5:
                logger.info(f"TIME EXIT (fallback): ticket {ticket}, stagnation {age_minutes:.0f}min")
                return True
            return False

        close_prices = [r[4] for r in rates]  # close
        sma20 = sum(close_prices) / len(close_prices)
        current_price = tick.bid if pos.get("type") == mt5.POSITION_TYPE_BUY else tick.ask

        if pos.get("type") == mt5.POSITION_TYPE_BUY:
            # Structure haussiere: le prix doit rester au-dessus SMA20
            if current_price < sma20:
                logger.info(f"TIME EXIT: ticket {ticket}, BUY casse SMA20 ({current_price:.5f} < {sma20:.5f})")
                return True
            # Verifier si la structure HH/HL est cassee (dernier low > low precedent?)
            highs = [r[2] for r in rates]
            lows = [r[3] for r in rates]
            # Structure HL cassee si le dernier swing low est plus bas que le precedent
            recent_low = min(lows[-5:])
            prior_low = min(lows[-10:-5])
            if recent_low < prior_low:
                logger.info(f"TIME EXIT: ticket {ticket}, BUY structure HL cassee (recent low {recent_low:.5f} < prior {prior_low:.5f})")
                return True
        else:
            # Structure baissiere: le prix doit rester sous SMA20
            if current_price > sma20:
                logger.info(f"TIME EXIT: ticket {ticket}, SELL casse SMA20 ({current_price:.5f} > {sma20:.5f})")
                return True
            # Verifier si la structure LH est cassee
            highs_arr = [r[2] for r in rates]
            lows_arr = [r[3] for r in rates]
            recent_high = max(highs_arr[-5:])
            prior_high = max(highs_arr[-10:-5])
            if recent_high > prior_high:
                logger.info(f"TIME EXIT: ticket {ticket}, SELL structure LH cassee (recent high {recent_high:.5f} > prior {prior_high:.5f})")
                return True

        # Securite: stagnation totale >4h
        db = get_db()
        row = db.execute("SELECT opened_at FROM trades WHERE ticket = ?", [ticket]).fetchone()
        if row is not None:
            opened = dt.fromisoformat(row[0])
            age_minutes = (dt.now() - opened).total_seconds() / 60
            if age_minutes > 240 and abs(pnl) < 0.5:
                logger.info(f"TIME EXIT: ticket {ticket}, stagnation totale {age_minutes:.0f}min")
                return True

    except Exception as e:
        logger.warning(f"TIME EXIT erreur: {e}")
    return False


def _modify_sl(ticket: int, new_sl: float) -> None:
    """Modifie le SL d'une position ouverte.
    v3.0: Verifie trade_stops_level du broker avant modification."""
    sym = settings.trading_symbol
    sym_info = mt5.symbol_info(sym)

    # Verifier la distance minimale SL autorisee par le broker
    if sym_info is not None:
        tick = mt5.symbol_info_tick(sym)
        if tick is not None:
            stops_level = sym_info.trade_stops_level * sym_info.point
            # Pour un SL, la distance minimale depuis le prix actuel
            pos = mt5.positions_get(ticket=ticket)
            if pos and len(pos) > 0:
                if pos[0].type == mt5.POSITION_TYPE_BUY:
                    distance_from_bid = tick.bid - new_sl
                    if distance_from_bid < stops_level and new_sl < tick.bid:
                        logger.warning(
                            f"SL rejete: distance {distance_from_bid:.5f} < stops_level {stops_level:.5f} "
                            f"(broker min). Ticket {ticket}, SL demande={new_sl}, bid={tick.bid}"
                        )
                        return
                else:
                    distance_from_ask = new_sl - tick.ask
                    if distance_from_ask < stops_level and new_sl > tick.ask:
                        logger.warning(
                            f"SL rejete: distance {distance_from_ask:.5f} < stops_level {stops_level:.5f} "
                            f"(broker min). Ticket {ticket}, SL demande={new_sl}, ask={tick.ask}"
                        )
                        return

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": sym,
        "position": ticket,
        "sl": new_sl,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(f"Echec modification SL ticket {ticket}: {result.comment if result else 'None'}")
