"""
Extended metrics computation for backtest results.

Complements the basic metrics already computed by engine.py's ``_compute_metrics``
with advanced ratios, distribution analysis, and formatted summary tables.

Usage::

    from strategiestoTest.core.metrics import (
        compute_advanced_metrics,
        summary_table,
        compare_strategies,
        compute_monthly_breakdown,
        compute_trade_distribution,
    )

    advanced = compute_advanced_metrics(result)
    print(summary_table(result))
    print(compare_strategies([r1, r2, r3]))
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

from .config import BacktestResult

# ---------------------------------------------------------------------------
# Advanced metrics
# ---------------------------------------------------------------------------


def compute_advanced_metrics(
    result: BacktestResult, df: Optional[pd.DataFrame] = None
) -> dict:
    """Compute advanced metrics beyond the basics.

    Parameters
    ----------
    result : BacktestResult
        The result object produced by ``BacktestEngine.run()``.
    df : pd.DataFrame, optional
        Raw price data - used when per-bar returns need to be recalculated.

    Returns
    -------
    dict
        Dictionary with the following keys:

        * calmar_ratio
        * sortino_ratio
        * avg_win_loss_ratio
        * largest_win_eur
        * largest_loss_eur
        * consecutive_wins
        * consecutive_losses
        * avg_mae_eur
        * avg_mfe_eur
        * recovery_factor
        * ulcer_index
        * upi (Ulcer Performance Index)
        * avg_monthly_return_pct
        * monthly_win_rate
        * best_month_pct
        * worst_month_pct
        * risk_of_ruin_pct
        * expectancy_per_eur
    """
    metrics: dict = {}
    trades = result.trades
    equity_curve = result.equity_curve

    # ---- calmar ratio: annualised return / max drawdown ----
    max_dd_pct = result.max_drawdown_pct
    if max_dd_pct > 0:
        calmar = _annualised_return(result) / abs(max_dd_pct)
    else:
        calmar = 0.0 if _annualised_return(result) <= 0 else float("inf")
    metrics["calmar_ratio"] = round(calmar, 3)

    # ---- sortino ratio: like Sharpe but only penalises downside ----
    equity_vals = np.array([e["equity"] for e in equity_curve], dtype=float)
    if len(equity_vals) > 1:
        rets = np.diff(equity_vals) / equity_vals[:-1]
        mar = _get_min_acceptable_return(result)
        downside = rets[rets < mar]
        if len(downside) > 0 and np.std(downside) > 0:
            sortino = (
                float(np.mean(rets) - mar)
                / float(np.std(downside))
                * np.sqrt(_bars_per_year(result))
            )
        else:
            sortino = 0.0
    else:
        sortino = 0.0
    metrics["sortino_ratio"] = round(sortino, 3)

    # ---- win / loss ratio ----
    if result.avg_loss_eur > 0:
        wl_ratio = result.avg_win_eur / result.avg_loss_eur
    else:
        wl_ratio = float("inf") if result.avg_win_eur > 0 else 0.0
    metrics["avg_win_loss_ratio"] = (
        round(wl_ratio, 3) if wl_ratio != float("inf") else float("inf")
    )

    # ---- largest win / loss ----
    profits = [t["profit_eur"] for t in trades]
    if profits:
        metrics["largest_win_eur"] = round(max(profits), 2)
        metrics["largest_loss_eur"] = round(min(profits), 2)
    else:
        metrics["largest_win_eur"] = 0.0
        metrics["largest_loss_eur"] = 0.0

    # ---- consecutive streaks ----
    metrics["consecutive_wins"] = _max_consecutive([
        1 if t["profit_eur"] > 0 else 0 for t in trades
    ], target=1)
    metrics["consecutive_losses"] = _max_consecutive([
        1 if t["profit_eur"] <= 0 else 0 for t in trades
    ], target=1)

    # ---- MAE / MFE ----
    mae_vals: list[float] = []
    mfe_vals: list[float] = []
    for t in trades:
        mae = t.get("mae_eur")
        mfe = t.get("mfe_eur")
        if mae is not None:
            mae_vals.append(float(mae))
        if mfe is not None:
            mfe_vals.append(float(mfe))
    metrics["avg_mae_eur"] = (
        round(float(np.mean(mae_vals)), 2) if mae_vals else 0.0
    )
    metrics["avg_mfe_eur"] = (
        round(float(np.mean(mfe_vals)), 2) if mfe_vals else 0.0
    )

    # ---- recovery factor ----
    if result.max_drawdown_eur > 0:
        recovery = result.net_profit_eur / result.max_drawdown_eur
    elif result.net_profit_eur > 0:
        recovery = float("inf")
    else:
        recovery = 0.0
    metrics["recovery_factor"] = (
        round(recovery, 3) if recovery != float("inf") else float("inf")
    )

    # ---- ulcer index & UPI ----
    ui = _ulcer_index(equity_curve)
    metrics["ulcer_index"] = round(ui, 4)
    if ui > 0:
        ann_ret = _annualised_return(result)
        mar = _get_min_acceptable_return(result)
        metrics["upi"] = round((ann_ret - mar) / ui, 3)
    else:
        metrics["upi"] = 0.0

    # ---- monthly stats ----
    if equity_curve:
        monthly = _monthly_returns(equity_curve)
        returns_pct: list[float] = list(monthly.values())
        if returns_pct:
            metrics["avg_monthly_return_pct"] = round(
                float(np.mean(returns_pct)), 2
            )
            metrics["monthly_win_rate"] = round(
                sum(1 for r in returns_pct if r > 0)
                / len(returns_pct)
                * 100.0,
                1,
            )
            metrics["best_month_pct"] = round(float(np.max(returns_pct)), 2)
            metrics["worst_month_pct"] = round(float(np.min(returns_pct)), 2)
        else:
            metrics["avg_monthly_return_pct"] = 0.0
            metrics["monthly_win_rate"] = 0.0
            metrics["best_month_pct"] = 0.0
            metrics["worst_month_pct"] = 0.0
    else:
        metrics["avg_monthly_return_pct"] = 0.0
        metrics["monthly_win_rate"] = 0.0
        metrics["best_month_pct"] = 0.0
        metrics["worst_month_pct"] = 0.0

    # ---- risk of ruin (simplified Kelly) ----
    metrics["risk_of_ruin_pct"] = round(_risk_of_ruin(result), 2)

    # ---- expectancy per euro risked ----
    avg_sl_cost = _avg_sl_cost_eur(trades)
    if avg_sl_cost > 0:
        metrics["expectancy_per_eur"] = round(
            result.expectancy_eur / avg_sl_cost, 4
        )
    else:
        metrics["expectancy_per_eur"] = 0.0

    return metrics


# ---------------------------------------------------------------------------
# Monthly breakdown
# ---------------------------------------------------------------------------


def compute_monthly_breakdown(equity_curve: list[dict]) -> dict:
    """Group equity curve by month and compute stats per month.

    Parameters
    ----------
    equity_curve : list[dict]
        Each entry: ``{"datetime": ..., "equity": ..., "drawdown_pct": ...}``.

    Returns
    -------
    dict
        ``{month_label: {trades, profit, return_pct, ...}, ...}``
        Sorted chronologically.
    """
    if not equity_curve:
        return {}

    # Convert to DataFrame for easier grouping.
    df = pd.DataFrame(equity_curve)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["month"] = df["datetime"].dt.to_period("M")

    breakdown: dict[str, dict] = {}
    for month, group in df.groupby("month", sort=True):
        month_str = str(month)
        start_eq = float(group["equity"].iloc[0])
        end_eq = float(group["equity"].iloc[-1])
        profit = end_eq - start_eq
        ret_pct = (profit / start_eq * 100.0) if start_eq > 0 else 0.0
        max_dd = float(group["drawdown_pct"].max())

        breakdown[month_str] = {
            "start_equity": round(start_eq, 2),
            "end_equity": round(end_eq, 2),
            "profit": round(profit, 2),
            "return_pct": round(ret_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "bars": len(group),
        }

    return dict(sorted(breakdown.items()))


# ---------------------------------------------------------------------------
# Trade distribution
# ---------------------------------------------------------------------------


def compute_trade_distribution(trades: list[dict]) -> dict:
    """Histogram of trade PnL and streak analysis.

    Parameters
    ----------
    trades : list[dict]
        Each entry must have ``"profit_eur"``.

    Returns
    -------
    dict
        ``{"buckets": [...], "counts": [...], "cumulative_pnl": [...],
           "win_streaks": [...], "loss_streaks": [...]}``
    """
    if not trades:
        return {
            "buckets": [],
            "counts": [],
            "cumulative_pnl": [],
            "win_streaks": [],
            "loss_streaks": [],
        }

    profits = np.array([t["profit_eur"] for t in trades], dtype=float)

    # ---- histogram buckets ----
    p_min = float(np.min(profits))
    p_max = float(np.max(profits))
    if p_max - p_min < 1e-9:
        buckets = [round(p_min, 2)]
        counts = [len(profits)]
    else:
        num_buckets = min(20, max(5, len(profits) // 5))
        bins = np.linspace(p_min, p_max, num_buckets + 1)
        counts_np, edges = np.histogram(profits, bins=bins)
        buckets = [round(float(e), 2) for e in edges[:-1]]
        counts = counts_np.tolist()

    cumulative_pnl: list[float] = []
    running = 0.0
    for t in trades:
        running += t["profit_eur"]
        cumulative_pnl.append(round(running, 2))

    # ---- streak distributions ----
    win_streaks = _streak_lengths(profits > 0)
    loss_streaks = _streak_lengths(profits <= 0)

    return {
        "buckets": buckets,
        "counts": counts,
        "cumulative_pnl": cumulative_pnl,
        "win_streaks": win_streaks,
        "loss_streaks": loss_streaks,
    }


# ---------------------------------------------------------------------------
# Summary table (ASCII)
# ---------------------------------------------------------------------------


def summary_table(result: BacktestResult) -> str:
    """Return a nicely formatted text summary table.

    Uses box-drawing characters and aligned columns.
    """
    adv = compute_advanced_metrics(result)

    def _fmt(v, decimals=2):
        if isinstance(v, float):
            if math.isinf(v):
                return "INF"
            return f"{v:,.{decimals}f}"
        return str(v)

    rows = [
        ("Total Trades", str(result.total_trades)),
        ("Win Trades", str(result.win_trades)),
        ("Loss Trades", str(result.loss_trades)),
        ("Win Rate", f"{_fmt(result.win_rate_pct, 1)} %"),
        ("Profit Factor", _fmt(result.profit_factor)),
        ("Net Profit", f"{_fmt(result.net_profit_eur)} EUR"),
        ("Max Drawdown", f"{_fmt(result.max_drawdown_pct, 1)} %"),
        ("Max Drawdown EUR", f"{_fmt(result.max_drawdown_eur)} EUR"),
        ("Avg Win", f"{_fmt(result.avg_win_eur)} EUR"),
        ("Avg Loss", f"{_fmt(result.avg_loss_eur)} EUR"),
        ("Expectancy", f"{_fmt(result.expectancy_eur)} EUR"),
        ("Sharpe Ratio", _fmt(result.sharpe_ratio)),
        ("Sortino Ratio", _fmt(adv.get("sortino_ratio", 0))),
        ("Calmar Ratio", _fmt(adv.get("calmar_ratio", 0), 3)),
        ("Win/Loss Ratio", _fmt(adv.get("avg_win_loss_ratio", 0), 3)),
        ("Largest Win", f"{_fmt(adv.get('largest_win_eur', 0))} EUR"),
        ("Largest Loss", f"{_fmt(adv.get('largest_loss_eur', 0))} EUR"),
        ("Consec Wins", str(adv.get("consecutive_wins", 0))),
        ("Consec Losses", str(adv.get("consecutive_losses", 0))),
        ("Recovery Factor", _fmt(adv.get("recovery_factor", 0), 3)),
        ("Ulcer Index", _fmt(adv.get("ulcer_index", 0), 4)),
        ("UPI", _fmt(adv.get("upi", 0), 3)),
        ("Avg Month Ret", f"{_fmt(adv.get('avg_monthly_return_pct', 0))} %"),
        (
            "Monthly Win Rate",
            f"{_fmt(adv.get('monthly_win_rate', 0), 1)} %",
        ),
        ("Best Month", f"{_fmt(adv.get('best_month_pct', 0))} %"),
        ("Worst Month", f"{_fmt(adv.get('worst_month_pct', 0))} %"),
        ("Risk of Ruin", f"{_fmt(adv.get('risk_of_ruin_pct', 0))} %"),
        ("Expectancy / EUR", _fmt(adv.get("expectancy_per_eur", 0), 4)),
        ("Avg Bars Held", _fmt(result.avg_bars_held, 1)),
    ]

    label_w = max(len(r[0]) for r in rows) + 2
    raw_val_w = max(len(r[1]) for r in rows) + 2
    # Cap value column at 22 chars to keep the table readable.
    val_w = min(raw_val_w, 22)

    top = "\u2554" + "\u2550" * label_w + "\u2566" + "\u2550" * val_w + "\u2557"
    sep = "\u2560" + "\u2550" * label_w + "\u256c" + "\u2550" * val_w + "\u2563"
    bot = "\u255a" + "\u2550" * label_w + "\u2569" + "\u2550" * val_w + "\u255d"

    lines = [top]
    lines.append(
        f"\u2551 {'Metric':<{label_w - 1}}"
        f"\u2551 {'Value':<{val_w - 1}}\u2551"
    )
    lines.append(sep)
    for label, value in rows:
        display_val = value if len(value) < val_w else value[: val_w - 4] + "..."
        lines.append(
            f"\u2551 {label:<{label_w - 1}}"
            f"\u2551 {display_val:<{val_w - 1}}\u2551"
        )
    lines.append(bot)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Strategy comparison table
# ---------------------------------------------------------------------------


def compare_strategies(results: list[BacktestResult]) -> str:
    """Side-by-side comparison table of multiple strategies.

    Sorted by Sharpe ratio descending.

    Columns: Strategy, Trades, Win%, PF, Net PnL, Max DD%, Sharpe,
             Sortino, Expectancy.
    """
    if not results:
        return "(no strategies to compare)"

    # Sort by Sharpe descending.
    sorted_results = sorted(
        results, key=lambda r: r.sharpe_ratio, reverse=True
    )

    columns = [
        ("Strategy", 22),
        ("Trades", 7),
        ("Win%", 7),
        ("PF", 7),
        ("Net PnL", 10),
        ("MaxDD%", 8),
        ("Sharpe", 7),
        ("Sortino", 8),
        ("Expect", 10),
    ]

    def _build_row(result: BacktestResult) -> list[str]:
        adv = compute_advanced_metrics(result)
        return [
            result.strategy_name[:20],
            str(result.total_trades),
            f"{result.win_rate_pct:.1f}",
            f"{result.profit_factor:.2f}",
            f"{result.net_profit_eur:,.0f}",
            f"{result.max_drawdown_pct:.1f}",
            f"{result.sharpe_ratio:.2f}",
            f"{adv.get('sortino_ratio', 0):.2f}",
            f"{result.expectancy_eur:,.2f}",
        ]

    # Header.
    header = "\u2502" + "\u2502".join(
        f" {col:<{w - 1}}" for col, w in columns
    ) + "\u2502"
    sep_h = "\u255e" + "\u2550" * (len(header) - 2) + "\u2561"
    top_b = "\u2554" + "\u2550" * (len(header) - 2) + "\u2557"
    bot_b = "\u255a" + "\u2550" * (len(header) - 2) + "\u255d"
    mid_b = "\u2560" + "\u2550" * (len(header) - 2) + "\u2563"

    lines = [top_b, header, sep_h]
    for i, r in enumerate(sorted_results):
        row = _build_row(r)
        line = "\u2502" + "\u2502".join(
            f" {val:<{w - 1}}" for val, (_, w) in zip(row, columns)
        ) + "\u2502"
        lines.append(line)
        if i < len(sorted_results) - 1:
            lines.append(mid_b)
    lines.append(bot_b)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TIMEFRAME_MINUTES: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "W1": 10080,
    "MN1": 43200,
}


def _annualised_return(result: BacktestResult) -> float:
    """Estimate annualised return from the equity curve.

    Uses simple (linear) annualisation for periods shorter than 1 month
    to avoid astronomical compounding artefacts on tiny sample sizes.
    """
    eq = result.equity_curve
    if len(eq) < 2:
        return 0.0
    start = float(eq[0]["equity"])
    end = float(eq[-1]["equity"])
    if start <= 0:
        return 0.0
    total_ret = (end - start) / start
    bpy = _bars_per_year(result)
    if bpy <= 0:
        return 0.0
    bars = len(eq)
    years = bars / bpy
    # Floor to 1 month (21/252 ≈ 0.083 yr) to prevent absurd compounding
    # on very short backtests.
    min_years = 21.0 / 252.0
    effective_years = max(years, min_years)
    if effective_years <= 0:
        return 0.0
    return (1.0 + total_ret) ** (1.0 / effective_years) - 1.0


def _bars_per_year(result: BacktestResult) -> float:
    """Number of bars per year for the strategy's timeframe."""
    tf_minutes = _TIMEFRAME_MINUTES.get(result.timeframe, 15)
    return 252.0 * 24.0 * (60.0 / tf_minutes)


