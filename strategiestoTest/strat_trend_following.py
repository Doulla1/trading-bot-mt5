#!/usr/bin/env python3
"""
Stratégie 1 : Suivi de Tendance avec Moyennes Mobiles et Pullback (Trend Following)
"""

import sys
import pandas as pd
from pathlib import Path

# Ajouter le répertoire parent au path pour importer engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import BacktestEngine

def run_trend_following(
    symbol: str,
    timeframe: str,
    initial_balance: float = 1000.0,
    ema_fast: int = 10,
    ema_medium: int = 30,
    ema_slow: int = 200,
    atr_period: int = 14,
    sl_atr_mult: float = 1.0,
    tp_ratio: float = 3.0,
    use_breakeven: bool = True,
    use_trailing: bool = True,
    time_exit_bars: int = 48,
    risk_pct: float = 1.0
) -> tuple[pd.DataFrame, dict]:
    """
    Exécute le backtest de la stratégie de suivi de tendance.
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
    df["atr"] = tr.ewm(alpha=1/atr_period, adjust=False).mean()
    
    # EMAs
    df["ema_fast"] = close.ewm(span=ema_fast, adjust=False).mean()
    df["ema_medium"] = close.ewm(span=ema_medium, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=ema_slow, adjust=False).mean()
    
    # 3. Détecter les signaux
    trend_up = (close > df["ema_slow"]) & (df["ema_fast"] > df["ema_medium"])
    pullback_buy = (low <= df["ema_fast"]) & (close > df["ema_fast"])
    df["buy_signal"] = trend_up & pullback_buy
    
    trend_down = (close < df["ema_slow"]) & (df["ema_fast"] < df["ema_medium"])
    pullback_sell = (high >= df["ema_fast"]) & (close < df["ema_fast"])
    df["sell_signal"] = trend_down & pullback_sell
    
    df = df.dropna(subset=["ema_slow", "atr"]).reset_index(drop=True)
    
    # 4. Lancer le backtest
    return engine.run(
        df_with_signals=df,
        risk_pct=risk_pct,
        sl_atr_mult=sl_atr_mult,
        tp_ratio=tp_ratio,
        use_breakeven=use_breakeven,
        use_trailing=use_trailing,
        trailing_atr_mult=sl_atr_mult,
        time_exit_bars=time_exit_bars
    )