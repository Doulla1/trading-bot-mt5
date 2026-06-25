"""Execution des ordres de trading via MT5."""

import MetaTrader5 as mt5
from loguru import logger
from dataclasses import dataclass
from typing import Optional

from src.config import settings


@dataclass
class TradeResult:
    """Resultat d'un ordre."""
    success: bool
    ticket: int | None
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    comment: str
    error: str | None = None


def calculate_position_size(account_balance, stop_loss_pips, symbol_info, risk_pct=None) -> float:
    """Calcule la taille de position en lots basee sur le risque."""
    risk = risk_pct or settings.max_risk_per_trade_pct
    risk_amount = account_balance * (risk / 100)
    point_value = symbol_info.get("trade_tick_value", 1.0)
    pip_size = 10 * symbol_info.get("point", 0.00001)
    sl_price_distance = stop_loss_pips * pip_size
    if sl_price_distance <= 0:
        return 0.01
    lots = risk_amount / (sl_price_distance * point_value / pip_size * 10)
    lots = max(0.01, round(lots, 2))
    return lots


def open_position(direction, volume, stop_loss, take_profit, symbol=None, comment="TradingBot IA") -> TradeResult:
    """Ouvre une position (CRITICAL-06 : protection tick None)."""
    sym = symbol or settings.trading_symbol
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        err = f"Tick introuvable pour {sym}"
        logger.error(err)
        return TradeResult(False, None, volume, 0, stop_loss, take_profit, comment, err)

    if direction.upper() == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 20,
        "magic": settings.mt5_magic_number,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error_msg = f"Code retour: {result.retcode if result else 'None'} - {result.comment if result else 'None'}"
        logger.error(f"Echec ouverture position {direction} {sym}: {error_msg}")
        if result and result.retcode == 10027:
            logger.warning("ASTUCE : Activez l'Algo Trading dans MT5 : Outils > Options > Expert Advisors > Allow Algo Trading")
        return TradeResult(False, None, volume, price, stop_loss, take_profit, comment, error_msg)

    logger.info(f"POSITION OUVERTE: {direction} {sym} | Volume: {volume} | Prix: {price} | SL: {stop_loss} | TP: {take_profit} | Ticket: {result.order}")
    return TradeResult(True, result.order, volume, price, stop_loss, take_profit, comment)


def close_position(ticket, symbol=None) -> TradeResult:
    """Ferme une position existante par son ticket."""
    sym = symbol or settings.trading_symbol
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return TradeResult(False, ticket, 0, 0, 0, 0, "", f"Position {ticket} introuvable")

    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        err = f"Tick introuvable pour {sym}"
        logger.error(err)
        return TradeResult(False, ticket, 0, 0, 0, 0, "", err)

    pos = position[0]
    if pos.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": pos.volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": settings.mt5_magic_number,
        "comment": "TradingBot IA - Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error_msg = f"Code retour: {result.retcode if result else 'None'}"
        logger.error(f"Echec fermeture position {ticket}: {error_msg}")
        return TradeResult(False, ticket, pos.volume, price, 0, 0, "", error_msg)

    logger.info(f"POSITION FERMEE: ticket {ticket} | Prix: {price}")
    return TradeResult(True, ticket, pos.volume, price, 0, 0, "Fermeture")


def get_open_positions(symbol=None) -> list:
    """Retourne les positions ouvertes pour le symbole et magic number actif."""
    sym = symbol or settings.trading_symbol
    positions = mt5.positions_get(symbol=sym)
    if positions is None:
        return []
    # Filtrer par magic number pour isoler les strategies paralleles sur le meme symbole
    return [p._asdict() for p in positions if p.magic == settings.mt5_magic_number]


def count_open_positions(symbol=None) -> int:
    """Compte les positions ouvertes pour le symbole."""
    return len(get_open_positions(symbol))