def _get_min_acceptable_return(result: BacktestResult, rf: float = 0.0) -> float:
    """Minimum acceptable return - defaults to 0 (preservation of capital).

    Could be set to the risk-free rate for more precise Sortino/UPI.
    """
    return rf


def _max_consecutive(seq: list[int], target: int) -> int:
    """Max consecutive occurrences of *target* in *seq*."""
    best = 0
    current = 0
    for v in seq:
        if v == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _streak_lengths(mask: np.ndarray) -> list[int]:
    """Return list of streak lengths for consecutive True values in *mask*."""
    lengths: list[int] = []
    cnt = 0
    for v in mask:
        if v:
            cnt += 1
        else:
            if cnt > 0:
                lengths.append(cnt)
            cnt = 0
    if cnt > 0:
        lengths.append(cnt)
    return lengths


def _ulcer_index(equity_curve: list[dict]) -> float:
    """Ulcer Index = sqrt(mean(drawdown^2))."""
    if not equity_curve:
        return 0.0
    equity = np.array([e["equity"] for e in equity_curve], dtype=float)
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
    return float(np.sqrt(np.mean(dd ** 2)))


def _monthly_returns(equity_curve: list[dict]) -> dict[str, float]:
    """Compute return % per calendar month."""
    if not equity_curve:
        return {}
    df = pd.DataFrame(equity_curve)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["month"] = df["datetime"].dt.to_period("M")

    result: dict[str, float] = {}
    for month, group in df.groupby("month", sort=True):
        start_eq = float(group["equity"].iloc[0])
        end_eq = float(group["equity"].iloc[-1])
        if start_eq > 0:
            result[str(month)] = (end_eq - start_eq) / start_eq * 100.0
        else:
            result[str(month)] = 0.0
    return result


