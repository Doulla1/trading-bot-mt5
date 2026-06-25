#!/usr/bin/env python3
"""
Robot de Trading Live/Démo : Divergence MACD sur Or (XAUUSD H1).
Se connecte au compte actif, écrit les logs techniques et de trades en DB pour affichage Streamlit.
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
from pathlib import Path
from loguru import logger
from rich.console import Console

# Ajouter la racine du projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings
from src.utils.logger import setup_logger
from src.data.database import log_analysis, log_trade_open, log_trade_close, get_db

# Surcharger les configurations symboles et magiques uniquement (compte chargé depuis .env)
settings.mt5_magic_number = 73999  # Magic Number unique pour l'Or MACD
settings.trading_symbol = "XAUUSD"
settings.trading_timeframe = "H1"

# Configuration experte de la stratégie gagnante
STRAT_PARAMS = {
    "swing_window": 8,
    "sl_atr_mult": 1.5,
    "tp_ratio": 2.5,
    "trailing_atr_mult": 1.0,
    "use_trend_filter": True,
    "time_exit_bars": 48
}

console = Console()

# ------------------------------------------------------------------
# Fonctions Techniques / Indicateurs
# ------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule le MACD, l'ATR et l'EMA 200 nécessaires à la stratégie."""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    
    # ATR
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()
    
    # MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df["macd_line"] = ema_12 - ema_26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    
    # EMA 200
    df["ema_slow"] = close.ewm(span=200, adjust=False).mean()
    
    return df

def detect_divergences(df: pd.DataFrame, swing_window: int = 8) -> tuple[pd.Series, pd.Series]:
    """Détecte les divergences haussières et baissières entre le prix et l'histogramme MACD."""
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    macd = df["macd_hist"].astype(float).values
    n = len(df)
    
    bull_div = pd.Series(False, index=df.index)
    bear_div = pd.Series(False, index=df.index)
    
    swing_lows = []
    swing_highs = []
    
    for i in range(swing_window, n - swing_window):
        # Swing Low
        is_low = True
        for w in range(-swing_window, swing_window + 1):
            if low[i + w] < low[i]:
                is_low = False
                break
        if is_low:
            swing_lows.append((i, low[i], macd[i]))
            if len(swing_lows) >= 2:
                prev_i, prev_low, prev_macd = swing_lows[-2]
                if low[i] < prev_low and macd[i] > prev_macd:
                    bull_div.iloc[i] = True
                    
        # Swing High
        is_high = True
        for w in range(-swing_window, swing_window + 1):
            if high[i + w] > high[i]:
                is_high = False
                break
        if is_high:
            swing_highs.append((i, high[i], macd[i]))
            if len(swing_highs) >= 2:
                prev_i, prev_high, prev_macd = swing_highs[-2]
                if high[i] > prev_high and macd[i] < prev_macd:
                    bear_div.iloc[i] = True
                    
    # Propager les divergences
    bull_div_extended = bull_div.rolling(window=swing_window * 3, min_periods=1).max().fillna(0).astype(bool)
    bear_div_extended = bear_div.rolling(window=swing_window * 3, min_periods=1).max().fillna(0).astype(bool)
    
    return bull_div_extended, bear_div_extended

# ------------------------------------------------------------------
# Gestion de la connexion MT5
# ------------------------------------------------------------------

def connect_mt5() -> bool:
    """Connecte le script au compte configuré dans le fichier .env."""
    if not mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server
    ):
        logger.error(f"Échec initialisation MT5 : {mt5.last_error()}")
        return False
        
    account = mt5.account_info()
    if account is None:
        logger.error("Impossible de récupérer les infos du compte démo.")
        mt5.shutdown()
        return False
        
    logger.info(f"Connecté avec succès au Compte Démo {account.login} | Solde: {account.balance} {account.currency}")
    return True

# ------------------------------------------------------------------
# Gestion de l'exécution en temps réel
# ------------------------------------------------------------------

def get_live_rates(count=150) -> pd.DataFrame:
    """Récupère les bougies historiques H1 récentes de l'Or."""
    rates = mt5.copy_rates_from_pos(settings.trading_symbol, mt5.TIMEFRAME_H1, 0, count)
    if rates is None or len(rates) == 0:
        logger.error("Erreur de récupération des données temps réel de l'Or.")
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["datetime"] = pd.to_datetime(df["time"], unit="s")
    return df

def get_our_position():
    """Vérifie si notre stratégie a une position actuellement ouverte sur le compte."""
    positions = mt5.positions_get(symbol=settings.trading_symbol)
    if positions is None or len(positions) == 0:
        return None
    # Filtrer manuellement par notre magic number unique
    our_pos = [p for p in positions if p.magic == settings.mt5_magic_number]
    return our_pos[0] if our_pos else None

