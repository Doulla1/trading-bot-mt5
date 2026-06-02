"""Optimiseur par grid search pour le backtesteur."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.backtest.engine import BacktestEngine
from src.backtest.rules_engine import DEFAULT_WEIGHTS, RuleEngine


# ============================================================
# Preset weight configurations
# ============================================================

# Aggressive trend-following: higher weights on trend signals
AGGRESSIVE_TREND_WEIGHTS = DEFAULT_WEIGHTS.copy()
AGGRESSIVE_TREND_WEIGHTS.update({
    "price_above_sma20": 20,
    "price_above_cloud": 25,
    "macd_above_signal": 15,
    "adx_di_plus_strong": 15,
})

# Conservative mean-reversion: higher weights on RSI, Bollinger
MEAN_REVERSION_WEIGHTS = DEFAULT_WEIGHTS.copy()
MEAN_REVERSION_WEIGHTS.update({
    "rsi_oversold": 25,
    "rsi_overbought": -25,
    "bb_near_lower": 20,
    "bb_near_upper": -20,
    "near_support": 15,
    "near_resistance": -15,
})

# Pattern-focused: higher weights on candlesticks and structure
PATTERN_WEIGHTS = DEFAULT_WEIGHTS.copy()
PATTERN_WEIGHTS.update({
    "bullish_pattern": 25,
    "bearish_pattern": -25,
    "higher_high_higher_low": 15,
    "lower_high_lower_low": -15,
})


# ============================================================
# BacktestMetrics - lightweight metrics container
# (Defined here until src.backtest.report is created)
# ============================================================

@dataclass
class BacktestMetrics:
    """Aggregated performance metrics from a backtest run."""

    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    win_rate: float = 0.0
    return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    final_balance: float = 0.0
    initial_balance: float = 0.0


# ============================================================
# OptimizationResult
# ============================================================

@dataclass
class OptimizationResult:
    """Result of a single optimization run."""

    params: dict
    metrics: BacktestMetrics
    rank: int = 0


# ============================================================
# Metrics computation helpers
# ============================================================

def _compute_metrics(results: dict[str, Any], initial_balance: float) -> BacktestMetrics:
    """Compute aggregated BacktestMetrics from engine.run() output.

    Parameters
    ----------
    results : dict
        Output of ``BacktestEngine.run()``, mapping symbol ->
        ``{"executor": SimulatedExecutor, "source": HistoricalDataSource}``.
    initial_balance : float
        Starting balance used to compute return percentages.
    """
    all_trades: list[Any] = []
    for sym, comps in results.items():
        executor = comps["executor"]
        all_trades.extend(executor.get_closed_trades())

    total_trades = len(all_trades)
    if total_trades == 0:
        return BacktestMetrics(initial_balance=initial_balance)

    profits = [t.profit for t in all_trades]
    net_profit = sum(profits)

    winning_trades = [t.profit for t in all_trades if t.profit > 0]
    losing_trades = [t.profit for t in all_trades if t.profit < 0]

    wins = len(winning_trades)
    losses = len(losing_trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    gross_profit = sum(winning_trades) if winning_trades else 0.0
    gross_loss = abs(sum(losing_trades)) if losing_trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    avg_win = gross_profit / wins if wins > 0 else 0.0
    avg_loss = gross_loss / losses if losses > 0 else 0.0

    return_pct = (net_profit / initial_balance * 100) if initial_balance > 0 else 0.0

    # Sharpe ratio: mean(profit) / std(profit), annualized loosely
    if len(profits) > 1:
        mean_profit = float(pd.Series(profits).mean())
        std_profit = float(pd.Series(profits).std())
        sharpe_ratio = (mean_profit / std_profit * math.sqrt(len(profits))) if std_profit > 0 else 0.0
        # Sortino: only downside deviation
        downside = [p for p in profits if p < 0]
        if downside:
            downside_std = float(pd.Series(downside).std())
            sortino_ratio = (mean_profit / downside_std * math.sqrt(len(profits))) if downside_std > 0 else 0.0
        else:
            sortino_ratio = 0.0
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    # Max drawdown from cumulative P&L
    cumsum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in profits:
        cumsum += p
        if cumsum > peak:
            peak = cumsum
        dd = peak - cumsum
        if dd > max_dd:
            max_dd = dd
    max_drawdown_pct = (max_dd / initial_balance * 100) if initial_balance > 0 else 0.0

    # Final balance from last symbol's executor (aggregate approximation)
    final_balance = initial_balance + net_profit

    return BacktestMetrics(
        net_profit=round(net_profit, 2),
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        profit_factor=round(profit_factor, 4),
        sharpe_ratio=round(sharpe_ratio, 4),
        sortino_ratio=round(sortino_ratio, 4),
        win_rate=round(win_rate, 2),
        return_pct=round(return_pct, 2),
        max_drawdown_pct=round(max_drawdown_pct, 2),
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        final_balance=round(final_balance, 2),
        initial_balance=initial_balance,
    )


# ============================================================
# GridOptimizer
# ============================================================

class GridOptimizer:
    """Grid search optimizer for backtest parameter tuning.

    Exhaustively tests all combinations of a parameter grid, ranks them
    by a chosen metric, and surfaces the best configuration.

    Parameters
    ----------
    symbols_config : list[dict]
        Same format as ``run_multi.py``. Each dict must have:
        ``symbol``, ``timeframe``, ``magic``, ``interval_min``.
    start_date : str
        Backtest start date ``"YYYY-MM-DD"``.
    end_date : str
        Backtest end date ``"YYYY-MM-DD"``.
    initial_balance : float
        Starting account balance.
    data_dir : str
        Path to the folder containing historical CSV files.
    metric : str
        Target metric to optimize. One of:
        ``"profit_factor"``, ``"sharpe_ratio"``, ``"net_profit"``,
        ``"win_rate"``, ``"sortino_ratio"``, ``"return_pct"``.
    """

    VALID_METRICS = frozenset({
        "profit_factor", "sharpe_ratio", "net_profit",
        "win_rate", "sortino_ratio", "return_pct",
    })

    # Parameters that belong to the RuleEngine constructor
    RULE_ENGINE_PARAMS = frozenset({
        "buy_threshold", "sell_threshold", "sl_atr_mult", "tp_atr_mult",
    })

    # Parameters that belong to the StrategyAdapter constructor
    STRATEGY_PARAMS = frozenset({
        "max_risk_per_trade_pct", "max_daily_loss_pct",
        "max_open_positions", "min_confidence_threshold",
        "max_spread_points", "consecutive_loss_limit",
        "circuit_breaker_hours",
    })

    def __init__(
        self,
        symbols_config: list[dict],
        start_date: str,
        end_date: str,
        initial_balance: float = 10000.0,
        data_dir: str = "data/historical",
        metric: str = "profit_factor",
    ) -> None:
        if metric not in self.VALID_METRICS:
            raise ValueError(
                f"Metric invalid: {metric!r}. Options: "
                f"{sorted(self.VALID_METRICS)}"
            )

        self.symbols_config = symbols_config
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.data_dir = data_dir
        self.metric = metric

    # ----------------------------------------------------------------
    # Grid generation
    # ----------------------------------------------------------------

    def define_grid(self, param_grid: dict) -> list[dict]:
        """Expand a parameter grid into all combinations (cartesian product).

        Parameters
        ----------
        param_grid : dict
            Parameter names mapped to lists of candidate values.

        Returns
        -------
        list[dict]
            One dict per combination, e.g.
            ``[{"buy_threshold": 20, "sell_threshold": 20, ...}, ...]``.
        """
        if not param_grid:
            return [{}]

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        return [dict(zip(keys, combo)) for combo in combinations]

    # ----------------------------------------------------------------
    # Main optimization loop
    # ----------------------------------------------------------------

    def run(
        self,
        param_grid: dict,
        max_workers: int = 1,
    ) -> list[OptimizationResult]:
        """Execute grid search over every parameter combination.

        For each combination a fresh ``RuleEngine`` and ``BacktestEngine``
        are created, the backtest is run, metrics are computed, and results
        are ranked by the target metric (descending).

        Parameters
        ----------
        param_grid : dict
            See :meth:`define_grid`.
        max_workers : int
            Reserved for future parallel execution. Currently ignored.

        Returns
        -------
        list[OptimizationResult]
            Ranked list (rank 1 = best).
        """
        combinations = self.define_grid(param_grid)
        total = len(combinations)

        logger.info(
            f"GridOptimizer: {total} combinaisons a tester "
            f"(metrique: {self.metric})"
        )

        results: list[OptimizationResult] = []

        for idx, params in enumerate(combinations, start=1):
            logger.info(
                f"[{idx}/{total}] Test: {params}"
            )

            try:
                metrics = self._run_single(params)
                results.append(OptimizationResult(
                    params=dict(params),
                    metrics=metrics,
                ))
            except Exception as exc:
                logger.error(
                    f"[{idx}/{total}] Echec pour {params}: {exc}"
                )
                # Still record a zero-metrics entry so the grid is complete
                results.append(OptimizationResult(
                    params=dict(params),
                    metrics=BacktestMetrics(initial_balance=self.initial_balance),
                ))

        # Rank by target metric (descending)
        results.sort(
            key=lambda r: getattr(r.metrics, self.metric),
            reverse=True,
        )
        for rank, r in enumerate(results, start=1):
            r.rank = rank

        logger.info(
            f"GridOptimizer: termine. Meilleur = {self.metric}="
            f"{getattr(results[0].metrics, self.metric) if results else 'N/A'}"
        )

        return results

    # ----------------------------------------------------------------
    # Single-run helper
    # ----------------------------------------------------------------

    def _run_single(self, params: dict) -> BacktestMetrics:
        """Create engines with the given params, run, and compute metrics."""
        # Split params into rule-engine params, strategy params, and weights
        rule_params: dict[str, Any] = {}
        strategy_params: dict[str, Any] = {}
        weights: dict[str, int] | None = None

        for key, value in params.items():
            if key == "weights":
                weights = value
            elif key in self.RULE_ENGINE_PARAMS:
                rule_params[key] = value
            elif key in self.STRATEGY_PARAMS:
                strategy_params[key] = value

        # Build RuleEngine
        if weights is not None:
            rule_params["weights"] = weights
        rule_engine = RuleEngine(**rule_params)

        # Build and run BacktestEngine
        engine = BacktestEngine(
            symbols_config=self.symbols_config,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_balance=self.initial_balance,
            rule_engine=rule_engine,
            data_dir=self.data_dir,
        )

        # Apply strategy parameters by patching each symbol's strategy adapter
        if strategy_params:
            for _sym, comps in engine.symbols.items():
                strategy = comps["strategy"]
                for attr, val in strategy_params.items():
                    if hasattr(strategy, attr):
                        setattr(strategy, attr, val)

        raw_results = engine.run()
        return _compute_metrics(raw_results, self.initial_balance)

    # ----------------------------------------------------------------
    # Result formatting
    # ----------------------------------------------------------------

    def to_dataframe(self, results: list[OptimizationResult]) -> pd.DataFrame:
        """Convert optimization results to a sorted DataFrame.

        Columns: rank, every param name, and every metric field.
        """
        if not results:
            return pd.DataFrame()

        rows: list[dict] = []
        for r in results:
            row: dict = {"rank": r.rank}
            row.update(r.params)
            m = r.metrics
            row.update({
                "net_profit": m.net_profit,
                "profit_factor": m.profit_factor,
                "sharpe_ratio": m.sharpe_ratio,
                "sortino_ratio": m.sortino_ratio,
                "win_rate": m.win_rate,
                "return_pct": m.return_pct,
                "max_drawdown_pct": m.max_drawdown_pct,
                "total_trades": m.total_trades,
                "wins": m.wins,
                "losses": m.losses,
                "avg_win": m.avg_win,
                "avg_loss": m.avg_loss,
                "final_balance": m.final_balance,
            })
            rows.append(row)

        df = pd.DataFrame(rows)
        return df.sort_values("rank").reset_index(drop=True)

    def save_results(
        self,
        results: list[OptimizationResult],
        output_path: str,
    ) -> None:
        """Save optimization results as JSON.

        Parameters
        ----------
        results : list[OptimizationResult]
            Ranked results from :meth:`run`.
        output_path : str
            Destination file path (``.json``).
        """
        payload: dict[str, Any] = {
            "config": {
                "symbols": self.symbols_config,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "initial_balance": self.initial_balance,
                "metric": self.metric,
            },
            "results": [],
        }

        for r in results:
            payload["results"].append({
                "rank": r.rank,
                "params": r.params,
                "metrics": {
                    "net_profit": r.metrics.net_profit,
                    "profit_factor": r.metrics.profit_factor,
                    "sharpe_ratio": r.metrics.sharpe_ratio,
                    "sortino_ratio": r.metrics.sortino_ratio,
                    "win_rate": r.metrics.win_rate,
                    "return_pct": r.metrics.return_pct,
                    "max_drawdown_pct": r.metrics.max_drawdown_pct,
                    "total_trades": r.metrics.total_trades,
                    "wins": r.metrics.wins,
                    "losses": r.metrics.losses,
                    "avg_win": r.metrics.avg_win,
                    "avg_loss": r.metrics.avg_loss,
                    "final_balance": r.metrics.final_balance,
                },
            })

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Resultats sauvegardes -> {out}")

    def best_params(self, results: list[OptimizationResult]) -> dict:
        """Return the parameter dict of the top-ranked result.

        Returns an empty dict if ``results`` is empty.
        """
        if not results:
            return {}
        return dict(results[0].params)

    def print_top(self, results: list[OptimizationResult], n: int = 10) -> None:
        """Print a formatted table of the top N optimization results."""
        if not results:
            print("(aucun resultat)")
            return

        top = results[:n]

        # Determine which param columns to display (skip "weights" for brevity)
        all_param_keys: list[str] = []
        for r in top:
            for k in r.params:
                if k != "weights" and k not in all_param_keys:
                    all_param_keys.append(k)

        # Build header
        param_headers = [k.replace("_", " ")[:8] for k in all_param_keys]
        metric_headers = ["Profit Factor", "Sharpe", "Win Rate", "Return%"]
        header = (
            ["Rank"]
            + param_headers
            + metric_headers
        )

        # Build rows
        rows: list[list[str]] = []
        for r in top:
            row = [str(r.rank)]
            for k in all_param_keys:
                val = r.params.get(k, "")
                if isinstance(val, float):
                    row.append(f"{val:.1f}")
                else:
                    row.append(str(val))
            m = r.metrics
            row.append(f"{m.profit_factor:.2f}")
            row.append(f"{m.sharpe_ratio:.2f}")
            row.append(f"{m.win_rate:.1f}%")
            row.append(f"{m.return_pct:+.1f}%")
            rows.append(row)

        # Column widths
        col_widths: list[int] = []
        for c in range(len(header)):
            max_w = len(header[c])
            for row in rows:
                if c < len(row):
                    max_w = max(max_w, len(row[c]))
            col_widths.append(max_w + 2)

        # Format
        def fmt_row(cols: list[str]) -> str:
            parts = []
            for i, cell in enumerate(cols):
                parts.append(cell.center(col_widths[i]))
            return "|".join(parts)

        print(f"\nTop {n} Optimizations (sorted by {self.metric}):")
        print(fmt_row(header))
        print("-" * sum(col_widths))
        for row in rows:
            print(fmt_row(row))
        print()


# ============================================================
# YAML / JSON loader
# ============================================================

def optimize_from_yaml(config_path: str) -> list[OptimizationResult]:
    """Load optimization config from YAML or JSON and run it.

    Expected config format::

        {
            "symbols": [
                {"symbol": "EURUSD", "timeframe": "M15",
                 "magic": 73456, "interval_min": 15}
            ],
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "initial_balance": 10000,
            "data_dir": "data/historical",
            "metric": "profit_factor",
            "param_grid": {
                "buy_threshold": [20, 25, 30],
                "sell_threshold": [20, 25, 30],
                "sl_atr_mult": [1.0, 1.5, 2.0],
                "tp_atr_mult": [2.0, 2.5, 3.0],
                "max_risk_per_trade_pct": [0.5, 1.0, 1.5]
            }
        }

    Parameters
    ----------
    config_path : str
        Path to a ``.yaml``, ``.yml``, or ``.json`` file.

    Returns
    -------
    list[OptimizationResult]
        Ranked optimization results.
    """
    path = Path(config_path)

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]

            with path.open("r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh)
        except ImportError:
            # Fall back to JSON with a helpful message
            logger.warning(
                "PyYAML non installe - essai de lecture JSON pour "
                f"{path.name}"
            )
            cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        cfg = json.loads(path.read_text(encoding="utf-8"))

    # Extract top-level keys
    symbols = cfg.get("symbols", cfg.get("symbols_config", []))
    start_date = cfg["start_date"]
    end_date = cfg["end_date"]
    initial_balance = cfg.get("initial_balance", 10000.0)
    data_dir = cfg.get("data_dir", "data/historical")
    metric = cfg.get("metric", "profit_factor")
    param_grid = cfg["param_grid"]

    optimizer = GridOptimizer(
        symbols_config=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance,
        data_dir=data_dir,
        metric=metric,
    )

    results = optimizer.run(param_grid=param_grid)
    optimizer.print_top(results)

    return results
