"""Pivot point computation module - Classic, Camarilla, Woodie, Fibonacci, CPR.

Supports daily, weekly, and monthly pivot levels with a unified PivotLevels
dataclass. Provides helpers for nearest support/resistance queries and
alignment of higher-timeframe pivot levels onto intraday bars.

Key exports:
    PivotLevels      -- dataclass holding all computed pivot levels
    compute_classic_pivots   -- classic floor trader pivots
    compute_camarilla_pivots -- Camarilla levels with R4/S4
    compute_woodie_pivots    -- Woodie pivot levels
    compute_fibonacci_pivots -- Fibonacci retracement-based pivots
    compute_cpr              -- Central Pivot Range (TC/BC)
    compute_pivots_from_daily -- compute all pivot types from a D1 DataFrame
    resample_to_weekly       -- resample D1 candles to weekly
    resample_to_monthly      -- resample D1 candles to monthly
    align_pivots_to_intraday -- merge-asof pivot levels onto intraday bars
"""

from src.pivots.types import (
    PivotLevels,
    compute_classic_pivots,
    compute_camarilla_pivots,
    compute_woodie_pivots,
    compute_fibonacci_pivots,
    compute_cpr,
    compute_pivots_from_daily,
    resample_to_weekly,
    resample_to_monthly,
    align_pivots_to_intraday,
)
