"""
Strategy: RSI Overbought/Oversold with EMA 200 trend filter (Mean Reversion).

Trades RSI extremes (oversold/overbought) in the direction of the dominant
trend defined by EMA 200.

- Uptrend (close > EMA_200): ONLY buy when RSI is oversold (buy the dip).
- Downtrend (close < EMA_200): ONLY sell when RSI is overbought (sell the rip).

Optional filters: RSI divergence, Bollinger Band touch, reversal candle
confirmation, volume spike, and ADX cap (mean reversion works best in
non-trending / weak-trending environments).

Uses ``BacktestEngine.run(signal_fn, params)`` API.
"""

from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from strategiestoTest.core.indicators import (
    compute_adx,
    compute_atr,
    compute_bollinger,
    compute_candle_patterns,
    compute_ema,
    compute_rsi,
    compute_volume_ratio,
)


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    # RSI
    "rsi_period": 14,
    "rsi_oversold": 30,          # RSI below this = oversold (buy zone)
    "rsi_overbought": 70,        # RSI above this = overbought (sell zone)
    "rsi_exit": 50,              # exit when RSI crosses this (return to neutral)

    # Trend filter
    "ema_trend_period": 200,
    "trend_required": True,      # must trade WITH the trend direction

    # Divergence (optional, adds reliability)
    "require_divergence": False,  # require RSI divergence for entry
    "divergence_lookback": 20,    # bars to look back for divergence

    # Bollinger confirmation (optional)
    "require_bb_touch": False,    # require price touching BB extreme
    "bb_period": 20,
    "bb_std": 2.0,

    # Candle confirmation
    "require_reversal_candle": True,  # require a reversal candle pattern

    # Trade management
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 3.0,          # target 3:1 RR by default

    # Filters
    "adx_max": 25,               # only trade when ADX <= this (ranging/weak trend)
    # mean reversion works best in non-trending markets

    # Volume confirmation
    "require_volume_spike": False,  # require volume > 1.5x average

    # Engine
    "warmup_bars": 50,
}


# ---------------------------------------------------------------------------
# Optimisation parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE: dict = {
    "rsi_period": [10, 14, 21],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "rsi_exit": [45, 50, 55],
    "ema_trend_period": [100, 200],
    "trend_required": [True, False],
    "require_divergence": [False, True],
    "divergence_lookback": [10, 20, 30],
    "require_bb_touch": [False, True],
    "bb_period": [14, 20, 30],
    "bb_std": [1.5, 2.0, 2.5],
    "require_reversal_candle": [True, False],
    "sl_atr_mult": [1.0, 1.5, 2.0],
    "tp_atr_mult": [2.0, 3.0, 4.0],
    "adx_max": [20, 25, 30],
    "require_volume_spike": [False, True],
    "warmup_bars": [50],
}


# ---------------------------------------------------------------------------
# Column name helpers
# ---------------------------------------------------------------------------


def _ema_col(period: int) -> str:
    return f"ema_{period}"


def _rsi_col(period: int) -> str:
    return f"rsi_{period}"


def _resolve_params(params: dict | None) -> dict:
    """Merge user params with defaults, returning a resolved dict."""
    resolved = dict(DEFAULT_PARAMS)
    if params:
        resolved.update(params)
    return resolved


# ---------------------------------------------------------------------------
# prepare_data - compute all indicators once on the full dataframe
# ---------------------------------------------------------------------------


