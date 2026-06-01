"""Bridge MT5 : connexion, deconnexion, recuperation de donnees."""

import MetaTrader5 as mt5
from loguru import logger
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from src.config import settings

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


def connect() -> bool:
    """Etablit la connexion au terminal MT5."""
    if not mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    ):
        error = mt5.last_error()
        logger.error(f"Echec connexion MT5 : {error}")
        return False
    logger.info(f"MT5 connecte - Compte {settings.mt5_login} sur {settings.mt5_server}")
    return True


def disconnect() -> None:
    """Ferme la connexion MT5."""
    mt5.shutdown()
    logger.info("MT5 deconnecte")


def get_account_info() -> Optional[dict]:
    """Retourne les informations du compte."""
    info = mt5.account_info()
    if info is None:
        logger.error("Impossible de recuperer les infos du compte")
        return None
    return info._asdict()


def get_rates(symbol=None, timeframe=None, count=100) -> pd.DataFrame:
    """Recupere les OHLCV pour un symbole et timeframe."""
    sym = symbol or settings.trading_symbol
    tf_str = timeframe or settings.trading_timeframe
    tf = TIMEFRAME_MAP.get(tf_str, mt5.TIMEFRAME_M15)
    rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
    if rates is None:
        logger.error(f"Echec recuperation rates pour {sym} {tf_str}")
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def get_current_price(symbol=None) -> Optional[float]:
    """Retourne le prix bid actuel."""
    sym = symbol or settings.trading_symbol
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        logger.error(f"Echec recuperation prix pour {sym}")
        return None
    return tick.bid


def get_symbol_info(symbol=None) -> Optional[dict]:
    """Retourne les proprietes du symbole (digits, point, spread...)."""
    sym = symbol or settings.trading_symbol
    info = mt5.symbol_info(sym)
    if info is None:
        logger.error(f"Echec recuperation info symbole {sym}")
        return None
    return info._asdict()


def is_market_open() -> bool:
    """Verifie si le marche est ouvert pour le symbole (CRITICAL-04 : trade_mode)."""
    sym = settings.trading_symbol
    selected = mt5.symbol_select(sym, True)
    if not selected:
        logger.warning(f"Symbole {sym} non disponible dans MarketWatch")
        return False
    info = mt5.symbol_info(sym)
    if info is None:
        return False
    # SYMBOL_TRADE_MODE_FULL = 4 = trading complet autorise
    return info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL
