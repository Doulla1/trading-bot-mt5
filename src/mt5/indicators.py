"""Calcul des indicateurs techniques via les donnees OHLCV."""

import pandas as pd
import numpy as np
from loguru import logger


def compute_all(df: pd.DataFrame) -> dict:
    """Calcule tous les indicateurs a partir d'un DataFrame OHLCV."""
    if df.empty or len(df) < 50:
        logger.warning("Pas assez de donnees pour les indicateurs (min 50 bougies)")
        return {}

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    result = {}

    rsi_val = _rsi(close, 14)
    result["rsi_14"] = round(rsi_val, 1) if not np.isnan(rsi_val) else None

    macd_line, signal_line, macd_hist = _macd(close)
    result["macd_line"] = round(macd_line, 5) if not np.isnan(macd_line) else None
    result["macd_signal"] = round(signal_line, 5) if not np.isnan(signal_line) else None
    result["macd_histogram"] = round(macd_hist, 5) if not np.isnan(macd_hist) else None

    result["sma_20"] = round(close.iloc[-20:].mean(), 5)
    result["sma_50"] = round(close.iloc[-50:].mean(), 5) if len(close) >= 50 else None

    bb_upper, bb_middle, bb_lower = _bollinger_bands(close, 20, 2)
    last_close = close.iloc[-1]
    result["bb_upper"] = round(bb_upper, 5)
    result["bb_middle"] = round(bb_middle, 5)
    result["bb_lower"] = round(bb_lower, 5)
    result["bb_position_pct"] = round(
        ((last_close - bb_lower) / (bb_upper - bb_lower)) * 100, 1
    ) if bb_upper != bb_lower else None

    atr_val = _atr(high, low, close, 14)
    result["atr_14"] = round(atr_val, 5) if not np.isnan(atr_val) else None

    result["current_price"] = round(last_close, 5)
    result["high_24h"] = round(high.iloc[-96:].max(), 5) if len(high) >= 96 else round(high.max(), 5)
    result["low_24h"] = round(low.iloc[-96:].min(), 5) if len(low) >= 96 else round(low.min(), 5)

    if result["sma_50"] is not None:
        result["trend_short"] = "haussier" if last_close > result["sma_20"] else "baissier"
        result["trend_medium"] = "haussier" if last_close > result["sma_50"] else "baissier"
    else:
        result["trend_short"] = "haussier" if last_close > result["sma_20"] else "baissier"
        result["trend_medium"] = "indetermine"

    return result


def _rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _macd(close: pd.Series, fast=12, slow=26, signal=9) -> tuple:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])


def _bollinger_bands(close: pd.Series, period=20, std_dev=2) -> tuple:
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> float:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1])
