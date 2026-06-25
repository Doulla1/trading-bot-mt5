"""
Strategy: EMA 50/200 Pullback + RSI (Trend Continuation).

Trades pullbacks in the direction of the dominant trend.
- Bullish trend: EMA_fast > EMA_slow AND close > EMA_slow
- Bearish trend: EMA_fast < EMA_slow AND close < EMA_slow

Entry: price pulls back close to EMA_fast with RSI confirming (oversold in uptrend,
  overbought in downtrend). Optional candle pattern confirmation.

Uses ``BacktestEngine.run(signal_fn, params)`` API.
"""

from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from strategiestoTest.core.indicators import (
    compute_ema,
    compute_rsi,
    compute_atr,
    compute_candle_patterns,
)

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    "ema_fast": 50,
    "ema_slow": 200,
    "rsi_period": 14,
    "rsi_entry_low": 40,          # RSI <= this for long entry (oversold in uptrend)
    "rsi_entry_high": 60,         # RSI >= this for short entry (overbought in downtrend)
    "rsi_exit_low": 70,           # RSI exit zone for longs (not currently used by engine)
    "rsi_exit_high": 30,          # RSI exit zone for shorts (not currently used by engine)
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 3.0,
    "min_trend_strength_pct": 0.001,       # minimum % separation between EMAs
    "require_ema_touch": True,
    "ema_touch_threshold_pct": 0.0015,     # % of price within which EMA is "touched"
    "require_candle_confirmation": True,
}

# ---------------------------------------------------------------------------
# Optimisation parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE: dict = {
    "ema_fast": [30, 50, 100],
    "ema_slow": [100, 200],
    "rsi_period": [10, 14, 21],
    "rsi_entry_low": [30, 35, 40, 45],
    "rsi_entry_high": [55, 60, 65, 70],
    "rsi_exit_low": [65, 70, 75],
    "rsi_exit_high": [25, 30, 35],
    "atr_period": [10, 14, 20],
    "sl_atr_mult": [1.0, 1.5, 2.0],
    "tp_atr_mult": [2.0, 3.0, 4.0],
    "min_trend_strength_pct": [0.0005, 0.001, 0.002],
    "ema_touch_threshold_pct": [0.001, 0.0015, 0.002],
    "require_candle_confirmation": [True, False],
}

# ---------------------------------------------------------------------------
# Column name helpers
# ---------------------------------------------------------------------------


def _ema_col(period: int) -> str:
    return f"ema_{period}"


def _rsi_col(period: int) -> str:
    return f"rsi_{period}"