def execute_order(direction: str, lot_size: float, sl: float, tp: float):
    """Envoie l'ordre d'achat ou de vente au terminal MT5."""
    tick = mt5.symbol_info_tick(settings.trading_symbol)
    if tick is None:
        logger.error("Pas de tick disponible pour envoyer l'ordre.")
        return None
        
    price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": settings.trading_symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "deviation": 10,
        "magic": settings.mt5_magic_number,
        "comment": "Or MACD Divergence",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Échec de l'ordre : {result.comment if result else 'Erreur inconnue'}")
        return None
        
    logger.info(f"ORDRE EXÉCUTÉ: {direction} {settings.trading_symbol} | Lots: {lot_size} | Entrée: {price} | SL: {sl} | TP: {tp} | Ticket: {result.order}")
    return result.order

def update_position_sl(ticket: int, new_sl: float):
    """Modifie le niveau de stop loss d'une position active."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False
    pos = pos[0]
    
    if abs(pos.sl - new_sl) < 0.05:
        return False
        
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": round(new_sl, 2),
        "tp": pos.tp
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Échec de modification SL/TP sur ticket {ticket}: {result.comment if result else 'Erreur'}")
        return False
    logger.info(f"SL MODIFIÉ : Ticket {ticket} -> Nouveau SL: {new_sl}")
    return True

def close_position_live(ticket: int):
    """Ferme complètement une position par son ticket."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False
    pos = pos[0]
    
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        return False
        
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 10,
        "magic": settings.mt5_magic_number,
        "comment": "Or MACD - Sortie Manuelle"
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Échec fermeture ticket {ticket}")
        return False
    logger.info(f"POSITION FERMÉE : Ticket {ticket} à {price}")
    return True

# ------------------------------------------------------------------
# Réconciliation & Logs DB
# ------------------------------------------------------------------

def reconcile_closed_trade(ticket: int):
    """Récupère le deal de clôture pour le ticket donné et met à jour la base de données SQLite."""
    try:
        now = datetime.now()
        mt5.history_deals_get(now - timedelta(days=30), now + timedelta(days=1))
        
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            close_deal = [d for d in deals if d.entry == 1]  # 1 = OUT
            if close_deal:
                d = close_deal[0]
                total_profit = d.profit + d.commission + d.swap
                log_trade_close(ticket, d.price, total_profit, symbol=settings.trading_symbol)
                logger.info(f"Position {ticket} enregistrée fermée en DB | Profit: {total_profit:.2f} €")
                return True
        # Fallback si deal introuvable
        log_trade_close(ticket, 0.0, 0.0, symbol=settings.trading_symbol)
        return False
    except Exception as e:
        logger.error(f"Erreur réconciliation ticket {ticket} : {e}")
        return False

def check_db_reconciliation():
    """Parcourt les trades ouverts en base et réconcilie ceux fermés par SL/TP externe."""
    try:
        db = get_db(symbol=settings.trading_symbol)
        open_db_trades = db.execute(
            "SELECT ticket FROM trades WHERE closed_at IS NULL AND symbol = ?", [settings.trading_symbol]
        ).fetchall()
        
        for row in open_db_trades:
            ticket = row[0]
            # Vérifier si la position est toujours ouverte sur MT5
            pos = mt5.positions_get(ticket=ticket)
            if pos is None or len(pos) == 0:
                logger.info(f"Détection de fermeture externe pour le ticket {ticket}. Lancement réconciliation...")
                reconcile_closed_trade(ticket)
    except Exception as e:
        logger.error(f"Erreur vérification réconciliation DB : {e}")

# ------------------------------------------------------------------
# Cerveau de la stratégie
# ------------------------------------------------------------------

