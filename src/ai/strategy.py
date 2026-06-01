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
from src.data.database import get_db


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
        if not _passes_trade_filters(decision, symbol_info):
            return result

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
    """Applique les filtres pre-trade: confiance, max positions, spread, circuit breaker."""
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