def _risk_of_ruin(result: BacktestResult) -> float:
    """Simplified Kelly-based risk of ruin estimate.

    RoR = ((1 - edge) / (1 + edge)) ^ capital_units

    where edge = win_rate - (1 - win_rate) / win_loss_ratio
    and capital_units = capital / avg_loss
    """
    if result.total_trades == 0:
        return 100.0

    wr = result.win_rate_pct / 100.0
    if wr >= 1.0:
        return 0.0
    if wr <= 0.0:
        return 100.0

    if result.avg_loss_eur == 0:
        return 100.0 if result.net_profit_eur <= 0 else 0.0

    wl_ratio = result.avg_win_eur / result.avg_loss_eur
    if wl_ratio <= 0:
        return 100.0

    edge = wr - (1.0 - wr) / wl_ratio
    if edge <= 0:
        return 100.0

    # Capital units: how many average losses can the account absorb
    capital = float(result.equity_curve[0]["equity"]) if result.equity_curve else 1000.0
    units = min(capital / result.avg_loss_eur, 50.0) if result.avg_loss_eur > 0 else 0.0
    if units <= 0:
        return 100.0

    loss_prob = (1.0 - edge) / (1.0 + edge)
    ror = loss_prob ** units * 100.0
    return min(ror, 100.0)


def _avg_sl_cost_eur(trades: list[dict]) -> float:
    """Average cost of a stop-loss hit in EUR.

    If trades don't carry their SL distance, estimate from avg_loss.
    """
    losses = [t for t in trades if t["profit_eur"] < 0]
    if not losses:
        return 0.0
    return abs(float(np.mean([t["profit_eur"] for t in losses])))