def check_and_trade():
    logger.info("Vérification des signaux de trading sur l'Or...")
    
    # Réconcilier la base avec les fermetures SL/TP du broker
    check_db_reconciliation()
    
    # 1. Charger et calculer les indicateurs
    df = get_live_rates(150)
    if df.empty:
        return
        
    df = compute_indicators(df)
    
    last_closed_bar = df.iloc[-2]
    close_price = float(last_closed_bar["close"])
    atr = float(last_closed_bar["atr"])
    ema_slow = float(last_closed_bar["ema_slow"])
    macd_line = float(last_closed_bar["macd_line"])
    macd_signal = float(last_closed_bar["macd_signal"])
    
    # Détecter les divergences
    bull_div, bear_div = detect_divergences(df, swing_window=STRAT_PARAMS["swing_window"])
    is_bull_div = bull_div.iloc[-2]
    is_bear_div = bear_div.iloc[-2]
    
    # Détecter le croisement du signal MACD
    prev_macd_line = df.iloc[-3]["macd_line"]
    prev_macd_signal = df.iloc[-3]["macd_signal"]
    macd_cross_up = (macd_line > macd_signal) and (prev_macd_line <= prev_macd_signal)
    macd_cross_down = (macd_line < macd_signal) and (prev_macd_line >= prev_macd_signal)
    
    buy_signal = is_bull_div and macd_cross_up
    sell_signal = is_bear_div and macd_cross_down
    
    if STRAT_PARAMS["use_trend_filter"]:
        buy_signal = buy_signal and (close_price > ema_slow)
        sell_signal = sell_signal and (close_price < ema_slow)
        
    pos = get_our_position()
    
    if pos is None:
        if buy_signal or sell_signal:
            account = mt5.account_info()
            balance = account.balance
            risk_amount = balance * 0.01
            
            sl_dist = STRAT_PARAMS["sl_atr_mult"] * atr
            lot_size = risk_amount / (sl_dist * 100.0)
            lot_size = max(0.01, round(lot_size, 2))
            
            direction = "BUY" if buy_signal else "SELL"
            sl = close_price - sl_dist if buy_signal else close_price + sl_dist
            tp = close_price + STRAT_PARAMS["tp_ratio"] * sl_dist if buy_signal else close_price - STRAT_PARAMS["tp_ratio"] * sl_dist
            
            # Enregistrer l'analyse dans la table de debug Streamlit
            log_analysis(
                symbol=settings.trading_symbol,
                timeframe=settings.trading_timeframe,
                decision={
                    "action": direction,
                    "confidence": 100,
                    "reasoning": f"Divergence MACD validée (Swing Window {STRAT_PARAMS['swing_window']})."
                },
                screenshot_path="",
                indicators={
                    "macd_line": macd_line,
                    "macd_signal": macd_signal,
                    "macd_hist": last_closed_bar["macd_hist"],
                    "atr_14": atr,
                    "ema_slow": ema_slow,
                    "is_bull_div": is_bull_div,
                    "is_bear_div": is_bear_div
                },
                calendar_events=[],
                was_executed=True
            )
            
            # Envoyer l'ordre
            order_ticket = execute_order(direction, lot_size, sl, tp)
            
            # Enregistrer l'ouverture du trade en DB
            if order_ticket:
                log_trade_open(
                    ticket=order_ticket,
                    symbol=settings.trading_symbol,
                    direction=direction,
                    volume=lot_size,
                    open_price=close_price,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=100,
                    reasoning="Signal Divergence MACD H1 sur l'Or. Entrée technique robuste."
                )
    else:
        direction = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
        entry_price = pos.price_open
        current_sl = pos.sl
        ticket = pos.ticket
        
        pos_time = pd.to_datetime(pos.time, unit="s")
        current_time = pd.to_datetime(df.iloc[-1]["time"], unit="s")
        bars_held = int((current_time - pos_time).total_seconds() / 3600.0)
        
        if bars_held >= STRAT_PARAMS["time_exit_bars"]:
            logger.info(f"Temps de maintien maximal de 48 barres atteint pour le ticket {ticket}. Sortie.")
            if close_position_live(ticket):
                reconcile_closed_trade(ticket)
            return
            
        sl_dist = STRAT_PARAMS["sl_atr_mult"] * atr
        
        if direction == "BUY":
            if current_sl < entry_price:
                if close_price - entry_price >= sl_dist:
                    update_position_sl(ticket, entry_price)
            new_sl = close_price - STRAT_PARAMS["trailing_atr_mult"] * atr
            if new_sl > current_sl:
                update_position_sl(ticket, new_sl)
        else:  # SELL
            if current_sl > entry_price:
                if entry_price - close_price >= sl_dist:
                    update_position_sl(ticket, entry_price)
            new_sl = close_price + STRAT_PARAMS["trailing_atr_mult"] * atr
            if new_sl < current_sl:
                update_position_sl(ticket, new_sl)

def run_loop():
    logger.info("=== INITIALISATION DU ROBOT LIVE SUR L'OR ===")
    logger.info("Strategy: MACD Divergence H1 (XAUUSD)")
    logger.info(f"Magic Number: {settings.mt5_magic_number}")
    
    last_bar_time = None
    
    while True:
        try:
            if not connect_mt5():
                logger.error("Problème de connexion MT5, nouvelle tentative dans 60s...")
                time.sleep(60)
                continue
                
            try:
                df = get_live_rates(5)
                if not df.empty:
                    current_bar_time = df.iloc[-1]["time"]
                    
                    if last_bar_time is None or current_bar_time > last_bar_time:
                        last_bar_time = current_bar_time
                        check_and_trade()
            finally:
                mt5.shutdown()
                
        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur.")
            break
        except Exception as e:
            logger.exception(f"Erreur inattendue dans la boucle : {e}")
            
        time.sleep(30)

if __name__ == "__main__":
    setup_logger()
    run_loop()
