#!/usr/bin/env python3
"""
Stratégie 4 : Divergence MACD (Contre-tendance / Reversal)
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Ajouter le répertoire parent au path pour importer engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import BacktestEngine

def detect_divergences(df: pd.DataFrame, swing_window: int = 5, macd_col: str = "macd_hist") -> tuple[pd.Series, pd.Series]:
    """
    Détecte les divergences haussières et baissières entre le prix et l'indicateur MACD.
    Retourne deux Series booléennes étendues pour s'aligner avec les croisements futurs.
    """
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    macd = df[macd_col].astype(float).values
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
                    
    # Étendre la validité des divergences pour permettre au MACD de croiser son signal
    bull_div_extended = bull_div.rolling(window=swing_window * 3, min_periods=1).max().fillna(0).astype(bool)
    bear_div_extended = bear_div.rolling(window=swing_window * 3, min_periods=1).max().fillna(0).astype(bool)
    
    return bull_div_extended, bear_div_extended

def run_macd_divergence(
    symbol: str,
    timeframe: str,
    initial_balance: float = 1000.0,
    swing_window: int = 5,
    sl_atr_mult: float = 1.5,
    tp_ratio: float = 2.0,
    use_breakeven: bool = True,
    use_trailing: bool = True,
    trailing_atr_mult: float = 1.0,
    time_exit_bars: int = 48,
    risk_pct: float = 1.0,
    use_trend_filter: bool = False
) -> tuple[pd.DataFrame, dict]:
    """
    Exécute le backtest de la stratégie de divergence MACD.
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
    
    # MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df["macd_line"] = ema_12 - ema_26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    
    # 3. Divergences
    bull_div, bear_div = detect_divergences(df, swing_window=swing_window, macd_col="macd_hist")
    df["bull_div"] = bull_div
    df["bear_div"] = bear_div
    
    # 4. Signaux
    macd_cross_up = (df["macd_line"] > df["macd_signal"]) & (df["macd_line"].shift(1) <= df["macd_signal"].shift(1))
    df["buy_signal"] = df["bull_div"] & macd_cross_up
    
    macd_cross_down = (df["macd_line"] < df["macd_signal"]) & (df["macd_line"].shift(1) >= df["macd_signal"].shift(1))
    df["sell_signal"] = df["bear_div"] & macd_cross_down
    
    if use_trend_filter:
        df["ema_slow"] = close.ewm(span=200, adjust=False).mean()
        df["buy_signal"] = df["buy_signal"] & (close > df["ema_slow"])
        df["sell_signal"] = df["sell_signal"] & (close < df["ema_slow"])
        
    df = df.dropna(subset=["macd_signal", "atr"]).reset_index(drop=True)
    
    # 5. Lancer le backtest
    return engine.run(
        df_with_signals=df,
        risk_pct=risk_pct,
        sl_atr_mult=sl_atr_mult,
        tp_ratio=tp_ratio,
        use_breakeven=use_breakeven,
        use_trailing=use_trailing,
        trailing_atr_mult=trailing_atr_mult,
        time_exit_bars=time_exit_bars
    )