def _resolve_params(params: dict) -> dict:
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
      - ``ema_{fast}``, ``ema_{slow}``
      - ``rsi_{rsi_period}``
      - ``atr``
      - ``is_hammer``, ``is_shooting_star``, ``is_bullish_engulfing``,
        ``is_bearish_engulfing``, ``is_doji``, ``is_pinbar_bull``,
        ``is_pinbar_bear``
    """
    p = _resolve_params(params)

    compute_ema(df, period=p["ema_fast"], column="close")
    compute_ema(df, period=p["ema_slow"], column="close")
    compute_rsi(df, period=p["rsi_period"], column="close")
    compute_atr(df, period=p["atr_period"], name="atr")
    compute_candle_patterns(df)

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

    ema_fast_col = _ema_col(p["ema_fast"])
    ema_slow_col = _ema_col(p["ema_slow"])
    rsi_col = _rsi_col(p["rsi_period"])

    # Ensure indicators are present on the slice.
    # The engine passes ``df.iloc[:i+1]`` at every bar, which may be a copy.
    # We compute indicators lazily on first access and cache via the
    # underlying numpy array identity so each backtest only computes once.
    _ensure_indicators(df, p)

    # Current bar data
    row = df.iloc[i]
    close_i = float(row["close"])
    open_i = float(row["open"])
    high_i = float(row["high"])
    low_i = float(row["low"])

    ema_fast_i = float(row[ema_fast_col])
    ema_slow_i = float(row[ema_slow_col])
    rsi_i = float(row[rsi_col])

    # Guard: need at least the slow EMA to be valid (warmup)
    if pd.isna(ema_slow_i) or pd.isna(ema_fast_i) or pd.isna(rsi_i):
        return 0

    # ------------------------------------------------------------------
    # Step 1: Determine trend
    # ------------------------------------------------------------------
    bullish_trend = (ema_fast_i > ema_slow_i) and (close_i > ema_slow_i)
    bearish_trend = (ema_fast_i < ema_slow_i) and (close_i < ema_slow_i)

    if not bullish_trend and not bearish_trend:
        return 0

    # ------------------------------------------------------------------
    # Step 2: Check trend strength
    # ------------------------------------------------------------------
    if ema_slow_i <= 0:
        return 0
    trend_strength = abs(ema_fast_i - ema_slow_i) / ema_slow_i
    if trend_strength <= p["min_trend_strength_pct"]:
        return 0

    # ------------------------------------------------------------------
    # Step 3: Pullback detection
    # ------------------------------------------------------------------
    threshold = p["ema_touch_threshold_pct"]
    require_ema = p["require_ema_touch"]
    require_candle = p["require_candle_confirmation"]

    if bullish_trend:
        # Price pullback toward EMA fast: low[i] is near ema_fast[i]
        ema_touched = False
        if require_ema:
            ema_upper = ema_fast_i * (1.0 + threshold)
            ema_lower = ema_fast_i * (1.0 - threshold / 2.0)
            ema_touched = (low_i <= ema_upper) and (low_i >= ema_lower)
        else:
            ema_touched = True  # skip EMA touch check

        # RSI must be oversold within the uptrend
        rsi_ok = rsi_i <= p["rsi_entry_low"]

        if not (ema_touched and rsi_ok):
            return 0

        # Candle confirmation (optional)
        if require_candle:
            if not _is_bullish_candle(row):
                return 0

        # Step 4: BUY signal
        return 1

    else:  # bearish_trend
        # Price pullback toward EMA fast: high[i] is near ema_fast[i]
        ema_touched = False
        if require_ema:
            ema_upper = ema_fast_i * (1.0 + threshold / 2.0)
            ema_lower = ema_fast_i * (1.0 - threshold)
            ema_touched = (high_i >= ema_lower) and (high_i <= ema_upper)
        else:
            ema_touched = True

        # RSI must be overbought within the downtrend
        rsi_ok = rsi_i >= p["rsi_entry_high"]

        if not (ema_touched and rsi_ok):
            return 0

        # Candle confirmation (optional)
        if require_candle:
            if not _is_bearish_candle(row):
                return 0

        # Step 4: SELL signal
        return -1


# ---------------------------------------------------------------------------
# Candle helpers
# ---------------------------------------------------------------------------


def _is_bullish_candle(row: pd.Series) -> bool:
    """Return True if the bar qualifies as a bullish confirmation candle."""
    # Bullish close > open
    if float(row["close"]) > float(row["open"]):
        return True
    # Hammer
    if bool(row.get("is_hammer", False)):
        return True
    # Bullish engulfing
    if bool(row.get("is_bullish_engulfing", False)):
        return True
    # Bullish pinbar
    if bool(row.get("is_pinbar_bull", False)):
        return True
    return False


def _is_bearish_candle(row: pd.Series) -> bool:
    """Return True if the bar qualifies as a bearish confirmation candle."""
    # Bearish close < open
    if float(row["close"]) < float(row["open"]):
        return True
    # Shooting star
    if bool(row.get("is_shooting_star", False)):
        return True
    # Bearish engulfing
    if bool(row.get("is_bearish_engulfing", False)):
        return True
    # Bearish pinbar
    if bool(row.get("is_pinbar_bear", False)):
        return True
    return False


# ---------------------------------------------------------------------------
# Internal: lazy indicator computation
# ---------------------------------------------------------------------------

# Cache keyed by the id of the underlying numpy array backing the DataFrame.
# Because ``df.iloc[:i+1]`` slices share the same ``.values.base`` we can
# detect that we have already computed indicators and avoid O(n^2) work.
_indicator_cache: set = set()


def _ensure_indicators(df: pd.DataFrame, params: dict) -> None:
    """Compute indicators on *df* if not already present."""
    ema_fast_col = _ema_col(params["ema_fast"])
    if ema_fast_col in df.columns:
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

    compute_ema(df, period=params["ema_fast"], column="close")
    compute_ema(df, period=params["ema_slow"], column="close")
    compute_rsi(df, period=params["rsi_period"], column="close")
    compute_atr(df, period=params["atr_period"], name="atr")
    compute_candle_patterns(df)


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
    """Run a complete backtest of the EMA Trend strategy.

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
        name="ema_trend",
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

    ap = argparse.ArgumentParser(description="EMA Trend Pullback Backtest")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--ema-fast", type=int, default=50)
    ap.add_argument("--ema-slow", type=int, default=200)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--rsi-entry-low", type=float, default=40.0)
    ap.add_argument("--rsi-entry-high", type=float, default=60.0)
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-atr", type=float, default=3.0)
    ap.add_argument("--no-candle", action="store_true",
                    help="Disable candle confirmation")
    args = ap.parse_args()

    overrides = {
        "ema_fast": args.ema_fast,
        "ema_slow": args.ema_slow,
        "rsi_period": args.rsi_period,
        "rsi_entry_low": args.rsi_entry_low,
        "rsi_entry_high": args.rsi_entry_high,
        "sl_atr_mult": args.sl_atr,
        "tp_atr_mult": args.tp_atr,
    }
    if args.no_candle:
        overrides["require_candle_confirmation"] = False

    result = run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_capital=args.capital,
        params=overrides,
    )

    print(f"\n=== EMA Trend [{args.symbol} {args.timeframe}] ===")
    print(f"Total trades : {result.total_trades}")
    print(f"Win rate     : {result.win_rate_pct:.1f}%")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(f"Net profit   : {result.net_profit_eur:.2f} EUR")
    print(f"Max drawdown : {result.max_drawdown_pct:.2f}%")
    print(f"Sharpe ratio : {result.sharpe_ratio:.2f}")
    print(f"Expectancy   : {result.expectancy_eur:.2f} EUR")
