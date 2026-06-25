"""
Strategy: Asian Session Breakout.

Trade breakouts of the Asian session range during London/NY sessions.
The Asian session (00:00-08:00 UTC) typically consolidates. When price breaks
this range during London (08:00-16:00 UTC) or NY (13:00-21:00 UTC), it often
continues in the breakout direction.

Uses ``BacktestEngine.run(signal_fn, params)`` API.
"""

from __future__ import annotations

import datetime as _dt
from typing import Union

import numpy as np
import pandas as pd

from strategiestoTest.core.indicators import compute_adx, compute_atr

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    # Session times (UTC)
    "asian_start_hour": 0,       # 00:00 UTC
    "asian_end_hour": 8,         # 08:00 UTC
    "london_start_hour": 8,      # 08:00 UTC
    "london_end_hour": 16,       # 16:00 UTC
    "ny_start_hour": 13,         # 13:00 UTC
    "ny_end_hour": 21,           # 21:00 UTC

    # Trade sessions: which sessions allow entries after asian range is set
    "trade_sessions": ["london", "ny"],

    # Range filters
    "min_range_pips": 15,        # minimum asian range to trade
    "max_range_pips": 80,        # maximum asian range

    # Entry rules
    "breakout_buffer_pips": 2,   # price must close ABOVE high + buffer or BELOW low - buffer
    "require_close_above": True, # require a full bar CLOSE above/below, not just a wick
    "entry_delay_bars": 0,       # wait N bars after breakout before entering (0 = immediate)

    # Filters
    "atr_period": 14,
    "adx_min": 20,               # minimum ADX (avoid ranging markets)
    "max_spread_pips": 5.0,
    "avoid_fomc_days": False,    # skip FOMC/Fed days
    "avoid_monday": True,        # skip Monday (asian range may be incomplete)
    "avoid_friday": True,        # skip Friday afternoon

    # Trade management
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.0,
    "tp_range_mult": 2.0,        # alternative: TP = range_size * this multiplier
    "use_range_tp": True,        # if True, TP = entry +/- range_size * tp_range_mult
    "trailing_activation_r": 1.0,
    "trailing_distance_r": 0.5,
    "time_exit_hour": 20,        # close all positions at this hour UTC (0 = disabled)
    "partial_tp_pct": 0.5,       # close 50% at 1R, let rest run (0 = disabled)
}

# ---------------------------------------------------------------------------
# Optimisation parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE: dict = {
    "min_range_pips": [10, 15, 20, 25],
    "max_range_pips": [60, 80, 100],
    "breakout_buffer_pips": [0, 2, 5],
    "entry_delay_bars": [0, 1],
    "adx_min": [15, 20, 25],
    "sl_atr_mult": [1.0, 1.5, 2.0],
    "tp_range_mult": [1.5, 2.0, 2.5, 3.0],
    "use_range_tp": [True, False],
    "trade_sessions": [["london"], ["london", "ny"]],
    "avoid_monday": [True, False],
    "avoid_friday": [True, False],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_params(params: dict | None) -> dict:
    """Merge user params with defaults, returning a resolved dict."""
    resolved = dict(DEFAULT_PARAMS)
    if params:
        resolved.update(params)
    return resolved


def _guess_pip_size(close_price: float) -> float:
    """Heuristic pip size based on price magnitude.

    - Price >= 50 (e.g. XAUUSD ~2600, indices): pip = 0.01
    - Price ~ 1 (most forex): pip = 0.0001
    """
    if close_price >= 50:
        return 0.01
    return 0.0001


# ---------------------------------------------------------------------------
# prepare_data - compute indicators and session columns once
# ---------------------------------------------------------------------------


