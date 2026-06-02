from __future__ import annotations

import pandas as pd


def export_mt5_to_csv(
    symbol: str, timeframe: str, start_date: str, end_date: str, output_path: str
) -> str:
    """Export OHLCV data from MetaTrader 5 to a CSV file for backtesting.

    This function documents the process of exporting data from MT5.
    It does NOT import MT5 at runtime - use it as a reference.

    Instructions
    ------------
    1. Install MetaTrader 5 Python package: ``pip install MetaTrader5``
    2. Ensure MT5 terminal is running and logged in to your account.
    3. Call this function or run the equivalent code:

    .. code-block:: python

        import MetaTrader5 as mt5
        from datetime import datetime

        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

        rates = mt5.copy_rates_range(
            symbol,                          # e.g. "EURUSD"
            tf_map[timeframe.upper()],       # e.g. mt5.TIMEFRAME_M15
            datetime.strptime(start_date, "%Y-%m-%d"),
            datetime.strptime(end_date, "%Y-%m-%d"),
        )

        if rates is None or len(rates) == 0:
            raise ValueError(f"No data returned: {mt5.last_error()}")

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"real_volume": "tick_volume"})
        df = df[["datetime", "open", "high", "low", "close", "tick_volume", "spread"]]
        df.to_csv(output_path, index=False)
        mt5.shutdown()

    Parameters
    ----------
    symbol : str
        Trading symbol, e.g. "EURUSD".
    timeframe : str
        Timeframe string: "M1", "M5", "M15", "H1", "H4", "D1".
    start_date : str
        Start date in "YYYY-MM-DD" format.
    end_date : str
        End date in "YYYY-MM-DD" format.
    output_path : str
        Path for the output CSV file.

    Returns
    -------
    str
        The output path that was (or would be) written to.

    Raises
    ------
    NotImplementedError
        Always raised with the documentation above.
    """
    raise NotImplementedError(
        "export_mt5_to_csv is a reference function. "
        "See the docstring above for MT5 export instructions. "
        f"Would export {symbol} ({timeframe}) from {start_date} to {end_date} "
        f"into {output_path}."
    )


