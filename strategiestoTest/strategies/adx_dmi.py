"""
Strategy: ADX + DMI (Directional Movement Index) - Trend Following.

Trades strong, confirmed trends using ADX for trend strength and +DI/-DI
crossovers for directional signals.

- ADX >= threshold AND rising: trend is strengthening
- ADX < extreme: trend not yet exhausted
- +DI > -DI: bullish directional movement dominates (LONG)
- -DI > +DI: bearish directional movement dominates (SHORT)
- Optional DI crossover entry: only enter on fresh +DI/-DI crossover
- Optional EMA 200 trend filter: only trade in EMA direction
- Optional volume confirmation: volume spike above average

Exits are handled by the engine via:
- Trailing stop (activated after profit reaches trailing_activation_atr * ATR)
- Fixed TP based on tp_atr_mult * ATR
- DI crossover exit: no new entries in opposite direction (engine holds position)

Uses ``BacktestEngine.run(signal_fn, params)`` API.
"""
from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

from strategiestoTest.core.indicators import (
    compute_adx,
    compute_atr,
    compute_ema,
    compute_volume_ratio,
)


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    # ADX
    "adx_period": 14,
    "adx_threshold": 25,           # ADX must be >= this (= trending market)
    "adx_rising_bars": 2,          # ADX must have been rising for N consecutive bars
    "adx_extreme": 40,             # ADX >= this = trend may be exhausting, skip entry

    # DI crossover
    "di_crossover_entry": True,    # enter only on fresh +DI/-DI crossover
    "di_crossover_exit": True,     # skip entries when DI crosses back (engine handles exit)

    # Trend strength
    "di_separation_min": 5,        # minimum absolute separation between +DI and -DI

    # EMA trend filter
    "ema_trend_period": 200,
    "use_ema_filter": True,        # only trade in EMA direction

    # Volume confirmation
    "require_volume_confirmation": False,
    "volume_ratio_min": 1.2,       # volume must be > this * 20-bar average

    # Trade management
    "atr_period": 14,
    "sl_atr_mult": 2.0,
    "tp_atr_mult": 4.0,            # let trends run: 4x ATR
    "use_trailing_stop": True,
    "trailing_activation_atr": 1.5,  # activate trailing when profit > 1.5 * ATR
    "trailing_distance_atr": 1.0,    # trail at 1.0 * ATR behind

    # ADX-based exit
    "adx_falling_exit": True,      # skip entries when ADX is falling
    "adx_falling_bars": 3,         # ADX falling for N consecutive bars = no entry
}

# ---------------------------------------------------------------------------
# Optimisation parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE: dict = {
    "adx_period": [10, 14, 20],
    "adx_threshold": [20, 25, 30],
    "adx_rising_bars": [1, 2, 3],
    "adx_extreme": [35, 40, 50],
    "di_crossover_entry": [True, False],
    "di_separation_min": [3, 5, 8],
    "use_ema_filter": [True, False],
    "require_volume_confirmation": [True, False],
    "sl_atr_mult": [1.5, 2.0, 2.5],
    "tp_atr_mult": [3.0, 4.0, 5.0],
}

# ---------------------------------------------------------------------------
# Column name helpers
# ---------------------------------------------------------------------------


