#!/usr/bin/env python3
"""
Stratégie 2 : Retour à la Moyenne (Mean Reversion)
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Ajouter le répertoire parent au path pour importer engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import BacktestEngine

def run_mean_reversion(
    symbol: str,
    timeframe: str,
    initial_balance: float = 1000.0,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
    rsi_oversold: float = 30.0,
    sl_atr_mult: float = 1.5,
    tp_ratio: float = 1.5,
    use_breakeven: bool = True,
    use_trailing: bool = False,
    time_exit_bars: int = 48,
    risk_pct: float = 1.0
) -> tuple[pd.DataFrame, dict]:
    """
    Exécute le backtest de la stratégie de retour à la moyenne.
    """
    engine = BacktestEngine(
        symbol=symbol,
        timeframe=timeframe,
        initial_balance=initial_balance
    )
    
    # 1. Charger les données
    df = engine.load_data()
    
    # 2. Calculer les indicateurs
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
    
    # Bollinger Bands
    bb_sma = close.rolling(window=bb_period).mean()
    bb_std_dev = close.rolling(window=bb_period).std()
    df["bb_upper"] = bb_sma + (bb_std * bb_std_dev)
    df["bb_lower"] = bb_sma - (bb_std * bb_std_dev)
    
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # 3. Détecter les signaux
    prev_close = close.shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)
    prev_bb_upper = df["bb_upper"].shift(1)
    prev_rsi = df["rsi"].shift(1)
    
    rsi_overbought = 100.0 - rsi_oversold
    
    df["buy_signal"] = (prev_close <= prev_bb_lower) & (prev_rsi <= rsi_oversold) & (close > df["bb_lower"])
    df["sell_signal"] = (prev_close >= prev_bb_upper) & (prev_rsi >= rsi_overbought) & (close < df["bb_upper"])
    
    df = df.dropna(subset=["bb_upper", "rsi", "atr"]).reset_index(drop=True)
    
    # 4. Lancer le backtest
    return engine.run(
        df_with_signals=df,
        risk_pct=risk_pct,
        sl_atr_mult=sl_atr_mult,
        tp_ratio=tp_ratio,
        use_breakeven=use_breakeven,
        use_trailing=use_trailing,
        trailing_atr_mult=1.5,
        time_exit_bars=time_exit_bars
    )