def prepare_data(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Add all required indicators to the dataframe.

    Called once before running the backtest.  Modifies *df* in-place and
    also returns it for chaining.

    Columns added:
      - ``ema_{ema_trend_period}``
      - ``rsi_{rsi_period}``
      - ``atr``
      - ``adx``, ``plus_di``, ``minus_di``
      - ``bb_upper``, ``bb_middle``, ``bb_lower``, ``bb_width``, ``bb_position``
      - ``is_hammer``, ``is_shooting_star``, ``is_bullish_engulfing``,
        ``is_bearish_engulfing``, ``is_doji``, ``is_pinbar_bull``, ``is_pinbar_bear``
      - ``vol_ratio`` (if tick_volume column exists)
    """
    p = _resolve_params(params)

    compute_ema(df, period=p["ema_trend_period"], column="close")
    compute_rsi(df, period=p["rsi_period"], column="close")
    compute_atr(df, period=p["atr_period"], name="atr")
    compute_adx(df, period=p["atr_period"])
    compute_bollinger(
        df,
        period=p["bb_period"],
        std_dev=p["bb_std"],
        column="close",
    )
    compute_candle_patterns(df)

    if "tick_volume" in df.columns:
        try:
            compute_volume_ratio(df, period=p["atr_period"])
        except Exception:
            # volume column may have all zeros
            pass

    return df


# ---------------------------------------------------------------------------
# generate_signal - bar-by-bar entry logic
# ---------------------------------------------------------------------------


def generate_signal(
    df: pd.DataFrame,
    i: int,
    params: dict | None = None,
) -> Union[int, dict]:
    """Generate entry signal at bar *i*.

    Steps:
      1. EMA 200 trend: long only if close > EMA, short only if close < EMA.
      2. RSI extreme: long requires RSI <= oversold, short requires RSI >= overbought.
      3. ADX cap: ADX <= adx_max (weak trend = good mean reversion).
      4. Optional BB touch: price touches the BB band extreme.
      5. Optional reversal candle: hammer / shooting star / engulfing.
      6. Optional divergence detection.

    Parameters
    ----------
    df : pd.DataFrame
        Data up to and including bar *i*  (``df.iloc[:i+1]``).
    i : int
        Current bar index (position in the original DataFrame).
    params : dict, optional
        Strategy parameters.  Merged with ``DEFAULT_PARAMS``.

    Returns
    -------
    int | dict
        * ``0``  - no trade
        * ``1``  - BUY entry (SL/TP derived from ATR by the engine)
        * ``-1`` - SELL entry
        * ``{"direction": 1, "sl": float, "tp": float}`` - entry with custom SL/TP
    """
    p = _resolve_params(params)

    # Lazy indicator computation (cached once per backtest run)
    _ensure_indicators(df, p)

    # Current bar data
    row = df.iloc[i]
    close_i = float(row["close"])
    open_i = float(row["open"])
    high_i = float(row["high"])
    low_i = float(row["low"])

    # Column references
    ema_col = _ema_col(p["ema_trend_period"])
    rsi_col = _rsi_col(p["rsi_period"])

    ema_val = float(row.get(ema_col, np.nan))
    rsi_val = float(row.get(rsi_col, np.nan))
    atr_val = float(row.get("atr", np.nan))
    adx_val = float(row.get("adx", np.nan))

    # Guard: indicators must be valid (warmed up)
    if pd.isna(ema_val) or pd.isna(rsi_val) or pd.isna(atr_val) or pd.isna(adx_val):
        return 0
    if atr_val <= 0:
        return 0

    # ------------------------------------------------------------------
    # Step 1: EMA 200 trend filter
    # ------------------------------------------------------------------
    trend_bullish = close_i > ema_val
    trend_bearish = close_i < ema_val

    if p["trend_required"]:
        if not trend_bullish and not trend_bearish:
            return 0
    else:
        # When trend is not required, we can trade both directions
        trend_bullish = True
        trend_bearish = True

    # ------------------------------------------------------------------
    # Step 2: RSI extreme detection
    # ------------------------------------------------------------------
    rsi_oversold = rsi_val <= p["rsi_oversold"]
    rsi_overbought = rsi_val >= p["rsi_overbought"]

    # Long candidate: bullish trend + oversold RSI
    long_candidate = trend_bullish and rsi_oversold
    # Short candidate: bearish trend + overbought RSI
    short_candidate = trend_bearish and rsi_overbought

    if not long_candidate and not short_candidate:
        return 0

    # ------------------------------------------------------------------
    # Step 3: ADX cap (weak trend = good mean reversion)
    # ------------------------------------------------------------------
    if adx_val > p["adx_max"]:
        return 0

    # ------------------------------------------------------------------
    # Step 4: Optional BB touch confirmation
    # ------------------------------------------------------------------
    if p["require_bb_touch"]:
        bb_lower = float(row.get("bb_lower", np.nan))
        bb_upper = float(row.get("bb_upper", np.nan))

        if pd.isna(bb_lower) or pd.isna(bb_upper):
            return 0

        if long_candidate:
            # Price should be near or below lower BB band
            if low_i > bb_lower * 1.002:
                return 0
        if short_candidate:
            # Price should be near or above upper BB band
            if high_i < bb_upper * 0.998:
                return 0

    # ------------------------------------------------------------------
    # Step 5: Optional reversal candle confirmation
    # ------------------------------------------------------------------
    if p["require_reversal_candle"]:
        if long_candidate:
            if not _is_bullish_reversal_candle(row):
                return 0
        if short_candidate:
            if not _is_bearish_reversal_candle(row):
                return 0

    # ------------------------------------------------------------------
    # Step 6: Optional divergence detection
    # ------------------------------------------------------------------
    if p["require_divergence"]:
        lookback = p["divergence_lookback"]
        if long_candidate:
            if not _detect_bullish_divergence(df, i, rsi_col, lookback):
                return 0
        if short_candidate:
            if not _detect_bearish_divergence(df, i, rsi_col, lookback):
                return 0

    # ------------------------------------------------------------------
    # Step 7: Optional volume spike
    # ------------------------------------------------------------------
    if p["require_volume_spike"]:
        vol_ratio = float(row.get("vol_ratio", np.nan))
        if not pd.isna(vol_ratio) and vol_ratio < 1.5:
            return 0

    # ------------------------------------------------------------------
    # Signal
    # ------------------------------------------------------------------
    if long_candidate:
        return 1
    elif short_candidate:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Candle helpers
# ---------------------------------------------------------------------------


def _is_bullish_reversal_candle(row: pd.Series) -> bool:
    """Return True if the bar qualifies as a bullish reversal candle.

    Accepts: hammer, bullish engulfing, bullish pinbar, or simple bullish
    close (close > open).
    """
    # Hammer
    if bool(row.get("is_hammer", False)):
        return True
    # Bullish engulfing
    if bool(row.get("is_bullish_engulfing", False)):
        return True
    # Bullish pinbar
    if bool(row.get("is_pinbar_bull", False)):
        return True
    # Simple bullish candle
    if float(row["close"]) > float(row["open"]):
        return True
    return False


def _is_bearish_reversal_candle(row: pd.Series) -> bool:
    """Return True if the bar qualifies as a bearish reversal candle.

    Accepts: shooting star, bearish engulfing, bearish pinbar, or simple
    bearish close (close < open).
    """
    # Shooting star
    if bool(row.get("is_shooting_star", False)):
        return True
    # Bearish engulfing
    if bool(row.get("is_bearish_engulfing", False)):
        return True
    # Bearish pinbar
    if bool(row.get("is_pinbar_bear", False)):
        return True
    # Simple bearish candle
    if float(row["close"]) < float(row["open"]):
        return True
    return False


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


def _detect_bullish_divergence(
    df: pd.DataFrame,
    i: int,
    rsi_col: str,
    lookback: int,
) -> bool:
    """Detect bullish RSI divergence.

    Bullish divergence: price makes a lower low vs *lookback* bars ago,
    but RSI makes a higher low (momentum is strengthening despite lower price).

    Args:
        df: DataFrame slice up to bar *i*.
        i: Current bar index.
        rsi_col: Name of the RSI column.
        lookback: Number of bars to look back.

    Returns:
        True if bullish divergence is detected.
    """
    if i < lookback:
        return False

    start = max(0, i - lookback)
    # Find the lowest low and its corresponding RSI in the lookback window
    window = df.iloc[start : i + 1]
    low_prices = window["low"].astype(float)
    rsi_values = window[rsi_col].astype(float)

    if low_prices.empty or rsi_values.empty:
        return False

    # Current values
    current_low = float(df.iloc[i]["low"])
    current_rsi = float(df.iloc[i][rsi_col])

    # Find the previous lowest low in the window (excluding current bar)
    if len(window) < 2:
        return False

    prev_window = window.iloc[:-1]
    if len(prev_window) == 0:
        return False

    prev_min_low = prev_window["low"].min()
    prev_min_idx = prev_window["low"].idxmin()
    prev_rsi_at_min_low = float(prev_window.loc[prev_min_idx, rsi_col])

    if pd.isna(prev_min_low) or pd.isna(prev_rsi_at_min_low):
        return False
    if pd.isna(current_low) or pd.isna(current_rsi):
        return False

    # Price makes a lower low, RSI makes a higher low
    price_lower_low = current_low < prev_min_low
    rsi_higher_low = current_rsi > prev_rsi_at_min_low

    return price_lower_low and rsi_higher_low


def _detect_bearish_divergence(
    df: pd.DataFrame,
    i: int,
    rsi_col: str,
    lookback: int,
) -> bool:
    """Detect bearish RSI divergence.

    Bearish divergence: price makes a higher high vs *lookback* bars ago,
    but RSI makes a lower high (momentum is weakening despite higher price).

    Args:
        df: DataFrame slice up to bar *i*.
        i: Current bar index.
        rsi_col: Name of the RSI column.
        lookback: Number of bars to look back.

    Returns:
        True if bearish divergence is detected.
    """
    if i < lookback:
        return False

    start = max(0, i - lookback)
    window = df.iloc[start : i + 1]
    high_prices = window["high"].astype(float)
    rsi_values = window[rsi_col].astype(float)

    if high_prices.empty or rsi_values.empty:
        return False

    current_high = float(df.iloc[i]["high"])
    current_rsi = float(df.iloc[i][rsi_col])

    if len(window) < 2:
        return False

    prev_window = window.iloc[:-1]
    if len(prev_window) == 0:
        return False

    prev_max_high = prev_window["high"].max()
    prev_max_idx = prev_window["high"].idxmax()
    prev_rsi_at_max_high = float(prev_window.loc[prev_max_idx, rsi_col])

    if pd.isna(prev_max_high) or pd.isna(prev_rsi_at_max_high):
        return False
    if pd.isna(current_high) or pd.isna(current_rsi):
        return False

    # Price makes a higher high, RSI makes a lower high
    price_higher_high = current_high > prev_max_high
    rsi_lower_high = current_rsi < prev_rsi_at_max_high

    return price_higher_high and rsi_lower_high


# ---------------------------------------------------------------------------
# Internal: lazy indicator computation
# ---------------------------------------------------------------------------

# Cache keyed by the id of the underlying numpy array backing the DataFrame.
# Because ``df.iloc[:i+1]`` slices share the same ``.values.base`` we can
# detect that we have already computed indicators and avoid O(n^2) work.
_indicator_cache: set = set()


def _ensure_indicators(df: pd.DataFrame, params: dict) -> None:
    """Compute indicators on *df* if not already present."""
    rsi_col = _rsi_col(params["rsi_period"])
    if rsi_col in df.columns:
        return

    # Build a cache key from the underlying buffer
    try:
        base = df.values.base if df.values.base is not None else df.values
        cache_key = id(base)
    except Exception:
        cache_key = id(df)

    if cache_key in _indicator_cache:
        return
    _indicator_cache.add(cache_key)

    compute_ema(df, period=params["ema_trend_period"], column="close")
    compute_rsi(df, period=params["rsi_period"], column="close")
    compute_atr(df, period=params["atr_period"], name="atr")
    compute_adx(df, period=params["atr_period"])
    compute_bollinger(
        df,
        period=params["bb_period"],
        std_dev=params["bb_std"],
        column="close",
    )
    compute_candle_patterns(df)

    if "tick_volume" in df.columns:
        try:
            compute_volume_ratio(df, period=params["atr_period"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Convenience: run a full backtest with this strategy
# ---------------------------------------------------------------------------


def run(
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    starting_capital: float = 1000.0,
    params: dict | None = None,
    start_date: str = "",
    end_date: str = "",
) -> "BacktestResult":
    """Run a complete backtest of the RSI Mean Reversion strategy.

    Parameters
    ----------
    symbol : str
        Trading symbol (EURUSD, XAUUSD, ...).
    timeframe : str
        Bar timeframe (M15, H1, ...).
    starting_capital : float
        Initial account balance in EUR.
    params : dict, optional
        Strategy parameter overrides.
    start_date : str
        Start date YYYY-MM-DD (empty = 365 days ago).
    end_date : str
        End date YYYY-MM-DD (empty = now).

    Returns
    -------
    BacktestResult
    """
    from strategiestoTest.core.config import StrategyConfig
    from strategiestoTest.core.engine import BacktestEngine

    p = _resolve_params(params)

    config = StrategyConfig(
        name="rsi_mean_reversion",
        symbol=symbol,
        timeframes=[timeframe],
        starting_capital=starting_capital,
        start_date=start_date,
        end_date=end_date,
    )
    engine = BacktestEngine(config)
    result = engine.run(generate_signal, params=p)
    return result


# ---------------------------------------------------------------------------
# Standalone entry point (for quick testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="RSI Mean Reversion with EMA 200 Trend Filter"
    )
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--rsi-oversold", type=float, default=30.0)
    ap.add_argument("--rsi-overbought", type=float, default=70.0)
    ap.add_argument("--ema-period", type=int, default=200)
    ap.add_argument("--adx-max", type=float, default=25.0)
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-atr", type=float, default=3.0)
    ap.add_argument("--no-trend", action="store_true",
                    help="Disable EMA 200 trend filter")
    ap.add_argument("--no-candle", action="store_true",
                    help="Disable reversal candle confirmation")
    ap.add_argument("--bb-touch", action="store_true",
                    help="Require Bollinger Band touch")
    ap.add_argument("--divergence", action="store_true",
                    help="Require RSI divergence")
    ap.add_argument("--volume", action="store_true",
                    help="Require volume spike")
    ap.add_argument("--start-date", default="")
    ap.add_argument("--end-date", default="")
    args = ap.parse_args()

    overrides: dict = {
        "rsi_period": args.rsi_period,
        "rsi_oversold": args.rsi_oversold,
        "rsi_overbought": args.rsi_overbought,
        "ema_trend_period": args.ema_period,
        "adx_max": args.adx_max,
        "sl_atr_mult": args.sl_atr,
        "tp_atr_mult": args.tp_atr,
    }
    if args.no_trend:
        overrides["trend_required"] = False
    if args.no_candle:
        overrides["require_reversal_candle"] = False
    if args.bb_touch:
        overrides["require_bb_touch"] = True
    if args.divergence:
        overrides["require_divergence"] = True
    if args.volume:
        overrides["require_volume_spike"] = True

    result = run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_capital=args.capital,
        params=overrides,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    print(f"\n=== RSI Mean Reversion [{args.symbol} {args.timeframe}] ===")
    print(f"Total trades : {result.total_trades}")
    print(f"Win rate     : {result.win_rate_pct:.1f}%")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(f"Net profit   : {result.net_profit_eur:.2f} EUR")
    print(f"Max drawdown : {result.max_drawdown_pct:.2f}%")
    print(f"Sharpe ratio : {result.sharpe_ratio:.2f}")
    print(f"Expectancy   : {result.expectancy_eur:.2f} EUR")
    print(f"Avg RR ratio : {result.avg_rr_ratio:.2f}")