class HistoricalDataSource:
    """Reads OHLCV data from a CSV file, replacing ``src/mt5/bridge.py`` for backtesting.

    This class mimics the MT5 bridge interface so the existing executor and strategy
    code can run against historical data without a live MT5 connection.

    Parameters
    ----------
    csv_path : str
        Path to a CSV file with columns: datetime, open, high, low, close,
        tick_volume, spread.
    symbol : str
        Trading symbol name (default "EURUSD"). Used to auto-detect point/digits.
    initial_balance : float
        Starting account balance for simulation (default 10 000).
    spread_pips : float
        Default spread in pips, used when the CSV has no spread column (default 1.0).
    point : float
        Pip value. Auto-detected from symbol if not provided.
    digits : int
        Decimal places for prices. Auto-detected from symbol if not provided.
    """

    def __init__(
        self,
        csv_path: str,
        symbol: str = "EURUSD",
        initial_balance: float = 10000.0,
        spread_pips: float = 1.0,
        point: float = 0.0,
        digits: int = 0,
    ) -> None:
        self.csv_path = csv_path
        self.symbol = symbol.upper()
        self.initial_balance = initial_balance
        self.spread_pips = spread_pips

        # Auto-detect symbol parameters
        if point > 0:
            self._point = point
        elif "JPY" in self.symbol:
            self._point = 0.001
        elif self.symbol == "XAUUSD":
            self._point = 0.01
        else:
            self._point = 0.00001

        if digits > 0:
            self._digits = digits
        elif "JPY" in self.symbol:
            self._digits = 3
        elif self.symbol == "XAUUSD":
            self._digits = 2
        else:
            self._digits = 5

        # Mutable state (set externally by executor / backtest runner)
        self._balance: float = initial_balance
        self._equity: float = initial_balance

        self._df: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self) -> pd.DataFrame:
        """Load and parse the CSV file.

        Returns
        -------
        pd.DataFrame
            Sorted by datetime ascending. Columns include at least
            datetime, open, high, low, close, tick_volume, spread.
        """
        df = pd.read_csv(self.csv_path)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime", ascending=True).reset_index(drop=True)
        self._df = df
        return df

    # ------------------------------------------------------------------
    # Rate access
    # ------------------------------------------------------------------

    def get_rates(self, start_idx: int, count: int) -> pd.DataFrame:
        """Return ``count`` rows starting from ``start_idx``.

        Parameters
        ----------
        start_idx : int
            Starting bar index (0-based).
        count : int
            Number of bars to return.

        Returns
        -------
        pd.DataFrame
            Slice of the loaded DataFrame.

        Raises
        ------
        IndexError
            If the requested range is out of bounds.
        """
        if self._df is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        if start_idx < 0 or start_idx >= len(self._df):
            raise IndexError(
                f"start_idx {start_idx} out of bounds [0, {len(self._df) - 1}]"
            )
        end_idx = start_idx + count
        if end_idx > len(self._df):
            raise IndexError(
                f"end_idx {end_idx} out of bounds (max {len(self._df)})"
            )
        return self._df.iloc[start_idx:end_idx]

    # ------------------------------------------------------------------
    # Price / tick access
    # ------------------------------------------------------------------

    def get_current_price(self, idx: int) -> float:
        """Return the close price at the given bar index.

        Parameters
        ----------
        idx : int
            Bar index.

        Returns
        -------
        float
            Close price.
        """
        if self._df is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")
        return float(self._df.iloc[idx]["close"])

    def get_current_tick(self, idx: int) -> dict[str, object]:
        """Return a simulated tick dict for the bar at ``idx``.

        Bid/ask are derived from close +/- half the spread (in points, not pips).

        Parameters
        ----------
        idx : int
            Bar index.

        Returns
        -------
        dict
            ``{"bid": float, "ask": float, "time": datetime}``
        """
        if self._df is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        row = self._df.iloc[idx]
        close = float(row["close"])
        spread_points: float = (
            float(row["spread"]) * self._point
            if "spread" in self._df.columns and pd.notna(row.get("spread"))
            else self.spread_pips * self._point
        )
        half_spread = spread_points / 2.0

        return {
            "bid": round(close - half_spread, self._digits),
            "ask": round(close + half_spread, self._digits),
            "time": row["datetime"],
        }

    # ------------------------------------------------------------------
    # Symbol / account info (MT5-compatible shapes)
    # ------------------------------------------------------------------

    def get_symbol_info(self) -> dict[str, object]:
        """Return a dict mimicking ``mt5.symbol_info()``.

        Returns
        -------
        dict
            Keys: spread, point, digits, trade_tick_value.
        """
        # In MT5, 1 pip = 10 points for most symbols (1.0 pip → 10 points)
        spread_in_points = int(self.spread_pips * 10)
        return {
            "spread": spread_in_points,
            "point": self._point,
            "digits": self._digits,
            "trade_tick_value": 1.0,
        }

    def get_account_info(self) -> dict[str, object]:
        """Return a dict mimicking ``mt5.account_info()``.

        ``balance`` and ``equity`` are mutable - updated externally by the
        executor / backtest runner as trades open and close.

        Returns
        -------
        dict
            Keys: balance, equity, currency.
        """
        return {
            "balance": self._balance,
            "equity": self._equity,
            "currency": "USD",
        }

    # ------------------------------------------------------------------
    # Market state
    # ------------------------------------------------------------------

    def is_market_open(self, idx: int) -> bool:  # noqa: ARG002
        """Always return True - during backtesting the market is always "open".

        Parameters
        ----------
        idx : int
            Bar index (unused, kept for interface compatibility).

        Returns
        -------
        bool
            Always ``True``.
        """
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_bar_count(self) -> int:
        """Return the total number of bars loaded.

        Returns
        -------
        int
            Number of rows in the DataFrame.
        """
        if self._df is None:
            return 0
        return len(self._df)

    def get_dataframe(self) -> pd.DataFrame:
        """Return the full loaded DataFrame.

        Returns
        -------
        pd.DataFrame
            The full historical data.

        Raises
        ------
        RuntimeError
            If ``load_data()`` has not been called yet.
        """
        if self._df is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")
        return self._df

    def get_bar_datetime(self, idx: int) -> str:
        """Return the datetime string of the bar at ``idx``.

        Parameters
        ----------
        idx : int
            Bar index.

        Returns
        -------
        str
            ISO-formatted datetime string.
        """
        if self._df is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")
        return str(self._df.iloc[idx]["datetime"])
