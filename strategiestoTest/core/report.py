"""
Generate comprehensive Markdown reports for a backtest result.

Usage::

    from strategiestoTest.core.report import (
        generate_report,
        executive_summary,
        generate_optimization_report,
    )

    path = generate_report(result, output_dir="reports")
    print(executive_summary(result))

    opt_path = generate_optimization_report(
        "my_strat", opt_result, output_dir="reports"
    )
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import BacktestResult, OptimizationResult
from .metrics import (
    compute_advanced_metrics,
    compute_monthly_breakdown,
    compute_trade_distribution,
    summary_table,
)

# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------


def generate_report(
    result: BacktestResult, output_dir: str | None = None
) -> str:
    """Generate a complete Markdown report for a strategy backtest.

    The report includes:

    1. Header with strategy name, symbol, timeframe, dates
    2. Executive Summary (1 paragraph interpreting the key numbers)
    3. Performance Metrics table (all key stats)
    4. Advanced Metrics section
    5. Monthly Breakdown table
    6. Trade Distribution (win/loss histogram as ASCII)
    7. Exit Reasons breakdown
    8. Equity Curve (described in text, max DD, recovery, etc.)
    9. Parameter Summary
    10. Warnings/Recommendations

    Also saves:

    - ``{output_dir}/{strategy_name}_report.md`` (the markdown)
    - ``{output_dir}/{strategy_name}_trades.csv`` (detail of each trade)
    - ``{output_dir}/{strategy_name}_equity.csv`` (equity curve points)
    - ``{output_dir}/{strategy_name}_summary.json`` (key metrics as JSON)

    Parameters
    ----------
    result : BacktestResult
        The backtest result produced by ``BacktestEngine.run()``.
    output_dir : str, optional
        Directory to write output files. Defaults to ``./reports``.

    Returns
    -------
    str
        Path to the generated Markdown report file.
    """
    if output_dir is None:
        output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)

    base = _sanitise_name(result.strategy_name)
    adv = compute_advanced_metrics(result)
    monthly = compute_monthly_breakdown(result.equity_curve)
    dist = compute_trade_distribution(result.trades)

    # ---- build report sections ----
    sections: list[str] = []

    sections.append(_report_header(result))
    sections.append(_report_exec_summary(result, adv))
    sections.append(_report_metrics(result, adv))
    sections.append(_report_advanced_metrics(adv))
    sections.append(_report_monthly_breakdown(monthly))
    sections.append(_report_trade_distribution(dist))
    sections.append(_report_exit_reasons(result))
    sections.append(_report_equity_curve(result))
    sections.append(_report_params(result))
    sections.append(_report_warnings(result, adv))

    md_content = "\n\n".join(sections)

    # ---- write files ----
    report_path = os.path.join(output_dir, f"{base}_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Trades CSV
    trades_path = os.path.join(output_dir, f"{base}_trades.csv")
    if result.trades:
        pd.DataFrame(result.trades).to_csv(trades_path, index=False)
    else:
        pd.DataFrame(
            columns=[
                "entry_time",
                "exit_time",
                "direction",
                "entry_price",
                "exit_price",
                "volume",
                "profit_eur",
                "exit_reason",
                "bars_held",
                "sl",
                "tp",
            ]
        ).to_csv(trades_path, index=False)

    # Equity curve CSV
    equity_path = os.path.join(output_dir, f"{base}_equity.csv")
    if result.equity_curve:
        pd.DataFrame(result.equity_curve).to_csv(equity_path, index=False)
    else:
        pd.DataFrame(
            columns=["datetime", "equity", "drawdown_pct"]
        ).to_csv(equity_path, index=False)

    # Summary JSON
    summary_path = os.path.join(output_dir, f"{base}_summary.json")
    summary_data = _build_summary_dict(result, adv)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, default=str)

    return report_path


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------


def executive_summary(result: BacktestResult) -> str:
    """3-5 line executive summary interpreting results.

    Examples of what to say:

    - "Strong strategy: profit factor {x}, consistent with {win_rate}% win rate"
    - "Warning: high drawdown of {x}% exceeds the 5% daily limit"
    - "The strategy shows promise but {x} trades is too few for statistical
      significance"
    - "Sharpe ratio of {x} indicates good risk-adjusted returns"
    - "Consider increasing position size: expectancy is positive at {x}/trade"
    - "Avoid: negative expectancy means this loses money over time"
    """
    adv = compute_advanced_metrics(result)
    return _build_exec_summary(result, adv)


# ---------------------------------------------------------------------------
# Optimization report
# ---------------------------------------------------------------------------


def generate_optimization_report(
    strategy_name: str,
    opt_result: OptimizationResult,
    output_dir: str,
) -> str:
    """Generate a report for parameter optimization results.

    Shows:

    - Best parameters found
    - Top 10 parameter combinations ranked by score
    - Parameter sensitivity: which params matter most
    - Overfitting warning if best result is much better than #2
    - Recommendation for next steps

    Returns the path to the generated Markdown report.
    """
    os.makedirs(output_dir, exist_ok=True)
    base = _sanitise_name(strategy_name)

    sections: list[str] = []

    sections.append(
        f"# Optimization Report: {strategy_name}\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        "---"
    )

    # ---- best parameters ----
    sections.append(_opt_best_params(opt_result))

    # ---- top 10 ----
    sections.append(_opt_top_n(opt_result, n=10))

    # ---- parameter sensitivity ----
    sections.append(_opt_param_sensitivity(opt_result))

    # ---- overfitting warning ----
    sections.append(_opt_overfitting_warning(opt_result))

    # ---- recommendations ----
    sections.append(_opt_recommendations(opt_result))

    md_content = "\n\n".join(sections)

    report_path = os.path.join(output_dir, f"{base}_optimization_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save optimization results as JSON
    json_path = os.path.join(output_dir, f"{base}_optimization.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(opt_result.to_dict(), f, indent=2, default=str)

    return report_path


# ===================================================================
# Report section builders
# ===================================================================


def _report_header(result: BacktestResult) -> str:
    return (
        f"# Backtest Report: {result.strategy_name}\n\n"
        f"| Property | Value |\n"
        f"|----------|-------|\n"
        f"| Symbol | {result.symbol} |\n"
        f"| Timeframe | {result.timeframe} |\n"
        f"| Start | {result.start_date} |\n"
        f"| End | {result.end_date} |\n"
        f"| Generated | {datetime.now().strftime('%Y-%m-%d %H:%M')} |\n"
        f"\n---"
    )


def _report_exec_summary(result: BacktestResult, adv: dict) -> str:
    return (
        "## Executive Summary\n\n"
        + _build_exec_summary(result, adv)
        + "\n\n---"
    )


def _report_metrics(result: BacktestResult, adv: dict) -> str:
    """Render the summary_table wrapped in a code block."""
    table = summary_table(result)
    return f"## Performance Metrics\n\n```\n{table}\n```\n\n---"


def _report_advanced_metrics(adv: dict) -> str:
    """Advanced metrics as a Markdown table."""
    rows = [
        ("Calmar Ratio", adv.get("calmar_ratio", 0)),
        ("Sortino Ratio", adv.get("sortino_ratio", 0)),
        ("Recovery Factor", adv.get("recovery_factor", 0)),
        ("Avg Win/Loss Ratio", adv.get("avg_win_loss_ratio", 0)),
        ("Largest Win (EUR)", adv.get("largest_win_eur", 0)),
        ("Largest Loss (EUR)", adv.get("largest_loss_eur", 0)),
        ("Consecutive Wins", adv.get("consecutive_wins", 0)),
        ("Consecutive Losses", adv.get("consecutive_losses", 0)),
        ("Avg MAE (EUR)", adv.get("avg_mae_eur", 0)),
        ("Avg MFE (EUR)", adv.get("avg_mfe_eur", 0)),
        ("Ulcer Index", adv.get("ulcer_index", 0)),
        ("UPI", adv.get("upi", 0)),
        ("Risk of Ruin (%)", adv.get("risk_of_ruin_pct", 0)),
        ("Expectancy / EUR Risked", adv.get("expectancy_per_eur", 0)),
    ]

    lines = [
        "## Advanced Metrics\n",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for label, val in rows:
        lines.append(f"| {label} | {_fmt_num(val)} |")
    lines.append("\n---")
    return "\n".join(lines)


def _report_monthly_breakdown(monthly: dict) -> str:
    if not monthly:
        return "## Monthly Breakdown\n\n*No data available*\n\n---"

    lines = [
        "## Monthly Breakdown\n",
        "| Month | Start Equity | End Equity | Profit | Return % | Max DD % |",
        "|-------|-------------|-----------|--------|----------|----------|",
    ]
    for month, stats in monthly.items():
        lines.append(
            f"| {month} | "
            f"{stats['start_equity']:,.2f} | "
            f"{stats['end_equity']:,.2f} | "
            f"{stats['profit']:+,.2f} | "
            f"{stats['return_pct']:+.2f} | "
            f"{stats['max_drawdown_pct']:.2f} |"
        )
    lines.append("\n---")
    return "\n".join(lines)


def _report_trade_distribution(dist: dict) -> str:
    if not dist.get("buckets"):
        return "## Trade Distribution\n\n*No trades*\n\n---"

    buckets = dist["buckets"]
    counts = dist["counts"]
    win_streaks = dist.get("win_streaks", [])
    loss_streaks = dist.get("loss_streaks", [])

    # ASCII histogram
    max_count = max(counts) if counts else 1
    bar_width = 40
    lines = ["## Trade Distribution\n"]
    lines.append("### PnL Histogram\n")
    lines.append("```")
    for i, (bucket, cnt) in enumerate(zip(buckets, counts)):
        if i < len(buckets) - 1:
            label = f"{bucket:>8.2f} - {buckets[i + 1]:.2f}"
        else:
            label = f"{bucket:>8.2f}+"
        bar = "#" * max(1, int(cnt / max_count * bar_width))
        lines.append(f"{label} | {bar} ({cnt})")
    lines.append("```")

    # Streak distribution
    lines.append("\n### Win Streak Distribution\n")
    if win_streaks:
        lines.append(f"- Max win streak: **{max(win_streaks)}**")
        lines.append(f"- Avg win streak: **{np.mean(win_streaks):.1f}**")
        lines.append(f"- Streak lengths: {sorted(win_streaks)}")
    else:
        lines.append("- No win streaks")

    lines.append("\n### Loss Streak Distribution\n")
    if loss_streaks:
        lines.append(f"- Max loss streak: **{max(loss_streaks)}**")
        lines.append(f"- Avg loss streak: **{np.mean(loss_streaks):.1f}**")
        lines.append(f"- Streak lengths: {sorted(loss_streaks)}")
    else:
        lines.append("- No loss streaks")

    lines.append("\n---")
    return "\n".join(lines)


def _report_exit_reasons(result: BacktestResult) -> str:
    exit_reasons = result.exit_reasons
    if not exit_reasons:
        return "## Exit Reasons\n\n*No exit data*\n\n---"

    total = sum(exit_reasons.values())
    lines = ["## Exit Reasons\n"]
    lines.append("| Reason | Count | % |")
    lines.append("|--------|-------|---|")
    for reason, count in sorted(
        exit_reasons.items(), key=lambda x: x[1], reverse=True
    ):
        pct = count / total * 100.0 if total > 0 else 0.0
        lines.append(f"| {reason} | {count} | {pct:.1f}% |")
    lines.append(f"\n**Total:** {total}\n\n---")
    return "\n".join(lines)


def _report_equity_curve(result: BacktestResult) -> str:
    eq = result.equity_curve
    if not eq:
        return "## Equity Curve\n\n*No equity data*\n\n---"

    start = float(eq[0]["equity"])
    end = float(eq[-1]["equity"])
    net = end - start
    ret_pct = (net / start * 100.0) if start > 0 else 0.0
    max_dd = float(max(e["drawdown_pct"] for e in eq))

    # Find the drawdown period
    dd_end_idx = int(
        np.argmax([e["drawdown_pct"] for e in eq])
    )
    dd_end_dt = eq[dd_end_idx]["datetime"]

    # Recovery analysis
    peak_eq = float(eq[0]["equity"])
    peak_dt = str(eq[0]["datetime"])
    for e in eq:
        if float(e["equity"]) > peak_eq:
            peak_eq = float(e["equity"])
            peak_dt = str(e["datetime"])

    lines = ["## Equity Curve\n"]
    lines.append(f"- **Starting equity:** {start:,.2f} EUR")
    lines.append(f"- **Final equity:** {end:,.2f} EUR")
    lines.append(f"- **Net change:** {net:+,.2f} EUR ({ret_pct:+.2f}%)")
    lines.append(f"- **Max drawdown:** {max_dd:.2f}% (at {dd_end_dt})")
    lines.append(f"- **Peak equity:** {peak_eq:,.2f} EUR (at {peak_dt})")
    lines.append(f"- **Total bars:** {len(eq)}")

    # Recovery from max DD
    if max_dd > 0 and start > 0:
        dd_euro = start * max_dd / 100.0
        if result.net_profit_eur > 0:
            recovery_ratio = result.net_profit_eur / dd_euro
            lines.append(
                f"- **Drawdown recovery ratio:** {recovery_ratio:.2f}x"
            )

    # Check if still in drawdown
    if end < peak_eq and peak_eq > 0:
        current_dd = (peak_eq - end) / peak_eq * 100.0
        lines.append(
            f"- **Currently in drawdown:** {current_dd:.2f}% from peak"
        )

    lines.append("\n---")
    return "\n".join(lines)


def _report_params(result: BacktestResult) -> str:
    params = result.params
    if not params:
        return "## Strategy Parameters\n\n*No parameters recorded*\n\n---"

    lines = ["## Strategy Parameters\n"]
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for key in sorted(params):
        val = params[key]
        lines.append(f"| `{key}` | {val} |")
    lines.append("\n---")
    return "\n".join(lines)


def _report_warnings(result: BacktestResult, adv: dict) -> str:
    warnings: list[str] = []

    if result.total_trades < 30:
        warnings.append(
            f"- **Low sample size**: only {result.total_trades} trades "
            f"- results may not be statistically significant."
        )

    if result.max_drawdown_pct > 20.0:
        warnings.append(
            f"- **High drawdown**: {result.max_drawdown_pct:.1f}% "
            f"exceeds the 20% warning threshold."
        )

    if result.sharpe_ratio < 0.5:
        warnings.append(
            f"- **Low Sharpe ratio**: {result.sharpe_ratio:.2f} "
            f"- risk-adjusted returns are poor."
        )

    if result.win_rate_pct < 30.0:
        warnings.append(
            f"- **Low win rate**: {result.win_rate_pct:.1f}% "
            f"- may be psychologically difficult to trade."
        )

    if adv.get("risk_of_ruin_pct", 0) > 50.0:
        warnings.append(
            f"- **High risk of ruin**: {adv['risk_of_ruin_pct']:.1f}% "
            f"- capital preservation is at serious risk."
        )
    elif adv.get("risk_of_ruin_pct", 0) > 20.0:
        warnings.append(
            f"- **Elevated risk of ruin**: {adv['risk_of_ruin_pct']:.1f}% "
            f"- consider reducing position size."
        )

    if result.expectancy_eur < 0:
        warnings.append(
            f"- **Negative expectancy**: {result.expectancy_eur:.2f} EUR/trade "
            f"- this strategy loses money on average."
        )

    if not warnings:
        return "## Warnings\n\n*No warnings - strategy looks healthy based on available metrics.*\n"

    return "## Warnings\n\n" + "\n".join(warnings) + "\n"


# ===================================================================
# Executive summary builder
# ===================================================================


def _build_exec_summary(result: BacktestResult, adv: dict) -> str:
    """Build a 3-5 line executive summary."""
    lines: list[str] = []

    # Overall assessment
    if result.profit_factor >= 1.5 and result.sharpe_ratio >= 1.0:
        lines.append(
            f"**Strong strategy**: profit factor of "
            f"{result.profit_factor:.2f} and Sharpe ratio of "
            f"{result.sharpe_ratio:.2f} indicate solid risk-adjusted "
            f"performance over {result.total_trades} trades."
        )
    elif result.profit_factor >= 1.0:
        lines.append(
            f"**Acceptable strategy**: profit factor of "
            f"{result.profit_factor:.2f} is above breakeven with "
            f"{result.total_trades} trades, but the Sharpe of "
            f"{result.sharpe_ratio:.2f} suggests room for improvement."
        )
    else:
        lines.append(
            f"**Unprofitable strategy**: profit factor of "
            f"{result.profit_factor:.2f} means the strategy loses money "
            f"over {result.total_trades} trades."
        )

    # Drawdown commentary
    if result.max_drawdown_pct > 30:
        lines.append(
            f"The maximum drawdown of {result.max_drawdown_pct:.1f}% "
            f"is severe and exceeds typical risk tolerance limits. "
            f"Position sizing or stop management should be revisited."
        )
    elif result.max_drawdown_pct > 15:
        lines.append(
            f"The maximum drawdown of {result.max_drawdown_pct:.1f}% "
            f"is moderate but should be monitored."
        )
    else:
        lines.append(
            f"The maximum drawdown of {result.max_drawdown_pct:.1f}% "
            f"is within acceptable limits."
        )

    # Expectancy / sample size
    if result.total_trades < 30:
        lines.append(
            f"With only {result.total_trades} trades, "
            f"statistical significance is limited. More backtesting "
            f"or forward testing is recommended before live deployment."
        )
    elif result.expectancy_eur > 0:
        lines.append(
            f"Positive expectancy of {result.expectancy_eur:.2f} EUR/trade "
            f"with a {result.win_rate_pct:.1f}% win rate suggests "
            f"a viable edge if the sample size is sufficient."
        )
    else:
        lines.append(
            f"Negative expectancy of {result.expectancy_eur:.2f} EUR/trade "
            f"means this strategy is expected to lose money over time. "
            f"Live trading is not recommended."
        )

    # Risk of ruin note
    ror = adv.get("risk_of_ruin_pct", 0)
    if ror > 30:
        lines.append(
            f"Risk of ruin is estimated at {ror:.1f}% - "
            f"this is dangerously high. Consider halving position size."
        )

    return " ".join(lines)


# ===================================================================
# Optimization report section builders
# ===================================================================


def _opt_best_params(opt: OptimizationResult) -> str:
    lines = ["## Best Parameters\n"]
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for k, v in opt.best_params.items():
        lines.append(f"| `{k}` | {v} |")

    if opt.best_metrics:
        lines.append("\n### Best Result Metrics\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for k, v in opt.best_metrics.items():
            lines.append(f"| {k} | {_fmt_num(v)} |")

    lines.append("\n---")
    return "\n".join(lines)


def _opt_top_n(opt: OptimizationResult, n: int = 10) -> str:
    results = opt.all_results
    if not results:
        return "## Top Results\n\n*No results available*\n\n---"

    # Determine scoring metric
    score_key = _pick_score_key(results)
    sorted_results = sorted(
        results, key=lambda r: r.get(score_key, 0), reverse=True
    )[:n]

    param_keys = list(opt.param_space.keys())

    lines = [f"## Top {n} Results (by {score_key})\n"]
    header_cols = ["#"] + param_keys + [score_key]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")

    for i, r in enumerate(sorted_results, 1):
        row = [str(i)]
        for pk in param_keys:
            row.append(str(r.get(pk, "")))
        row.append(_fmt_num(r.get(score_key, 0)))
        lines.append("| " + " | ".join(row) + " |")

    lines.append("\n---")
    return "\n".join(lines)


def _opt_param_sensitivity(opt: OptimizationResult) -> str:
    """Estimate parameter sensitivity by grouping results per parameter."""
    results = opt.all_results
    param_space = opt.param_space
    if not results or not param_space:
        return "## Parameter Sensitivity\n\n*Insufficient data*\n\n---"

    score_key = _pick_score_key(results)
    lines = ["## Parameter Sensitivity\n"]
    lines.append(
        "Parameters ranked by the spread between best and worst score "
        "for each value.\n"
    )
    lines.append("| Parameter | Impact |")
    lines.append("|-----------|--------|")

    sensitivities: dict[str, float] = {}
    for param_name in param_space:
        scores_by_val: dict = defaultdict(list)
        for r in results:
            if param_name in r:
                scores_by_val[r[param_name]].append(
                    r.get(score_key, 0)
                )
        if len(scores_by_val) > 1:
            means = [
                float(np.mean(vals))
                for vals in scores_by_val.values()
            ]
            sensitivities[param_name] = max(means) - min(means)

    for param_name, impact in sorted(
        sensitivities.items(), key=lambda x: x[1], reverse=True
    ):
        if impact > 0.5:
            tag = "HIGH"
        elif impact > 0.2:
            tag = "MEDIUM"
        else:
            tag = "LOW"
        lines.append(f"| `{param_name}` | {impact:.3f} ({tag}) |")

    lines.append("\n---")
    return "\n".join(lines)


def _opt_overfitting_warning(opt: OptimizationResult) -> str:
    results = opt.all_results
    if len(results) < 2:
        return (
            "## Overfitting Check\n\n"
            "*Too few results to assess overfitting risk*\n\n---"
        )

    score_key = _pick_score_key(results)
    sorted_r = sorted(
        results, key=lambda r: r.get(score_key, 0), reverse=True
    )

    best = sorted_r[0].get(score_key, 0)
    second = sorted_r[1].get(score_key, 0)

    if second and abs(best) > 1e-9:
        gap_pct = (best - second) / abs(second) * 100.0
    else:
        gap_pct = 0.0

    lines = ["## Overfitting Check\n"]
    lines.append(f"- Best {score_key}: **{_fmt_num(best)}**")
    lines.append(f"- Second best {score_key}: **{_fmt_num(second)}**")
    lines.append(f"- Gap: **{gap_pct:.1f}%**\n")

    if gap_pct > 30:
        lines.append(
            "**WARNING**: The best result significantly outperforms "
            "the runner-up. This is a strong indicator of overfitting. "
            "The parameters may not generalise to unseen data. "
            "Strongly consider walk-forward validation or out-of-sample "
            "testing before going live."
        )
    elif gap_pct > 15:
        lines.append(
            "**CAUTION**: Moderate gap between best and second best. "
            "Some degree of overfitting is possible. Review the top "
            "parameter sets for consistency."
        )
    else:
        lines.append(
            "The top results are clustered closely together, suggesting "
            "the parameter surface is smooth and the optimum is stable."
        )

    lines.append("\n---")
    return "\n".join(lines)


def _opt_recommendations(opt: OptimizationResult) -> str:
    lines = ["## Recommendations\n"]

    results = opt.all_results
    score_key = _pick_score_key(results) if results else ""
    sorted_r = sorted(
        results, key=lambda r: r.get(score_key, 0), reverse=True
    ) if results else []

    if not results:
        lines.append("- No results to base recommendations on.")
        return "\n".join(lines)

    # Check if best is much better than #2
    if len(sorted_r) >= 2:
        best = sorted_r[0].get(score_key, 0)
        second = sorted_r[1].get(score_key, 0)
        if second and abs(best) > 1e-9:
            gap_pct = (best - second) / abs(second) * 100.0
        else:
            gap_pct = 0.0

        if gap_pct > 30:
            lines.append(
                "- **Run walk-forward analysis** to verify the best "
                "parameters hold up out-of-sample."
            )
            lines.append(
                "- **Consider using the average** of the top 5 parameter "
                "sets instead of the single best to reduce overfitting risk."
            )
        else:
            lines.append(
                "- The parameter surface appears stable. The best "
                "parameters are likely robust."
            )

    lines.append(
        "- **Forward test on a demo account** for at least 2-4 weeks "
        "before committing real capital."
    )
    lines.append(
        "- **Set a kill switch**: if drawdown exceeds 2x the backtest "
        "max drawdown, stop trading and re-evaluate."
    )
    lines.append(
        "- **Document the rationale** for each parameter choice in an "
        "ADR or strategy playbook."
    )

    return "\n".join(lines)


# ===================================================================
# Utility helpers
# ===================================================================


def _sanitise_name(name: str) -> str:
    """Replace characters that are unsafe in filenames."""
    return (
        name.replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .lower()
    )


def _fmt_num(val, decimals: int = 2) -> str:
    """Format a numeric value for display."""
    if isinstance(val, float):
        if np.isinf(val):
            return "INF"
        if np.isnan(val):
            return "N/A"
        return f"{val:,.{decimals}f}"
    return str(val)


def _build_summary_dict(result: BacktestResult, adv: dict) -> dict:
    """Build the JSON summary dict."""
    return {
        "strategy_name": result.strategy_name,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "period": {
            "start": result.start_date,
            "end": result.end_date,
        },
        "performance": {
            "total_trades": result.total_trades,
            "win_trades": result.win_trades,
            "loss_trades": result.loss_trades,
            "win_rate_pct": result.win_rate_pct,
            "profit_factor": result.profit_factor,
            "net_profit_eur": result.net_profit_eur,
            "max_drawdown_pct": result.max_drawdown_pct,
            "max_drawdown_eur": result.max_drawdown_eur,
            "sharpe_ratio": result.sharpe_ratio,
            "expectancy_eur": result.expectancy_eur,
        },
        "advanced": {
            "calmar_ratio": adv.get("calmar_ratio", 0),
            "sortino_ratio": adv.get("sortino_ratio", 0),
            "avg_win_loss_ratio": adv.get("avg_win_loss_ratio", 0),
            "recovery_factor": adv.get("recovery_factor", 0),
            "ulcer_index": adv.get("ulcer_index", 0),
            "upi": adv.get("upi", 0),
            "risk_of_ruin_pct": adv.get("risk_of_ruin_pct", 0),
        },
    }


def _pick_score_key(results: list[dict]) -> str:
    """Pick the best scoring metric to sort by.

    Prefers Sharpe, then profit_factor, then net_profit.
    """
    if not results:
        return ""
    first = results[0]
    for candidate in (
        "sharpe_ratio",
        "profit_factor",
        "net_profit_eur",
        "expectancy_eur",
    ):
        if candidate in first:
            return candidate
    # Fallback: any numeric key
    for k, v in first.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return k
    return ""
