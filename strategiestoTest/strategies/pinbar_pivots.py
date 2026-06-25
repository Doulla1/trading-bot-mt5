"""
Strategy: Pin Bar aux Pivot Points (Price Action).

Trades pin bar rejections at key daily pivot levels (S/R).
- Bullish pin bar at support (S1/S2/S3) with RSI not overbought, ADX filter.
- Bearish pin bar at resistance (R1/R2/R3) with RSI not oversold, ADX filter.
- Optional EMA 200 trend alignment.
- Custom SL/TP: SL beyond pinbar extreme, TP at next pivot level.

Uses ``BacktestEngine.run(signal_fn, params)`` API.
"""

from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from strategiestoTest.core.indicators import (
    align_pivots_to_intraday,
    compute_adx,
    compute_atr,
    compute_ema,
    compute_pivots,
    compute_rsi,
)

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    "pivot_method": "classic",                # "classic" or "camarilla"
    "pivot_levels_long": ["s1", "s2", "s3"],  # support levels for long entries
    "pivot_levels_short": ["r1", "r2", "r3"], # resistance levels for short entries
    "pivot_touch_tolerance_pct": 0.0008,      # % tolerance for "touching" a pivot
    "pinbar_body_ratio": 3.0,                 # min shadow/body ratio for pin bar
    "pinbar_nose_ratio": 0.35,                # max opposite shadow/body ratio
    "require_ema_trend_filter": True,         # filter by EMA 200 trend
    "ema_trend_period": 200,
    "adx_min": 20,                            # min ADX for valid market
    "rsi_period": 14,
    "rsi_confirm_long_max": 50,               # RSI must be <= this for long
    "rsi_confirm_short_min": 50,              # RSI must be >= this for short
    "atr_period": 14,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 3.0,
    "next_level_tp": True,                    # TP = next pivot level instead of ATR-based
    "sl_pips_beyond_extreme": 5.0,            # pips beyond pinbar extreme for SL
}

# ---------------------------------------------------------------------------
# Optimisation parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE: dict = {
    "pivot_method": ["classic", "camarilla"],
    "pivot_levels_long": [["s1"], ["s1", "s2"], ["s1", "s2", "s3"]],
    "pivot_levels_short": [["r1"], ["r1", "r2"], ["r1", "r2", "r3"]],
    "pivot_touch_tolerance_pct": [0.0005, 0.0008, 0.0012],
    "pinbar_body_ratio": [2.0, 3.0, 4.0],
    "pinbar_nose_ratio": [0.2, 0.35, 0.5],
    "require_ema_trend_filter": [True, False],
    "adx_min": [15, 20, 25],
    "rsi_confirm_long_max": [40, 50, 60],
    "rsi_confirm_short_min": [40, 50, 60],
    "sl_atr_mult": [1.0, 1.5, 2.0],
    "tp_atr_mult": [2.0, 3.0, 4.0],
    "next_level_tp": [True, False],
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
# prepare_data - compute pivots & indicators once
# ---------------------------------------------------------------------------


