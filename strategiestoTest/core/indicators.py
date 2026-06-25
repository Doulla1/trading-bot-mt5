"""
Technical indicators module - pure pandas/numpy implementation.

Computes all indicators needed by the 5 trading strategies:
  - Trend Following: EMA crossovers, ATR
  - Mean Reversion: Bollinger Bands, RSI, ATR
  - Breakout: Donchian channel, ATR
  - MACD Divergence: MACD line/signal/histogram
  - Candle patterns, ADX, Pivot Points, Volume Ratio

Wilder's smoothing is used throughout for RSI, ATR, and ADX:
  smoothed = (prev * (period - 1) + current) / period

This is equivalent to ewm(alpha=1/period, adjust=False).mean() in pandas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Wilder's smoothing helper
# ---------------------------------------------------------------------------

def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Apply Wilder's smoothing to a series.

    First value is the mean of the first *period* values.
    Subsequent values: smoothed[i] = (smoothed[i-1] * (period-1) + series[i]) / period

    Args:
        series: Raw values to smooth.
        period: Lookback period.

    Returns:
        Smoothed series of same length (early values NaN).
    """
    result = series.copy()
    # Initial seed: SMA of the first *period* values
    if len(result) >= period:
        result.iloc[period - 1] = result.iloc[:period].mean()
        # Rolling Wilder's smoothing
        for i in range(period, len(result)):
            result.iloc[i] = (result.iloc[i - 1] * (period - 1) + result.iloc[i]) / period
    result.iloc[:period - 1] = np.nan
    return result

# ---------------------------------------------------------------------------
# EMA / SMA
# ---------------------------------------------------------------------------

def compute_ema(
    df: pd.DataFrame,
    period: int,
    column: str = 'close',
    name: str | None = None,
) -> pd.DataFrame:
    col_name = name if name is not None else f'ema_{period}'
    df[col_name] = df[column].ewm(span=period, adjust=False).mean()
    return df


def compute_sma(
    df: pd.DataFrame,
    period: int,
    column: str = 'close',
    name: str | None = None,
) -> pd.DataFrame:
    col_name = name if name is not None else f'sma_{period}'
    df[col_name] = df[column].rolling(window=period).mean()
    return df


# ---------------------------------------------------------------------------
# RSI (Wilder's smoothing)
# ---------------------------------------------------------------------------

def compute_rsi(
    df: pd.DataFrame,
    period: int = 14,
    column: str = 'close',
    name: str | None = None,
) -> pd.DataFrame:
    col_name = name if name is not None else f'rsi_{period}'
    delta = df[column].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df[col_name] = 100.0 - (100.0 / (1.0 + rs))
    df.loc[(avg_loss == 0) & (avg_gain > 0), col_name] = 100.0
    df.loc[(avg_gain == 0) & (avg_loss > 0), col_name] = 0.0
    return df


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def compute_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = 'close',
) -> pd.DataFrame:
    ema_fast = df[column].ewm(span=fast, adjust=False).mean()
    ema_slow = df[column].ewm(span=slow, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=signal, adjust=False).mean()
    df['macd_histogram'] = df['macd_line'] - df['macd_signal']
    return df


# ---------------------------------------------------------------------------
# ATR (Average True Range, Wilder's smoothing)
# ---------------------------------------------------------------------------

def compute_atr(
    df: pd.DataFrame,
    period: int = 14,
    name: str = 'atr',
) -> pd.DataFrame:
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df[name] = _wilder_smooth(true_range, period)
    return df


# ---------------------------------------------------------------------------
# ADX / DMI (Wilder's smoothing)
# ---------------------------------------------------------------------------

