#!/usr/bin/env python3
"""
Stratégie 3 : Cassure des Canaux de Donchian (Breakout)
"""

import sys
import pandas as pd
from pathlib import Path

# Ajouter le répertoire parent au path pour importer engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import BacktestEngine

def run_breakout(
    symbol: str,
    timeframe: str,
    initial_balance: float = 1000.0,
    donchian_period: int = 20,
    atr_period: int = 14,
    sl_atr_mult: float = 1.5,
    tp_ratio: float = 3.0,
    use_breakeven: bool = True,
    use_trailing: bool = True,
    trailing_atr_mult: float = 1.5,
    time_exit_bars: int = 96,
    risk_pct: float = 1.0,
    use_trend_filter: bool = False
) -> tuple[pd.DataFrame, dict]:
    """
    Exécute le backtest de la stratégie de cassure de Donchian.
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
    
    # Canal de Donchian (calculé sur les N bougies précédentes, excluant la bougie courante)
    df["donchian_high"] = high.shift(1).rolling(window=donchian_period).max()
    df["donchian_low"] = low.shift(1).rolling(window=donchian_period).min()
    
    # ATR
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/atr_period, adjust=False).mean()
    
    # 3. Détecter les signaux
    df["buy_signal"] = close > df["donchian_high"]
    df["sell_signal"] = close < df["donchian_low"]
    
    if use_trend_filter:
        df["ema_slow"] = close.ewm(span=200, adjust=False).mean()
        df["buy_signal"] = df["buy_signal"] & (close > df["ema_slow"])
        df["sell_signal"] = df["sell_signal"] & (close < df["ema_slow"])
        
    df = df.dropna(subset=["donchian_high", "atr"]).reset_index(drop=True)
    
    # 4. Lancer le backtest
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