def prepare_data(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Compute ATR, ADX, and add hour/date columns for session filtering.

    Called once before running the backtest.  Modifies *df* in-place and
    also returns it for chaining.

    Columns added:
      - ``atr``
      - ``adx``
      - ``hour_utc``: hour of the bar's datetime (0-23)
      - ``date_utc``: date of the bar's datetime
    """
    p = _resolve_params(params)

    compute_atr(df, period=p["atr_period"], name="atr")
    compute_adx(df, period=p["atr_period"])

    if "datetime" in df.columns:
        df["hour_utc"] = df["datetime"].dt.hour
        df["date_utc"] = df["datetime"].dt.date

    return df


# ---------------------------------------------------------------------------
# Stateful strategy class
# ---------------------------------------------------------------------------


class AsianBreakoutStrategy:
    """Stateful strategy that tracks the Asian session range per day.

    The engine calls ``generate_signal`` at every bar.  This class maintains
    state across calls to track today's Asian range and whether we have
    already entered a trade today.
    """

    def __init__(self, params: dict):
        self.params = params
        self._today_asian_high: float | None = None
        self._today_asian_low: float | None = None
        self._today_asian_date = None  # date object for the current range
        self._entered_today: bool = False
        self._breakout_bar: int = -1
        self._breakout_direction: int = 0

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _get_session(self, hour: int) -> str:
        """Return the session name for a given UTC hour.

        Returns one of ``"asian"``, ``"london"``, ``"ny"``, ``"closed"``.
        """
        p = self.params
        if p["asian_start_hour"] <= hour < p["asian_end_hour"]:
            return "asian"
        if p["london_start_hour"] <= hour < p["london_end_hour"]:
            return "london"
        if p["ny_start_hour"] <= hour < p["ny_end_hour"]:
            return "ny"
        return "closed"

    def _is_trade_session(self, session: str) -> bool:
        """Check if *session* is configured for trade entries."""
        return session in self.params["trade_sessions"]

    # ------------------------------------------------------------------
    # Day-of-week filters
    # ------------------------------------------------------------------

    def _check_day_filters(self, dt) -> bool:
        """Return False if the day is excluded by Monday/Friday filters.

        *dt* can be a ``datetime``, ``date``, or ``Timestamp``.
        """
        p = self.params
        # weekday: Monday=0, Sunday=6
        try:
            weekday = dt.weekday()
        except AttributeError:
            weekday = dt.weekday()

        if p["avoid_monday"] and weekday == 0:
            return False
        if p["avoid_friday"] and weekday == 4:
            return False

        return True

    # ------------------------------------------------------------------
    # Asian range computation (fallback when not tracked live)
    # ------------------------------------------------------------------

    def _compute_asian_range(
        self, df: pd.DataFrame, i: int
    ) -> tuple[float, float] | None:
        """Compute today's Asian session range by scanning bars 0..i.

        Used as a fallback when we enter London/NY without having tracked
        the Asian session live (e.g. data starts mid-day).

        Returns ``(asian_high, asian_low)`` or ``None`` if insufficient bars.
        """
        if i < 0:
            return None

        p = self.params
        bar_date = df["date_utc"].iloc[i]
        asian_start = p["asian_start_hour"]
        asian_end = p["asian_end_hour"]

        highs: list[float] = []
        lows: list[float] = []

        # Scan backward from bar i to find today's Asian session bars
        for j in range(i, -1, -1):
            row_date = df["date_utc"].iloc[j]
            row_hour = df["hour_utc"].iloc[j]

            if row_date != bar_date:
                break  # moved to previous day

            if asian_start <= row_hour < asian_end:
                highs.append(float(df["high"].iloc[j]))
                lows.append(float(df["low"].iloc[j]))

        if not highs:
            return None

        return max(highs), min(lows)

    # ------------------------------------------------------------------
    # Core signal generation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        df: pd.DataFrame,
        i: int,
        params: dict | None = None,
    ) -> int | dict:
        """Generate entry signal at bar *i*.

        Called by the engine at every bar with ``df.iloc[:i+1]``.
        The ``params`` argument is accepted for compatibility but ignored;
        ``self.params`` is used instead.
        """
        p = self.params

        # Warmup guard: need enough bars for indicators to be valid
        if i < p["atr_period"] + 5:
            return 0

        # ------------------------------------------------------------------
        # Current bar data
        # ------------------------------------------------------------------
        row = df.iloc[i]
        bar_dt = row["datetime"]
        bar_date = row["date_utc"]
        bar_hour = int(row["hour_utc"])
        close_i = float(row["close"])
        high_i = float(row["high"])
        low_i = float(row["low"])

        # ------------------------------------------------------------------
        # Indicators
        # ------------------------------------------------------------------
        atr_i = float(row.get("atr", np.nan))
        adx_i = float(row.get("adx", np.nan))

        if pd.isna(atr_i) or pd.isna(adx_i) or atr_i <= 0:
            return 0

        # ------------------------------------------------------------------
        # Session detection
        # ------------------------------------------------------------------
        session = self._get_session(bar_hour)

        # ------------------------------------------------------------------
        # Reset state on new UTC day
        # ------------------------------------------------------------------
        if self._today_asian_date != bar_date:
            self._today_asian_high = None
            self._today_asian_low = None
            self._today_asian_date = bar_date
            self._entered_today = False
            self._breakout_bar = -1
            self._breakout_direction = 0

        # ==================================================================
        # Phase 1: Track Asian Range (00:00-07:59 UTC)
        # ==================================================================
        if session == "asian":
            if self._today_asian_high is None:
                self._today_asian_high = high_i
                self._today_asian_low = low_i
            else:
                self._today_asian_high = max(self._today_asian_high, high_i)
                self._today_asian_low = min(self._today_asian_low, low_i)
            return 0

        # ==================================================================
        # Outside all trading sessions: skip
        # ==================================================================
        if session == "closed":
            return 0

        # ==================================================================
        # Day-of-week filters (applied before any trade logic)
        # ==================================================================
        if not self._check_day_filters(bar_dt):
            return 0

        # ==================================================================
        # ADX filter
        # ==================================================================
        if adx_i < p["adx_min"]:
            return 0

        # ==================================================================
        # Already entered a trade today
        # ==================================================================
        if self._entered_today:
            return 0

        # ==================================================================
        # Compute or retrieve today's Asian range
        # ==================================================================
        if self._today_asian_high is None or self._today_asian_low is None:
            asian_range = self._compute_asian_range(df, i)
            if asian_range is None:
                return 0
            self._today_asian_high, self._today_asian_low = asian_range

        asian_high = self._today_asian_high
        asian_low = self._today_asian_low
        pip_size = _guess_pip_size(close_i)
        asian_range_pips = (asian_high - asian_low) / pip_size

        # ==================================================================
        # Range validation (min/max)
        # ==================================================================
        if asian_range_pips < p["min_range_pips"]:
            return 0
        if asian_range_pips > p["max_range_pips"]:
            return 0

        # ==================================================================
        # Trade session check
        # ==================================================================
        if not self._is_trade_session(session):
            return 0

        # ==================================================================
        # Phase 2: Monitor Breakout
        # ==================================================================
        buffer_dist = p["breakout_buffer_pips"] * pip_size
        breakout_high = asian_high + buffer_dist
        breakout_low = asian_low - buffer_dist

        if p["require_close_above"]:
            long_breakout = close_i > breakout_high
            short_breakout = close_i < breakout_low
        else:
            long_breakout = high_i > breakout_high
            short_breakout = low_i < breakout_low

        if not long_breakout and not short_breakout:
            # If we were tracking a delayed entry but breakout no longer
            # valid, reset the tracking
            self._breakout_bar = -1
            self._breakout_direction = 0
            return 0

        direction = 1 if long_breakout else -1

        # ==================================================================
        # Entry delay: wait N bars after breakout before entering
        # ==================================================================
        delay = p["entry_delay_bars"]
        if delay > 0:
            if self._breakout_bar < 0 or self._breakout_direction != direction:
                # First bar of this breakout - start tracking
                self._breakout_bar = i
                self._breakout_direction = direction
                return 0

            bars_since_breakout = i - self._breakout_bar
            if bars_since_breakout < delay:
                return 0

            # Delay elapsed - reset tracking
            self._breakout_bar = -1
            self._breakout_direction = 0

        # ==================================================================
        # Phase 3: Entry
        # ==================================================================
        self._entered_today = True

        # -- Stop-loss --
        # Opposite side of Asian range, but minimum sl_atr_mult * ATR
        sl_atr_dist = p["sl_atr_mult"] * atr_i

        if direction == 1:
            sl = asian_low
            if close_i - sl < sl_atr_dist:
                sl = close_i - sl_atr_dist
        else:
            sl = asian_high
            if sl - close_i < sl_atr_dist:
                sl = close_i + sl_atr_dist

        # -- Take-profit --
        if p["use_range_tp"]:
            range_dist = asian_range_pips * pip_size * p["tp_range_mult"]
            if direction == 1:
                tp = close_i + range_dist
            else:
                tp = close_i - range_dist
        else:
            tp_dist = p["tp_atr_mult"] * atr_i
            if direction == 1:
                tp = close_i + tp_dist
            else:
                tp = close_i - tp_dist

        return {
            "direction": direction,
            "sl": round(float(sl), 8),
            "tp": round(float(tp), 8),
        }


# ---------------------------------------------------------------------------
# Module-level signal function (bridge for engine compatibility)
# ---------------------------------------------------------------------------

_strategy_instance: AsianBreakoutStrategy | None = None


def generate_signal(
    df: pd.DataFrame,
    i: int,
    params: dict | None = None,
) -> int | dict:
    """Generate entry signal at bar *i*.

    Delegates to the module-level ``AsianBreakoutStrategy`` instance.
    The instance is created on first call within a backtest run.

    Parameters
    ----------
    df : pd.DataFrame
        Data up to and including bar *i*  (``df.iloc[:i+1]``).
    i : int
        Current bar index.
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
    global _strategy_instance
    if _strategy_instance is None:
        p = _resolve_params(params)
        _strategy_instance = AsianBreakoutStrategy(p)
    return _strategy_instance.generate_signal(df, i, params)


def _reset_strategy() -> None:
    """Reset the module-level strategy instance (called before each run)."""
    global _strategy_instance
    _strategy_instance = None


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
    """Run a complete backtest of the Asian Breakout strategy.

    Loads intraday data, prepares indicators and session columns, and
    runs the bar-by-bar simulation.

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

    # Reset strategy state for a fresh run
    _reset_strategy()

    # Load data
    df = load_data(symbol, timeframe)
    if len(df) == 0:
        raise RuntimeError(f"No data for {symbol} {timeframe}")

    # Pre-compute indicators and session columns
    prepare_data(df, params=p)

    config = StrategyConfig(
        name="asian_breakout",
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

    ap = argparse.ArgumentParser(description="Asian Breakout Backtest")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--min-range", type=float, default=15)
    ap.add_argument("--max-range", type=float, default=80)
    ap.add_argument("--buffer", type=float, default=2)
    ap.add_argument("--adx-min", type=float, default=20)
    args = ap.parse_args()

    result = run(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_capital=args.capital,
        params={
            "min_range_pips": args.min_range,
            "max_range_pips": args.max_range,
            "breakout_buffer_pips": args.buffer,
            "adx_min": args.adx_min,
        },
    )
    print(result.summary())