def compute_adx(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.DataFrame:
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    # True Range
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where(
        (up_move > down_move) & (up_move > 0),
        up_move,
        0.0,
    )
    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0),
        down_move,
        0.0,
    )

    plus_dm_series = pd.Series(plus_dm, index=df.index, dtype=float)
    minus_dm_series = pd.Series(minus_dm, index=df.index, dtype=float)

    atr_smoothed = _wilder_smooth(true_range, period)
    plus_dm_smoothed = _wilder_smooth(plus_dm_series, period)
    minus_dm_smoothed = _wilder_smooth(minus_dm_series, period)

    df['plus_di'] = 100.0 * plus_dm_smoothed / atr_smoothed.replace(0, np.nan)
    df['minus_di'] = 100.0 * minus_dm_smoothed / atr_smoothed.replace(0, np.nan)

    di_sum = df['plus_di'] + df['minus_di']
    di_diff = (df['plus_di'] - df['minus_di']).abs()
    dx = 100.0 * di_diff / di_sum.replace(0, np.nan)

    df['adx'] = _wilder_smooth(dx, period)
    return df


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def compute_bollinger(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    column: str = 'close',
) -> pd.DataFrame:
    price = df[column].astype(float)
    df['bb_middle'] = price.rolling(window=period).mean()
    rolling_std = price.rolling(window=period).std()
    df['bb_upper'] = df['bb_middle'] + std_dev * rolling_std
    df['bb_lower'] = df['bb_middle'] - std_dev * rolling_std
    df['bb_width'] = df['bb_upper'] - df['bb_lower']
    bb_range = df['bb_upper'] - df['bb_lower']
    df['bb_position'] = (price - df['bb_lower']) / bb_range.replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Pivot Points
# ---------------------------------------------------------------------------

def compute_pivots(
    df_daily: pd.DataFrame,
    method: str = 'classic',
) -> pd.DataFrame:
    h = df_daily['high'].astype(float)
    l = df_daily['low'].astype(float)
    c = df_daily['close'].astype(float)

    if method == 'camarilla':
        rng = h - l
        df_daily['pp'] = (h + l + c) / 3.0
        df_daily['r1'] = c + rng * (1.1 / 12.0)
        df_daily['s1'] = c - rng * (1.1 / 12.0)
        df_daily['r2'] = c + rng * (1.1 / 6.0)
        df_daily['s2'] = c - rng * (1.1 / 6.0)
        df_daily['r3'] = c + rng * (1.1 / 4.0)
        df_daily['s3'] = c - rng * (1.1 / 4.0)
    else:
        pp = (h + l + c) / 3.0
        df_daily['pp'] = pp
        df_daily['r1'] = 2.0 * pp - l
        df_daily['s1'] = 2.0 * pp - h
        df_daily['r2'] = pp + (h - l)
        df_daily['s2'] = pp - (h - l)
        df_daily['r3'] = h + 2.0 * (pp - l)
        df_daily['s3'] = l - 2.0 * (h - pp)

    return df_daily


# ---------------------------------------------------------------------------
# Candle Patterns
# ---------------------------------------------------------------------------

