"""Rapport de backtesting - metriques de performance detailles."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.backtest.simulated_executor import ClosedTrade, SimulatedExecutor


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class BacktestMetrics:
    """Container for all backtest performance metrics."""

    symbol: str
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float
    final_equity: float

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0

    # Profit metrics
    total_profit: float = 0.0
    total_loss: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0

    # Trade averages
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    return_pct: float = 0.0

    # Exit reason breakdown
    exit_reasons: dict = field(default_factory=dict)

    # Time-based metrics
    avg_bars_held: float = 0.0
    avg_hours_held: float = 0.0

    # Equity curve
    equity_curve: list[tuple[str, float]] = field(default_factory=list)

    # Drawdown curve
    drawdown_curve: list[tuple[str, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(dt_str: str) -> pd.Timestamp:
    """Parse a datetime string into a pandas Timestamp."""
    return pd.to_datetime(dt_str)


def _timeframe_to_minutes(timeframe: str) -> int:
    """Convert a timeframe string like 'M15' or 'H1' to minutes."""
    tf = timeframe.upper()
    if tf.startswith("M"):
        return int(tf[1:])
    elif tf == "H1":
        return 60
    elif tf == "H4":
        return 240
    elif tf == "D1":
        return 1440
    else:
        return 15  # default fallback


# ---------------------------------------------------------------------------
# BacktestReport
# ---------------------------------------------------------------------------


class BacktestReport:
    """Compute comprehensive performance metrics from backtest results."""

    def __init__(
        self,
        executor: SimulatedExecutor,
        initial_balance: float,
        symbol: str,
        start_date: str,
        end_date: str,
        equity_curve: list[tuple[str, float]] | None = None,
        timeframe: str = "M15",
    ):
        self._executor = executor
        self._initial_balance = initial_balance
        self._symbol = symbol
        self._start_date = start_date
        self._end_date = end_date
        self._equity_curve = equity_curve or []
        self._timeframe = timeframe
        self._metrics: BacktestMetrics | None = None

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def compute(self) -> BacktestMetrics:
        """Compute ALL metrics from the executor's closed trades and equity curve."""
        trades: list[ClosedTrade] = self._executor.closed_trades
        final_balance = self._executor.balance

        m = BacktestMetrics(
            symbol=self._symbol,
            start_date=self._start_date,
            end_date=self._end_date,
            initial_balance=self._initial_balance,
            final_balance=final_balance,
            final_equity=self._executor.equity,
        )

        if not trades:
            self._metrics = m
            return m

        profits = [t.profit for t in trades]

        # -- Trade statistics -------------------------------------------------
        m.total_trades = len(trades)
        m.winning_trades = sum(1 for p in profits if p > 0)
        m.losing_trades = sum(1 for p in profits if p <= 0)
        m.win_rate_pct = (m.winning_trades / m.total_trades) * 100 if m.total_trades > 0 else 0.0

        # -- Profit metrics ---------------------------------------------------
        positive = [p for p in profits if p > 0]
        negative = [p for p in profits if p <= 0]

        m.gross_profit = sum(positive)
        m.gross_loss = sum(negative)
        m.net_profit = m.gross_profit + m.gross_loss  # gross_loss is negative
        m.return_pct = (
            ((final_balance - self._initial_balance) / self._initial_balance) * 100
        )

        if m.gross_loss != 0:
            m.profit_factor = m.gross_profit / abs(m.gross_loss)
        elif m.gross_profit > 0:
            m.profit_factor = float("inf")
        else:
            m.profit_factor = 0.0

        # -- Trade averages ---------------------------------------------------
        m.avg_win = m.gross_profit / m.winning_trades if m.winning_trades > 0 else 0.0
        m.avg_loss = m.gross_loss / m.losing_trades if m.losing_trades > 0 else 0.0
        m.avg_trade = m.net_profit / m.total_trades if m.total_trades > 0 else 0.0
        m.largest_win = max(positive) if positive else 0.0
        m.largest_loss = min(negative) if negative else 0.0

        # -- Exit reason breakdown --------------------------------------------
        for t in trades:
            reason = t.exit_reason or "UNKNOWN"
            m.exit_reasons[reason] = m.exit_reasons.get(reason, 0) + 1

        # -- Time metrics -----------------------------------------------------
        bars_held_values: list[float] = []
        hours_held_values: list[float] = []
        tf_minutes = _timeframe_to_minutes(self._timeframe)

        for t in trades:
            try:
                open_dt = _parse_dt(t.open_time)
                close_dt = _parse_dt(t.close_time)
                td = close_dt - open_dt
                hours = td.total_seconds() / 3600.0
                hours_held_values.append(hours)
                bars_held_values.append(hours / (tf_minutes / 60.0))
            except (ValueError, TypeError):
                continue

        if hours_held_values:
            m.avg_hours_held = float(np.mean(hours_held_values))
            m.avg_bars_held = float(np.mean(bars_held_values))

        # -- Equity curve & drawdown ------------------------------------------
        equity_curve = self._equity_curve
        if not equity_curve and trades:
            # Build a simple equity curve from trade close events
            running_balance = self._initial_balance
            equity_curve = [(self._start_date, running_balance)]
            for t in trades:
                running_balance += t.profit
                equity_curve.append((t.close_time, running_balance))

        m.equity_curve = list(equity_curve)

        if equity_curve:
            drawdown_curve, max_dd_pct, max_dd_bars = self._compute_drawdown(equity_curve)
            m.drawdown_curve = drawdown_curve
            m.max_drawdown_pct = max_dd_pct
            m.max_drawdown_duration_bars = max_dd_bars

        # -- Sharpe & Sortino ratios ------------------------------------------
        if equity_curve and len(equity_curve) >= 5:
            m.sharpe_ratio, m.sortino_ratio = self._compute_ratios(equity_curve)
        else:
            m.sharpe_ratio = 0.0
            m.sortino_ratio = 0.0

        self._metrics = m
        return m

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_drawdown(
        equity_curve: list[tuple[str, float]],
    ) -> tuple[list[tuple[str, float]], float, int]:
        """Compute drawdown series, max drawdown %, and max drawdown duration.

        Returns:
            drawdown_curve: [(datetime_str, drawdown_pct), ...]
            max_drawdown_pct: float
            max_drawdown_duration_bars: int (consecutive bars with drawdown > 0)
        """
        drawdown_curve: list[tuple[str, float]] = []
        peak = float("-inf")
        max_dd_pct = 0.0
        current_dd_bars = 0
        max_dd_bars = 0

        for dt_str, equity in equity_curve:
            if equity > peak:
                peak = equity

            dd_pct = ((peak - equity) / peak) * 100 if peak > 0 else 0.0
            drawdown_curve.append((dt_str, dd_pct))

            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            if dd_pct > 0:
                current_dd_bars += 1
                if current_dd_bars > max_dd_bars:
                    max_dd_bars = current_dd_bars
            else:
                current_dd_bars = 0

        return drawdown_curve, max_dd_pct, max_dd_bars

    @staticmethod
    def _compute_ratios(
        equity_curve: list[tuple[str, float]],
    ) -> tuple[float, float]:
        """Compute Sharpe and Sortino ratios from equity curve.

        Resamples equity curve to daily returns, then computes annualized
        Sharpe and Sortino. Returns (0.0, 0.0) if insufficient data.
        """
        if len(equity_curve) < 5:
            return 0.0, 0.0

        # Build a daily equity series
        df = pd.DataFrame(equity_curve, columns=["datetime", "equity"])
        df["datetime"] = pd.to_datetime(df["datetime"], format="mixed")
        df = df.set_index("datetime")
        df = df.sort_index()

        # Resample to daily: use last equity of each day
        daily = df["equity"].resample("D").last().dropna()

        if len(daily) < 2:
            return 0.0, 0.0

        daily_returns = daily.pct_change().dropna()

        if len(daily_returns) < 2:
            return 0.0, 0.0

        mean_ret = daily_returns.mean()
        std_ret = daily_returns.std()

        sharpe = 0.0
        if std_ret > 0:
            sharpe = (mean_ret / std_ret) * math.sqrt(252)

        # Sortino: downside deviation only
        downside = daily_returns[daily_returns < 0]
        sortino = 0.0
        if len(downside) > 1:
            downside_std = downside.std()
            if downside_std > 0:
                sortino = (mean_ret / downside_std) * math.sqrt(252)

        return round(sharpe, 4), round(sortino, 4)

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def summary_table(self) -> str:
        """Return a formatted Unicode table with key metrics."""
        m = self._metrics
        if m is None:
            m = self.compute()

        # Box drawing characters
        # Detect if terminal supports Unicode box drawing
        try:
            "\u2550".encode(sys.stdout.encoding or "ascii")
            use_unicode = True
        except (UnicodeEncodeError, UnicodeError):
            use_unicode = False

        if use_unicode:
            h, v = "\u2550", "\u2551"
            tl, tr = "\u2554", "\u2557"
            bl, br = "\u255a", "\u255d"
            ml, mr = "\u2560", "\u2563"
            mt, mb = "\u2566", "\u2569"
            inf_str = "\u221e"
        else:
            h, v = "=", "|"
            tl = tr = bl = br = ml = mr = mt = mb = "+"
            inf_str = "inf"

        width = 44

        def line(left: str, fill: str, right: str) -> str:
            return f"{left}{fill * width}{right}"

        def header(text: str) -> str:
            return f"{v} {text.center(width - 2)} {v}"

        def row(label: str, value: str) -> str:
            padded = f" {label}: {value}"
            return f"{v} {padded.ljust(width - 2)} {v}"

        lines: list[str] = []
        lines.append(line(tl, h, tr))
        lines.append(header(f"BACKTEST REPORT - {m.symbol}"))
        lines.append(line(ml, h, mr))
        lines.append(row("Period", f"{m.start_date} -> {m.end_date}"))
        lines.append(row("Initial Balance", f"${m.initial_balance:,.2f}"))
        lines.append(row("Final Balance", f"${m.final_balance:,.2f}"))
        lines.append(row("Return", f"{m.return_pct:+.2f}%"))
        lines.append(line(ml, h, mr))
        lines.append(row("Total Trades", str(m.total_trades)))
        lines.append(
            row(
                "Win Rate",
                f"{m.win_rate_pct:.1f}% ({m.winning_trades}W / {m.losing_trades}L)",
            )
        )
        pf_str = inf_str if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
        lines.append(row("Profit Factor", pf_str))
        lines.append(row("Avg Win", f"${m.avg_win:+,.2f}"))
        lines.append(row("Avg Loss", f"${m.avg_loss:+,.2f}"))
        lines.append(row("Largest Win", f"${m.largest_win:+,.2f}"))
        lines.append(row("Largest Loss", f"${m.largest_loss:+,.2f}"))
        lines.append(line(ml, h, mr))
        lines.append(row("Max Drawdown", f"{m.max_drawdown_pct:.1f}%"))
        lines.append(row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}"))
        lines.append(row("Sortino Ratio", f"{m.sortino_ratio:.2f}"))
        lines.append(line(ml, h, mr))
        exit_parts = "  ".join(f"{k}: {v}" for k, v in m.exit_reasons.items())
        lines.append(row("Exit Reasons", exit_parts if exit_parts else "N/A"))
        lines.append(line(bl, h, br))

        return "\n".join(lines)

    def print_report(self) -> None:
        """Print the summary table to console."""
        print(self.summary_table())

    def to_dict(self) -> dict:
        """Convert all metrics to a JSON-serializable dict."""
        m = self._metrics
        if m is None:
            m = self.compute()

        pf = m.profit_factor
        if pf == float("inf"):
            pf = "inf"

        return {
            "symbol": m.symbol,
            "start_date": m.start_date,
            "end_date": m.end_date,
            "initial_balance": m.initial_balance,
            "final_balance": m.final_balance,
            "final_equity": m.final_equity,
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "win_rate_pct": round(m.win_rate_pct, 2),
            "net_profit": round(m.net_profit, 2),
            "gross_profit": round(m.gross_profit, 2),
            "gross_loss": round(m.gross_loss, 2),
            "profit_factor": pf,
            "avg_win": round(m.avg_win, 2),
            "avg_loss": round(m.avg_loss, 2),
            "avg_trade": round(m.avg_trade, 2),
            "largest_win": round(m.largest_win, 2),
            "largest_loss": round(m.largest_loss, 2),
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "max_drawdown_duration_bars": m.max_drawdown_duration_bars,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "return_pct": round(m.return_pct, 2),
            "exit_reasons": dict(m.exit_reasons),
            "avg_bars_held": round(m.avg_bars_held, 2),
            "avg_hours_held": round(m.avg_hours_held, 2),
            "equity_curve": [[ts, val] for ts, val in m.equity_curve],
            "drawdown_curve": [[ts, val] for ts, val in m.drawdown_curve],
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert closed trades to a DataFrame."""
        trades = self._executor.closed_trades

        if not trades:
            return pd.DataFrame(
                columns=[
                    "ticket",
                    "direction",
                    "open_time",
                    "close_time",
                    "open_price",
                    "close_price",
                    "profit",
                    "exit_reason",
                    "bars_held",
                ]
            )

        tf_minutes = _timeframe_to_minutes(self._timeframe)
        rows = []
        for t in trades:
            bars_held: float | None = None
            try:
                open_dt = _parse_dt(t.open_time)
                close_dt = _parse_dt(t.close_time)
                hours = (close_dt - open_dt).total_seconds() / 3600.0
                bars_held = round(hours / (tf_minutes / 60.0), 1)
            except (ValueError, TypeError):
                bars_held = None

            rows.append(
                {
                    "ticket": t.ticket,
                    "direction": t.direction,
                    "open_time": t.open_time,
                    "close_time": t.close_time,
                    "open_price": t.open_price,
                    "close_price": t.close_price,
                    "profit": t.profit,
                    "exit_reason": t.exit_reason,
                    "bars_held": bars_held,
                }
            )

        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def generate_multi_symbol_report(
    symbol_results: dict[str, dict],
    initial_balance: float,
) -> pd.DataFrame:
    """Generate a comparison DataFrame across multiple symbols.

    Parameters
    ----------
    symbol_results : dict
        Keys are symbol names, values are dicts with at least:
        - "executor": SimulatedExecutor instance
        - "source": HistoricalDataSource instance
        Optionally:
        - "start_date": str
        - "end_date": str
    initial_balance : float
        Starting balance used across all symbols.

    Returns
    -------
    pd.DataFrame
        One row per symbol with key comparison metrics.
    """
    rows = []
    for sym, data in symbol_results.items():
        executor = data["executor"]
        report = BacktestReport(
            executor=executor,
            initial_balance=initial_balance,
            symbol=sym,
            start_date=data.get("start_date", ""),
            end_date=data.get("end_date", ""),
        )
        metrics = report.compute()
        rows.append(
            {
                "Symbol": sym,
                "Trades": metrics.total_trades,
                "Win Rate": f"{metrics.win_rate_pct:.1f}%",
                "Net Profit": f"${metrics.net_profit:+,.2f}",
                "Return": f"{metrics.return_pct:+.2f}%",
                "Profit Factor": (
                    "∞"
                    if metrics.profit_factor == float("inf")
                    else f"{metrics.profit_factor:.2f}"
                ),
                "Max DD": f"{metrics.max_drawdown_pct:.1f}%",
                "Sharpe": f"{metrics.sharpe_ratio:.2f}",
            }
        )
    return pd.DataFrame(rows)