def _ema_col(period: int) -> str:
    return f"ema_{period}"


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
      - ``adx``, ``plus_di``, ``minus_di`` (via compute_adx)
      - ``ema_{ema_trend_period}``
      - ``atr``
      - ``vol_ratio`` (if volume confirmation enabled)
    """
    p = _resolve_params(params)

    compute_adx(df, period=p["adx_period"])
    compute_atr(df, period=p["atr_period"], name="atr")

    if p["use_ema_filter"]:
        compute_ema(df, period=p["ema_trend_period"], column="close")

    if p["require_volume_confirmation"]:
        compute_volume_ratio(df, period=20)

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
        Data up to and including bar *i* (``df.iloc[:i+1]``).
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

    # ------------------------------------------------------------------
    # Guard: need enough bars for all lookbacks
    # ------------------------------------------------------------------
    max_lookback = max(
        p["adx_period"],
        p["atr_period"],
        p["adx_rising_bars"] + 1,
        p["adx_falling_bars"] + 1,
        p["ema_trend_period"] if p["use_ema_filter"] else 0,
    )
    if i < max_lookback:
        return 0

    # Current bar data
    row = df.iloc[i]
    close_i = float(row["close"])

    # ------------------------------------------------------------------
    # Step 1: ADX validity
    # ------------------------------------------------------------------
    adx_i = float(row.get("adx", np.nan))
    if pd.isna(adx_i):
        return 0

    # ADX must be above threshold (trend exists)
    if adx_i < p["adx_threshold"]:
        return 0

    # ADX must be below extreme (trend not exhausted)
    if adx_i >= p["adx_extreme"]:
        return 0

    # ADX must be rising for N consecutive bars
    rising_bars = p["adx_rising_bars"]
    if rising_bars > 0:
        for k in range(rising_bars):
            idx_curr = i - k
            idx_prev = i - k - 1
            if idx_curr < 0 or idx_prev < 0:
                return 0
            adx_curr = float(df.iloc[idx_curr].get("adx", np.nan))
            adx_prev = float(df.iloc[idx_prev].get("adx", np.nan))
            if pd.isna(adx_curr) or pd.isna(adx_prev):
                return 0
            if adx_curr <= adx_prev:
                return 0

    # ------------------------------------------------------------------
    # Step 2: ADX falling exit check (skip entry)
    # ------------------------------------------------------------------
    if p["adx_falling_exit"]:
        falling_bars = p["adx_falling_bars"]
        is_falling = True
        for k in range(1, falling_bars + 1):
            idx_curr = i - k + 1
            idx_prev = i - k
            if idx_curr < 0 or idx_prev < 0:
                is_falling = False
                break
            adx_curr = float(df.iloc[idx_curr].get("adx", np.nan))
            adx_prev = float(df.iloc[idx_prev].get("adx", np.nan))
            if pd.isna(adx_curr) or pd.isna(adx_prev):
                is_falling = False
                break
            if adx_curr >= adx_prev:
                is_falling = False
                break
        if is_falling:
            return 0  # ADX is weakening - skip entry

    # ------------------------------------------------------------------
    # Step 3: DI directional check
    # ------------------------------------------------------------------
    plus_di = float(row.get("plus_di", np.nan))
    minus_di = float(row.get("minus_di", np.nan))
    if pd.isna(plus_di) or pd.isna(minus_di):
        return 0

    # DI crossover entry (optional)
    if p["di_crossover_entry"] and i >= 1:
        prev_row = df.iloc[i - 1]
        prev_plus_di = float(prev_row.get("plus_di", np.nan))
        prev_minus_di = float(prev_row.get("minus_di", np.nan))

        if pd.isna(prev_plus_di) or pd.isna(prev_minus_di):
            return 0

        # Long: +DI just crossed above -DI
        long_crossover = (prev_plus_di <= prev_minus_di) and (plus_di > minus_di)
        # Short: -DI just crossed above +DI
        short_crossover = (prev_minus_di <= prev_plus_di) and (minus_di > plus_di)

        if long_crossover:
            direction = 1
        elif short_crossover:
            direction = -1
        else:
            return 0  # no fresh crossover
    else:
        # DI dominance only (no crossover requirement)
        if plus_di > minus_di:
            direction = 1
        elif minus_di > plus_di:
            direction = -1
        else:
            return 0

    # ------------------------------------------------------------------
    # Step 4: DI separation check
    # ------------------------------------------------------------------
    separation = abs(plus_di - minus_di)
    if separation < p["di_separation_min"]:
        return 0  # DI lines too close - no clear direction

    # ------------------------------------------------------------------
    # Step 5: EMA trend filter (optional)
    # ------------------------------------------------------------------
    if p["use_ema_filter"]:
        ema_col = _ema_col(p["ema_trend_period"])
        ema_val = float(row.get(ema_col, np.nan))
        if pd.isna(ema_val):
            return 0

        if direction == 1 and close_i <= ema_val:
            return 0  # Long: price must be above EMA
        if direction == -1 and close_i >= ema_val:
            return 0  # Short: price must be below EMA

    # ------------------------------------------------------------------
    # Step 6: Volume confirmation (optional)
    # ------------------------------------------------------------------
    if p["require_volume_confirmation"]:
        vol_ratio = float(row.get("vol_ratio", np.nan))
        if pd.isna(vol_ratio):
            return 0
        if vol_ratio < p["volume_ratio_min"]:
            return 0  # volume not strong enough

    # ------------------------------------------------------------------
    # Entry: return direction (engine handles SL/TP from params)
    # ------------------------------------------------------------------
    return direction


# ---------------------------------------------------------------------------
# Internal: lazy indicator computation
# ---------------------------------------------------------------------------

# Cache keyed by the id of the underlying numpy array backing the DataFrame.
# Because ``df.iloc[:i+1]`` slices share the same ``.values.base`` we can
# detect that we have already computed indicators and avoid O(n^2) work.
_indicator_cache: set = set()


def _ensure_indicators(df: pd.DataFrame, params: dict) -> None:
    """Compute indicators on *df* if not already present."""
    # Fast path: check if columns already exist
    if "adx" in df.columns and "atr" in df.columns:
        if params["use_ema_filter"]:
            ema_col = _ema_col(params["ema_trend_period"])
            if ema_col not in df.columns:
                pass  # need to compute
            else:
                return
        else:
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

    compute_adx(df, period=params["adx_period"])
    compute_atr(df, period=params["atr_period"], name="atr")

    if params["use_ema_filter"]:
        compute_ema(df, period=params["ema_trend_period"], column="close")

    if params.get("require_volume_confirmation", False):
        compute_volume_ratio(df, period=20)


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
    """Run a complete backtest of the ADX + DMI strategy.

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
    from strategiestoTest.core.engine import BacktestEngine

    p = _resolve_params(params)

    config = StrategyConfig(
        name="adx_dmi",
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

    ap = argparse.ArgumentParser(description="ADX + DMI Trend Following Backtest")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--adx-period", type=int, default=14)
    ap.add_argument("--adx-threshold", type=float, default=25.0)
    ap.add_argument("--adx-rising-bars", type=int, default=2)
    ap.add_argument("--adx-extreme", type=float, default=40.0)
    ap.add_argument("--di-separation", type=float, default=5.0)
    ap.add_argument("--no-crossover", action="store_true",
                    help="Disable DI crossover entry requirement")
    ap.add_argument("--no-ema", action="store_true",
                    help="Disable EMA trend filter")
    ap.add_argument("--sl-atr", type=float, default=2.0)
    ap.add_argument("--tp-atr", type=float, default=4.0)
    args = ap.parse_args()

    overrides = {
        "adx_period": args.adx_period,
        "adx_threshold": args.adx_threshold,
        "adx_rising_bars": args.adx_rising_bars,
        "adx_extreme": args.adx_extreme,
        "di_separation_min": args.di_separation,
        "sl_atr_mult": args.sl_atr,
        "tp_atr_mult": args.tp_atr,
    }
    if args.no_crossover:
        overrides["di_crossover_entry"] = False
    if args.no_ema:
        overrides["use_ema_filter"] = False

    result = run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_capital=args.capital,
        params=overrides,
    )

    print(f"\n=== ADX + DMI [{args.symbol} {args.timeframe}] ===")
    print(f"Total trades : {result.total_trades}")
    print(f"Win rate     : {result.win_rate_pct:.1f}%")
