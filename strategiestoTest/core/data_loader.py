from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAME_MAP: dict[str, int] = {}
"""Populated lazily when MT5 is imported."""

# Symbol categories for pip-size auto-detection
_JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"}
_XAU_SYMBOLS = {"XAUUSD", "GOLD"}
_INDEX_SYMBOLS = {"US30", "US100", "US500", "GER40", "UK100", "JPN225"}
_CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"}

# MT5 credentials -- prefer environment, fall back to defaults
_MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
_MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
_MT5_SERVER = os.getenv("MT5_SERVER", "FusionMarkets-Demo")

# Project data root
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "historical"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_pip_size(symbol: str) -> float:
    """Return the size of one pip for *symbol*.

    ============ =======
    Category      Pip
    ============ =======
    Forex (most)  0.0001
    JPY pairs     0.01
    XAUUSD        0.01
    Indices       1.0
    Crypto        1.0
    ============ =======
    """
    symbol = symbol.upper()

    if symbol in _XAU_SYMBOLS:
        return 0.01
    if symbol in _JPY_PAIRS:
        return 0.01
    if symbol in _INDEX_SYMBOLS:
        return 1.0
    if symbol in _CRYPTO_SYMBOLS:
        return 1.0
    # Default: standard forex
    return 0.0001


def get_pip_value(symbol: str) -> float:
    """Return the notional value of one pip per standard lot.

    ============ ==========
    Category      Pip Value
    ============ ==========
    Forex         10.0 (units of quote currency)
    XAUUSD        1.0
    Indices       1.0
    Crypto        1.0
    ============ ==========
    """
    symbol = symbol.upper()

    if symbol in _XAU_SYMBOLS:
        return 1.0
    if symbol in _INDEX_SYMBOLS:
        return 1.0
    if symbol in _CRYPTO_SYMBOLS:
        return 1.0
    # Default: standard forex (1 lot = 100 000 units, 1 pip = 10 quote-currency units)
    return 10.0


def get_available_symbols() -> list[str]:
    """Scan ``data/historical/`` and return deduplicated, sorted symbol names."""
    symbols: set[str] = set()

    if not _DATA_DIR.exists():
        return []

    for entry in _DATA_DIR.iterdir():
        if entry.is_file() and entry.suffix == ".csv":
            # Flat file: eurusd_M15_1y.csv -> "EURUSD"
            stem = entry.stem
            parts = stem.split("_")
            if parts:
                symbols.add(parts[0].upper())
        elif entry.is_dir():
            # Subdirectory: eurusd/  -> "EURUSD"
            symbols.add(entry.name.upper())

    return sorted(symbols)


# ---------------------------------------------------------------------------
# Core data-loading
# ---------------------------------------------------------------------------