def prepare_data(
    df_intraday: pd.DataFrame,
    df_daily: pd.DataFrame,
    params: dict | None = None,
) -> pd.DataFrame:
    """Compute daily pivots, align to intraday, and compute all indicators.

    Modifies *df_intraday* in-place and also returns it for chaining.

    Parameters
    ----------
    df_intraday : pd.DataFrame
        Intraday OHLCV data (M15, H1, ...).
    df_daily : pd.DataFrame
        Daily OHLCV data (D1) used to compute pivot points.
    params : dict, optional
        Strategy parameters.  Merged with ``DEFAULT_PARAMS``.

    Returns
    -------
    pd.DataFrame
        The mutated *df_intraday* with indicator columns added.
    """
    p = _resolve_params(params)

    # 1. Compute daily pivot levels
    df_pivots = compute_pivots(df_daily.copy(), method=p["pivot_method"])

    # 2. Align pivots to intraday (each bar gets previous day's pivots)
    align_pivots_to_intraday(df_intraday, df_pivots)

    # 3. Compute indicators on intraday
    if p["require_ema_trend_filter"]:
        compute_ema(df_intraday, period=p["ema_trend_period"], column="close")

    compute_rsi(df_intraday, period=p["rsi_period"], column="close")
    compute_atr(df_intraday, period=p["atr_period"], name="atr")
    compute_adx(df_intraday, period=p["atr_period"])

    return df_intraday


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
        Data up to and including bar *i* (``df.iloc[:i+1]``).
    i : int
        Current bar index (position in the original DataFrame).
    params : dict, optional
        Strategy parameters.  Merged with ``DEFAULT_PARAMS``.

    Returns
    -------
    int | dict
        * ``0``  - no trade
        * ``1``  - BUY entry
        * ``-1`` - SELL entry
        * ``{"direction": 1, "sl": float, "tp": float}`` - entry with custom SL/TP
    """
    p = _resolve_params(params)

    # Lazy indicator computation (cached once per backtest run)
    _ensure_indicators(df, p)

    # Current bar data
    row = df.iloc[i]
    open_i = float(row["open"])
    high_i = float(row["high"])
    low_i = float(row["low"])
    close_i = float(row["close"])

    # ------------------------------------------------------------------
    # Guard: indicators must be valid
    # ------------------------------------------------------------------
    adx_i = float(row.get("adx", np.nan))
    rsi_i = float(row[_rsi_col(p["rsi_period"])])
    atr_i = float(row.get("atr", np.nan))

    if pd.isna(adx_i) or pd.isna(rsi_i) or pd.isna(atr_i) or atr_i <= 0:
        return 0

    # ------------------------------------------------------------------
    # Step 1: Identify Pin Bar
    # ------------------------------------------------------------------
    body = abs(close_i - open_i)
    total_range = high_i - low_i

    if body <= 0 or total_range <= 0:
        return 0

    upper_shadow = high_i - max(open_i, close_i)
    lower_shadow = min(open_i, close_i) - low_i

    # -- Bullish pin bar --
    # Long lower shadow, small upper shadow, body near the top
    bullish_pinbar = (
        lower_shadow >= p["pinbar_body_ratio"] * body
        and upper_shadow <= p["pinbar_nose_ratio"] * body
        and (close_i > open_i)
        and (min(open_i, close_i) >= low_i + (2.0 / 3.0) * total_range)
    )

    # -- Bearish pin bar --
    # Long upper shadow, small lower shadow, body near the bottom
    bearish_pinbar = (
        upper_shadow >= p["pinbar_body_ratio"] * body
        and lower_shadow <= p["pinbar_nose_ratio"] * body
        and (close_i < open_i)
        and (max(open_i, close_i) <= high_i - (2.0 / 3.0) * total_range)
    )

    if not bullish_pinbar and not bearish_pinbar:
        return 0

    # ------------------------------------------------------------------
    # Step 2: Check Pivot Touch
    # ------------------------------------------------------------------
    tolerance = p["pivot_touch_tolerance_pct"]

    # Helper: does a price touch a specific pivot level?
    def _touches(price: float, level_val: float) -> bool:
        if pd.isna(level_val) or level_val <= 0:
            return False
        return (
            abs(price - level_val) / level_val <= tolerance
            or (price <= level_val * 1.001 and price >= level_val * 0.999)
        )

    if bullish_pinbar:
        # Low of the pinbar must touch one of the support levels
        touched_level = None
        for level_name in p["pivot_levels_long"]:
            level_val = float(row.get(level_name, np.nan))
            if _touches(low_i, level_val):
                touched_level = level_name
                break

        if touched_level is None:
            return 0

        direction = 1
        entry_price = close_i

    else:  # bearish_pinbar
        # High of the pinbar must touch one of the resistance levels
        touched_level = None
        for level_name in p["pivot_levels_short"]:
            level_val = float(row.get(level_name, np.nan))
            if _touches(high_i, level_val):
                touched_level = level_name
                break

        if touched_level is None:
            return 0

        direction = -1
        entry_price = close_i

    # ------------------------------------------------------------------
    # Step 3: EMA Trend Filter (optional)
    # ------------------------------------------------------------------
    if p["require_ema_trend_filter"]:
        ema_col = _ema_col(p["ema_trend_period"])
        ema_val = float(row.get(ema_col, np.nan))
        if pd.isna(ema_val):
            return 0

        if direction == 1 and close_i <= ema_val:
            return 0  # Long requires close > EMA (uptrend)
        if direction == -1 and close_i >= ema_val:
            return 0  # Short requires close < EMA (downtrend)

    # ------------------------------------------------------------------
    # Step 4: RSI Confirmation
    # ------------------------------------------------------------------
    if direction == 1 and rsi_i > p["rsi_confirm_long_max"]:
        return 0  # Long: RSI must not be overbought
    if direction == -1 and rsi_i < p["rsi_confirm_short_min"]:
        return 0  # Short: RSI must not be oversold

    # ------------------------------------------------------------------
    # Step 5: ADX Filter
    # ------------------------------------------------------------------
    if adx_i < p["adx_min"]:
        return 0

    # ------------------------------------------------------------------
    # Compute SL (stop-loss)
    # ------------------------------------------------------------------
    # We need pip_size for the "pips beyond extreme" calculation.
    # Derive it from the typical pip size for this symbol based on price magnitude.
    pip_size = _guess_pip_size(entry_price)

    sl_pips_dist = p["sl_pips_beyond_extreme"] * pip_size
    min_sl_dist = p["sl_atr_mult"] * atr_i

    if direction == 1:
        # SL: 5 pips below the pinbar low, minimum 1.5 * ATR
        sl = low_i - max(sl_pips_dist, min_sl_dist)
    else:
        # SL: 5 pips above the pinbar high, minimum 1.5 * ATR
        sl = high_i + max(sl_pips_dist, min_sl_dist)

    # ------------------------------------------------------------------
    # Compute TP (take-profit)
    # ------------------------------------------------------------------
    if p["next_level_tp"]:
        tp = _find_next_pivot_level(
            row, direction, entry_price, atr_i, p
        )
    else:
        tp = None

    if tp is None:
        tp_dist = p["tp_atr_mult"] * atr_i
        if direction == 1:
            tp = entry_price + tp_dist
        else:
            tp = entry_price - tp_dist

    return {
        "direction": direction,
        "sl": round(float(sl), 8),
        "tp": round(float(tp), 8),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_pip_size(price: float) -> float:
    """Heuristic pip size based on price magnitude.

    - Price > 100 (e.g. XAUUSD ~2600, indices): pip = 0.01
    - Price ~ 100 (JPY pairs): pip = 0.01
    - Price ~ 1 (most forex): pip = 0.0001
    """
    if price >= 50:
        return 0.01
    return 0.0001


def _find_next_pivot_level(
    row: pd.Series,
    direction: int,
    entry_price: float,
    atr_val: float,
    params: dict,
) -> float | None:
    """Find the next pivot level in the trade direction.

    For long: first pivot level strictly above entry_price.
    For short: first pivot level strictly below entry_price.

    Returns None if no suitable level is found or the level is too close
    (< 0.5 * ATR).
    """
    pivot_names = ["s3", "s2", "s1", "pp", "r1", "r2", "r3"]
    levels: list[float] = []
    for name in pivot_names:
        val = row.get(name, np.nan)
        if not pd.isna(val):
            levels.append(float(val))

    if not levels:
        return None

    levels.sort()

    min_tp_dist = 0.5 * atr_val

    if direction == 1:
        for lvl in levels:
            if lvl > entry_price and (lvl - entry_price) >= min_tp_dist:
                return lvl
    else:
        for lvl in reversed(levels):
            if lvl < entry_price and (entry_price - lvl) >= min_tp_dist:
                return lvl

    return None


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
    if rsi_col in df.columns and "adx" in df.columns and "atr" in df.columns:
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

    if params["require_ema_trend_filter"]:
        compute_ema(df, period=params["ema_trend_period"], column="close")

    compute_rsi(df, period=params["rsi_period"], column="close")
    compute_atr(df, period=params["atr_period"], name="atr")
    compute_adx(df, period=params["atr_period"])


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
    """Run a complete backtest of the Pinbar Pivots strategy.

    Loads intraday and daily data, prepares indicators, and runs the
    bar-by-bar simulation.

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

    Returns
    -------
    BacktestResult
    """
    from strategiestoTest.core.config import StrategyConfig
    from strategiestoTest.core.data_loader import load_data
    from strategiestoTest.core.engine import BacktestEngine

    p = _resolve_params(params)

    # Load intraday and daily data
    df_intraday = load_data(symbol, timeframe)
    df_daily = load_data(symbol, "D1")

    if len(df_intraday) == 0:
        raise RuntimeError(f"No intraday data for {symbol} {timeframe}")
    if len(df_daily) == 0:
        raise RuntimeError(f"No daily data for {symbol}")

    # Pre-compute pivots and indicators
    prepare_data(df_intraday, df_daily, params=p)

    config = StrategyConfig(
        name="pinbar_pivots",
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

    ap = argparse.ArgumentParser(description="Pinbar Pivots Backtest")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--method", default="classic", choices=["classic", "camarilla"])
    ap.add_argument("--pinbar-ratio", type=float, default=3.0,
                    help="Min shadow/body ratio")
    ap.add_argument("--pinbar-nose", type=float, default=0.35,
                    help="Max opposite shadow/body ratio")
    ap.add_argument("--tolerance", type=float, default=0.0008,
                    help="Pivot touch tolerance pct")
    ap.add_argument("--adx-min", type=float, default=20.0)
    ap.add_argument("--rsi-long-max", type=float, default=50.0)
    ap.add_argument("--rsi-short-min", type=float, default=50.0)
    ap.add_argument("--no-ema", action="store_true",
                    help="Disable EMA 200 trend filter")
    ap.add_argument("--no-next-level", action="store_true",
                    help="Use ATR-based TP instead of next pivot level")
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-atr", type=float, default=3.0)
    args = ap.parse_args()

    overrides = {
        "pivot_method": args.method,
        "pinbar_body_ratio": args.pinbar_ratio,
        "pinbar_nose_ratio": args.pinbar_nose,
        "pivot_touch_tolerance_pct": args.tolerance,
        "adx_min": args.adx_min,
        "rsi_confirm_long_max": args.rsi_long_max,
        "rsi_confirm_short_min": args.rsi_short_min,
        "require_ema_trend_filter": not args.no_ema,
        "next_level_tp": not args.no_next_level,
        "sl_atr_mult": args.sl_atr,
        "tp_atr_mult": args.tp_atr,
    }

    result = run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_capital=args.capital,
        params=overrides,
    )

    print(f"\n=== Pinbar Pivots [{args.symbol} {args.timeframe}] ===")
    print(f"Total trades : {result.total_trades}")
    print(f"Win rate     : {result.win_rate_pct:.1f}%")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(f"Net profit   : {result.net_profit_eur:.2f} EUR")
    print(f"Max drawdown : {result.max_drawdown_pct:.2f}%")
    print(f"Sharpe ratio : {result.sharpe_ratio:.2f}")
    print(f"Expectancy   : {result.expectancy_eur:.2f} EUR")