def compute_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    open_ = df['open'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    total_range = high - low

    body = (close - open_).abs()
    upper_shadow = high - np.maximum(open_, close)
    lower_shadow = np.minimum(open_, close) - low

    has_body = body > 0

    # Hammer: bullish candle with long lower shadow
    df['is_hammer'] = (
        has_body
        & (close > open_)
        & (lower_shadow >= 2.0 * body)
        & (upper_shadow <= 0.3 * body)
    )

    # Shooting Star: bearish candle with long upper shadow
    df['is_shooting_star'] = (
        has_body
        & (close < open_)
        & (upper_shadow >= 2.0 * body)
        & (lower_shadow <= 0.3 * body)
    )

    # Doji: tiny body relative to the entire range
    df['is_doji'] = body <= 0.1 * total_range

    # Pinbar Bull: long lower shadow, body near the top of the range
    body_in_top_third = (close > open_) & (
        np.minimum(open_, close) >= low + (2.0 / 3.0) * total_range
    )
    df['is_pinbar_bull'] = (
        has_body
        & (lower_shadow >= 3.0 * body)
        & body_in_top_third
    )

    # Pinbar Bear: long upper shadow, body near the bottom of the range
    body_in_bottom_third = (close < open_) & (
        np.maximum(open_, close) <= high - (2.0 / 3.0) * total_range
    )
    df['is_pinbar_bear'] = (
        has_body
        & (upper_shadow >= 3.0 * body)
        & body_in_bottom_third
    )

    # Engulfing patterns (need previous bar)
    prev_open = open_.shift(1)
    prev_close = close.shift(1)

    df['is_bullish_engulfing'] = (
        (close > open_)
        & (prev_close < prev_open)
        & (open_ <= prev_close)
        & (close >= prev_open)
    )

    df['is_bearish_engulfing'] = (
        (close < open_)
        & (prev_close > prev_open)
        & (open_ >= prev_close)
        & (close <= prev_open)
    )

    return df


# ---------------------------------------------------------------------------
# Volume Ratio
# ---------------------------------------------------------------------------

def compute_volume_ratio(
    df: pd.DataFrame,
    period: int = 20,
) -> pd.DataFrame:
    if "tick_volume" not in df.columns:
        raise KeyError("DataFrame must contain a tick_volume column")
    avg_vol = df["tick_volume"].rolling(window=period).mean()
    df["vol_ratio"] = df["tick_volume"] / avg_vol.replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Merge pivots onto intraday data
# ---------------------------------------------------------------------------

def align_pivots_to_intraday(
    df_intraday: pd.DataFrame,
    df_daily_pivots: pd.DataFrame,
) -> pd.DataFrame:
    pivot_cols = ["pp", "r1", "r2", "r3", "s1", "s2", "s3"]

    if not pd.api.types.is_datetime64_any_dtype(df_intraday["datetime"]):
        df_intraday["datetime"] = pd.to_datetime(df_intraday["datetime"])
    if not pd.api.types.is_datetime64_any_dtype(df_daily_pivots["datetime"]):
        df_daily_pivots["datetime"] = pd.to_datetime(df_daily_pivots["datetime"])

    daily_cols = ["datetime"] + [c for c in pivot_cols if c in df_daily_pivots.columns]
    df_daily_subset = df_daily_pivots[daily_cols].copy()
    df_daily_subset = df_daily_subset.sort_values("datetime").reset_index(drop=True)

    df_intraday_sorted = df_intraday.sort_values("datetime").reset_index(drop=True)

    merged = pd.merge_asof(
        df_intraday_sorted,
        df_daily_subset,
        on="datetime",
        direction="backward",
    )

    available_cols = [c for c in pivot_cols if c in merged.columns]
    if available_cols:
        merged[available_cols] = merged[available_cols].ffill()

    for col in available_cols:
        df_intraday[col] = np.nan
        df_intraday.loc[df_intraday_sorted.index, col] = merged[col].values

    return df_intraday


# ---------------------------------------------------------------------------
# Compute all indicators at once
# ---------------------------------------------------------------------------

_DEFAULT_EMA_PERIODS = [20, 50, 200]

_DEFAULT_CONFIG: dict = {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "atr_period": 14,
    "adx_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    "ema_periods": _DEFAULT_EMA_PERIODS,
    "sma_periods": [],
    "compute_pivots": False,
    "compute_candles": True,
    "compute_volume": True,
}


def compute_all(
    df: pd.DataFrame,
    config: dict | None = None,
) -> pd.DataFrame:
    cfg = {**_DEFAULT_CONFIG, **(config or {})}

    # EMA
    for period in cfg.get("ema_periods", []):
        compute_ema(df, period)

    # SMA
    for period in cfg.get("sma_periods", []):
        compute_sma(df, period)

    # RSI
    compute_rsi(df, period=cfg["rsi_period"])

    # MACD
    compute_macd(
        df,
        fast=cfg["macd_fast"],
        slow=cfg["macd_slow"],
        signal=cfg["macd_signal"],
    )

    # ATR
    compute_atr(df, period=cfg["atr_period"])

    # ADX
    compute_adx(df, period=cfg["adx_period"])

    # Bollinger Bands
    compute_bollinger(
        df,
        period=cfg["bb_period"],
        std_dev=cfg["bb_std"],
    )

    # Pivot points (only if requested - daily data required)
    if cfg.get("compute_pivots"):
        compute_pivots(df, method="classic")

    # Candle patterns
    if cfg.get("compute_candles"):
        compute_candle_patterns(df)

    # Volume ratio
    if cfg.get("compute_volume") and "tick_volume" in df.columns:
        compute_volume_ratio(df)

    return df