def load_data(
    symbol: str,
    timeframe: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    force_download: bool = False,
) -> pd.DataFrame:
    """Load OHLCV data for *symbol* at *timeframe*.

    Resolution order:
    1. If ``force_download=False``, try to read from local CSV(s).
    2. Otherwise (or if local data is missing) download from MT5.

    Parameters
    ----------
    symbol : str
        Trading symbol, e.g. ``"EURUSD"``.
    timeframe : str
        Timeframe string: ``"M1"``, ``"M5"``, ``"M15"``, ``"H1"``, ``"H4"``, ``"D1"``.
    start_date : str, optional
        Start date in ``"YYYY-MM-DD"`` format.  Default is 12 months ago.
    end_date : str, optional
        End date in ``"YYYY-MM-DD"`` format.  Default is today.
    force_download : bool
        If ``True``, skip local cache and re-download from MT5.

    Returns
    -------
    pd.DataFrame
        Columns: ``datetime`` (datetime64[ns, UTC]), ``open``, ``high``, ``low``,
        ``close``, ``tick_volume`` (optional), ``spread`` (optional).
    """
    symbol = symbol.upper()
    timeframe = timeframe.upper()

    # --- resolve date range ---
    end_dt = _parse_date(end_date) if end_date else datetime.now(timezone.utc)
    start_dt = _parse_date(start_date) if start_date else (end_dt - timedelta(days=365))

    s_start = start_dt.strftime("%Y-%m-%d")
    s_end = end_dt.strftime("%Y-%m-%d")

    # --- 1. Try flat yearly file ---
    flat_path = _DATA_DIR / f"{symbol.lower()}_{timeframe}_1y.csv"
    if flat_path.exists() and not force_download:
        logger.info(f"[{symbol}] Loading flat file: {flat_path}")
        df = _read_csv(flat_path)
        df = _filter_date_range(df, start_dt, end_dt)
        if len(df) > 0:
            return df
        logger.warning(f"[{symbol}] Flat file is empty after date filter, trying monthly files...")

    # --- 2. Try monthly files in subdirectory ---
    subdir = _DATA_DIR / symbol.lower()
    if subdir.exists() and not force_download:
        monthly_paths = sorted(subdir.glob(f"{symbol.lower()}_{timeframe}_*.csv"))
        if monthly_paths:
            logger.info(f"[{symbol}] Loading {len(monthly_paths)} monthly file(s) from {subdir}")
            frames = [_read_csv(p) for p in monthly_paths]
            df = pd.concat(frames, ignore_index=True)
            df = df.drop_duplicates(subset="datetime").sort_values("datetime").reset_index(drop=True)
            df = _filter_date_range(df, start_dt, end_dt)
            if len(df) > 0:
                return df

    # --- 3. Download from MT5 ---
    logger.info(f"[{symbol}] Downloading {timeframe} from MT5 ({s_start} to {s_end})...")
    df = _download_mt5(symbol, timeframe, start_dt, end_dt)

    # Cache to flat yearly file for next time
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(flat_path, index=False)
    logger.info(f"[{symbol}] Cached {len(df)} rows to {flat_path}")

    df = _filter_date_range(df, start_dt, end_dt)
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` string into a timezone-aware UTC datetime."""
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV and standardise its columns."""
    df = pd.read_csv(path)

    # Normalise datetime column
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    elif "time" in df.columns:
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.drop(columns=["time"], inplace=True)

    # Normalise volume column name
    if "real_volume" in df.columns and "tick_volume" not in df.columns:
        df.rename(columns={"real_volume": "tick_volume"}, inplace=True)

    # Ensure standard column order
    wanted = ["datetime", "open", "high", "low", "close"]
    extras = [c for c in ["tick_volume", "spread"] if c in df.columns]
    df = df[wanted + extras + [c for c in df.columns if c not in wanted and c not in extras]]

    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _filter_date_range(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    """Keep only rows where ``start <= datetime <= end``."""
    if df.empty:
        return df
    # Ensure the datetime column is tz-aware for comparison
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize("UTC")
    mask = (df["datetime"] >= start) & (df["datetime"] <= end)
    return df.loc[mask].reset_index(drop=True)


def _download_mt5(
    symbol: str,
    timeframe: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    """Connect to MT5, download rates, return a standardised DataFrame."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise ImportError(
            "MetaTrader5 package is required for live data download. "
            "Install it with: pip install MetaTrader5"
        )

    # Lazy-init the timeframe map
    if not TIMEFRAME_MAP:
        _TIMEFRAME_ATTRS = [
            "TIMEFRAME_M1", "TIMEFRAME_M5", "TIMEFRAME_M15", "TIMEFRAME_M30",
            "TIMEFRAME_H1", "TIMEFRAME_H4", "TIMEFRAME_D1", "TIMEFRAME_W1",
        ]
        for attr in _TIMEFRAME_ATTRS:
            if hasattr(mt5, attr):
                key = attr.replace("TIMEFRAME_", "")
                TIMEFRAME_MAP[key] = getattr(mt5, attr)

    tf_const = TIMEFRAME_MAP.get(timeframe)
    if tf_const is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. Supported: {sorted(TIMEFRAME_MAP.keys())}"
        )

    # Connect
    if not mt5.initialize(login=_MT5_LOGIN, password=_MT5_PASSWORD, server=_MT5_SERVER):
        error = mt5.last_error()
        mt5.shutdown()
        raise ConnectionError(f"MT5 initialize() failed: {error}")

    try:
        # Extend start by a few days so we don't miss partial bars
        fetch_start = start_dt - timedelta(days=7)
        fetch_end = end_dt + timedelta(days=1)

        rates = mt5.copy_rates_range(symbol, tf_const, fetch_start, fetch_end)

        if rates is None or len(rates) == 0:
            error = mt5.last_error()
            raise ValueError(f"MT5 returned no data for {symbol} {timeframe}: {error}")

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)

        # Rename to standard column names
        rename_map = {}
        if "real_volume" in df.columns:
            rename_map["real_volume"] = "tick_volume"
        df.rename(columns=rename_map, inplace=True)

        wanted = ["datetime", "open", "high", "low", "close"]
        extras = [c for c in ["tick_volume", "spread"] if c in df.columns]
        df = df[wanted + extras + [c for c in df.columns if c not in wanted and c not in extras]]

        df.sort_values("datetime", inplace=True)
        df.reset_index(drop=True, inplace=True)

        logger.info(f"[{symbol}] Downloaded {len(df)} rows from MT5")
        return df

    finally:
        mt5.shutdown()
