"""Pivot point types and computation functions.

This module defines the PivotLevels dataclass and five pivot-type compute
functions: Classic, Camarilla, Woodie, Fibonacci, and Central Pivot Range
(CPR). It also provides pipeline helpers to compute pivots from daily
DataFrames, resample daily data to weekly/monthly, and align higher-
timeframe pivot levels onto intraday bars via merge-asof.

Usage example:
    from src.pivots.types import compute_classic_pivots, PivotLevels

    levels: PivotLevels = compute_classic_pivots(
        h=1.0850, l=1.0810, c=1.0835
    )
    print(levels.pp)   # ~1.0832
    print(levels.r1)   # ~1.0854
    print(levels.s1)   # ~1.0814
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PivotLevels:
    """Container for a complete set of pivot levels.

    Holds R1-R4, S1-S4, PP, and CPR-specific TC/BC fields.
    Camarilla fills R4/S4; CPR fills TC/BC and leaves R2-R3/S2-S3 as None.

    Attributes:
        pp: Pivot Point (central level).
        r1-r4: Resistance levels 1 through 4 (R4 only for Camarilla).
        s1-s4: Support levels 1 through 4 (S4 only for Camarilla).
        tc: CPR Top Central (only for CPR type).
        bc: CPR Bottom Central (only for CPR type).
    """
    pp: float
    r1: float; s1: float
    r2: float; s2: float
    r3: float; s3: float
    r4: Optional[float] = None  # Camarilla
    s4: Optional[float] = None  # Camarilla
    tc: Optional[float] = None  # CPR Top Central
    bc: Optional[float] = None  # CPR Bottom Central
    
    def to_dict(self) -> dict:
        return {k: round(v, 5) if v is not None else None for k, v in self.__dict__.items()}
    
    def all_levels(self) -> dict[str, float]:
        """Return all non-None pivot levels keyed by uppercase name (S4..R4, TC, BC)."""
        result = {}
        for name in ["s4", "s3", "s2", "s1", "pp", "r1", "r2", "r3", "r4", "tc", "bc"]:
            val = getattr(self, name, None)
            if val is not None:
                result[name.upper()] = val
        return result
    
    def nearest_support(self, price: float):
        """Find the name and value of the nearest support level below the given price."""
        best = None
        for name in ["S4", "S3", "S2", "S1", "PP"]:
            val = getattr(self, name.lower(), None)
            if val is not None and val < price:
                if best is None or val > best[1]:
                    best = (name, val)
        return best
    
    def nearest_resistance(self, price: float):
        """Find the name and value of the nearest resistance level above the given price."""
        best = None
        for name in ["R1", "R2", "R3", "R4", "PP"]:
            val = getattr(self, name.lower(), None)
            if val is not None and val > price:
                if best is None or val < best[1]:
                    best = (name, val)
        return best
    
    def distance_to_nearest_support(self, price: float):
        """Absolute distance in price units from current price to nearest support."""
        sr = self.nearest_support(price)
        return price - sr[1] if sr else None
    
    def distance_to_nearest_resistance(self, price: float):
        """Absolute distance in price units from current price to nearest resistance."""
        sr = self.nearest_resistance(price)
        return sr[1] - price if sr else None


def compute_classic_pivots(h: float, l: float, c: float) -> PivotLevels:
    """Compute Classic floor-trader pivot levels.

    Args:
        h: Previous period high.
        l: Previous period low.
        c: Previous period close.

    Returns:
        PivotLevels with PP, R1-R3, S1-S3.
    """
    pp = (h + l + c) / 3.0
    return PivotLevels(
        pp=pp,
        r1=2*pp - l, s1=2*pp - h,
        r2=pp + (h - l), s2=pp - (h - l),
        r3=h + 2*(pp - l), s3=l - 2*(h - pp),
    )


def compute_camarilla_pivots(h: float, l: float, c: float) -> PivotLevels:
    """Compute Camarilla pivot levels with extended R4/S4.

    Uses a 1.1x range multiplier distributed across 4 levels.
    Reference: Nick Scott's Camarilla Equation.

    Args:
        h: Previous period high.
        l: Previous period low.
        c: Previous period close.

    Returns:
        PivotLevels with PP, R1-R4, S1-S4.
    """
    rng = h - l
    pp = (h + l + c) / 3.0
    r4 = c + rng * 1.1 / 2
    r3 = c + rng * 1.1 / 4
    r2 = c + rng * 1.1 / 6
    r1 = c + rng * 1.1 / 12
    s1 = c - rng * 1.1 / 12
    s2 = c - rng * 1.1 / 6
    s3 = c - rng * 1.1 / 4
    s4 = c - rng * 1.1 / 2
    return PivotLevels(pp=pp, r1=r1, s1=s1, r2=r2, s2=s2, r3=r3, s3=s3, r4=r4, s4=s4)


def compute_woodie_pivots(h: float, l: float, c: float, o: float = None) -> PivotLevels:
    """Compute Woodie pivot levels.

    Differs from Classic by using (H + L + 2*C) / 4 for the pivot point,
    giving extra weight to the close.

    Args:
        h: Previous period high.
        l: Previous period low.
        c: Previous period close.
        o: Previous period open (optional, accepted but not used in calculation).

    Returns:
        PivotLevels with PP, R1-R3, S1-S3.
    """
    pp = (h + l + 2*c) / 4.0
    return PivotLevels(
        pp=pp,
        r1=2*pp - l, s1=2*pp - h,
        r2=pp + (h - l), s2=pp - (h - l),
        r3=h + 2*(pp - l), s3=l - 2*(h - pp),
    )


def compute_fibonacci_pivots(h: float, l: float, c: float) -> PivotLevels:
    """Compute Fibonacci retracement-based pivot levels.

    Uses 38.2%, 61.8%, and 100% of the previous period's range projected
    from the central pivot point.

    Args:
        h: Previous period high.
        l: Previous period low.
        c: Previous period close.

    Returns:
        PivotLevels with PP, R1-R3, S1-S3.
    """
    pp = (h + l + c) / 3.0
    rng = h - l
    r1 = pp + 0.382 * rng; s1 = pp - 0.382 * rng
    r2 = pp + 0.618 * rng; s2 = pp - 0.618 * rng
    r3 = pp + 1.000 * rng; s3 = pp - 1.000 * rng
    return PivotLevels(pp=pp, r1=r1, s1=s1, r2=r2, s2=s2, r3=r3, s3=s3)


def compute_cpr(h: float, l: float, c: float) -> PivotLevels:
    """Compute Central Pivot Range (CPR).

    CPR consists of a Top Central (TC) and Bottom Central (BC) level
    derived from the pivot point and the range midpoint. It also includes
    R1 and S1 for reference, but no R2-R3/S2-S3.

    Args:
        h: Previous period high.
        l: Previous period low.
        c: Previous period close.

    Returns:
        PivotLevels with PP, R1, S1, TC, BC. R2-R3/S2-S3 are None.
    """
    pp = (h + l + c) / 3.0
    bc_val = (h + l) / 2.0
    tc = (pp - bc_val) + pp
    r1 = 2*pp - l; s1 = 2*pp - h
    return PivotLevels(pp=pp, r1=r1, s1=s1, r2=None, s2=None, r3=None, s3=None, tc=tc, bc=bc_val)


def compute_pivots_from_daily(df_daily: pd.DataFrame, pivot_types=None):
    """Compute all requested pivot types from a daily OHLC DataFrame.

    Uses the previous day's H/L/C to calculate pivot levels for the current day.
    Columns are named `pivot_{type}_{field}` (e.g. `pivot_classic_r1`).

    Args:
        df_daily: DataFrame with datetime, high, low, close, open columns.
        pivot_types: List of pivot type names. Defaults to all 5 types.

    Returns:
        DataFrame with datetime, pivot columns, high, low, close.
    """
    if pivot_types is None:
        pivot_types = ['classic', 'camarilla', 'woodie', 'fibonacci', 'cpr']
    df = df_daily.sort_values('datetime').reset_index(drop=True).copy()
    df['ph'] = df['high'].shift(1)
    df['pl'] = df['low'].shift(1)
    df['pc'] = df['close'].shift(1)
    df['po'] = df['open'].shift(1)
    result_cols = ['datetime']
    for ptype in pivot_types:
        prefix = f'pivot_{ptype}'
        for idx in range(len(df)):
            row = df.iloc[idx]
            if pd.isna(row['ph']):
                continue
            pivots = _compute_single_set(row['ph'], row['pl'], row['pc'], row['po'], ptype)
            d = pivots.to_dict()
            for k, v in d.items():
                col = f'{prefix}_{k}'
                if col not in df.columns:
                    df[col] = np.nan
                df.at[idx, col] = v
        for k in PivotLevels.__dataclass_fields__:
            col = f'{prefix}_{k}'
            if col in df.columns:
                result_cols.append(col)
    return df[result_cols + ['high', 'low', 'close']]


def _compute_single_set(h, l, c, o, ptype):
    """Dispatch a single H/L/C/O set to the appropriate pivot compute function."""
    if ptype == 'classic':
        return compute_classic_pivots(h, l, c)
    elif ptype == 'camarilla':
        return compute_camarilla_pivots(h, l, c)
    elif ptype == 'woodie':
        return compute_woodie_pivots(h, l, c, o)
    elif ptype == 'fibonacci':
        return compute_fibonacci_pivots(h, l, c)
    elif ptype == 'cpr':
        return compute_cpr(h, l, c)
    else:
        raise ValueError(f"Unknown pivot type: {ptype}")


def resample_to_weekly(df_daily):
    """Resample daily OHLC DataFrame to weekly bars.

    Args:
        df_daily: DataFrame with datetime, open, high, low, close columns.

    Returns:
        DataFrame with weekly OHLC bars.
    """
    return df_daily.set_index('datetime').resample('W').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()


def resample_to_monthly(df_daily):
    """Resample daily OHLC DataFrame to monthly bars.

    Args:
        df_daily: DataFrame with datetime, open, high, low, close columns.

    Returns:
        DataFrame with monthly OHLC bars.
    """
    return df_daily.set_index('datetime').resample('ME').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()


def align_pivots_to_intraday(df_intraday, df_pivots_daily, pivot_type='classic'):
    """Align higher-timeframe pivot levels onto intraday bars using merge-asof.

    For each intraday bar, the most recent daily pivot row (backward direction)
    is joined. This means intraday bars use the current day's pivot levels
    computed from the previous D1 candle.

    Args:
        df_intraday: Intraday DataFrame (M15, H1, etc.) with datetime column.
        df_pivots_daily: DataFrame produced by compute_pivots_from_daily().
        pivot_type: Which pivot type's columns to align (e.g. 'classic').

    Returns:
        Merged DataFrame with intraday bars + pivot level columns.
    """
    df_intra = df_intraday.sort_values('datetime').reset_index(drop=True).copy()
    df_piv = df_pivots_daily.sort_values('datetime').reset_index(drop=True).copy()
    pivot_cols = ['datetime']
    for col in df_piv.columns:
        if col.startswith(f'pivot_{pivot_type}_'):
            pivot_cols.append(col)
    df_piv_subset = df_piv[pivot_cols]
    # Remove duplicate columns if any
    df_piv_subset = df_piv_subset.loc[:, ~df_piv_subset.columns.duplicated()]
    # Drop only rows where ALL pivot value columns are NaN (keep datetime)
    value_cols = [c for c in pivot_cols if c != 'datetime']
    df_piv_subset = df_piv_subset.dropna(subset=value_cols, how='all')
    return pd.merge_asof(df_intra, df_piv_subset, on='datetime', direction='backward')