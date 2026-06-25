from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from loguru import logger

from .config import BacktestResult, OptimizationResult, StrategyConfig
from .engine import BacktestEngine


# ---------------------------------------------------------------------------
# Optimizer Configuration
# ---------------------------------------------------------------------------


@dataclass
class OptimizerConfig:
    """Configuration for the optimization run."""

    max_combinations: int = 200
    """Cap total param combos to avoid explosion."""

    scoring_metric: str = "sharpe_ratio"
    """Metric to optimize for.  Valid values:

    - ``sharpe_ratio``
    - ``profit_factor``
    - ``expectancy_eur``
    - ``net_profit_eur``
    - ``win_rate_pct``
    - ``sortino_ratio``
    - ``calmar_ratio``
    """

    min_trades: int = 30
    """Require at least N trades for a result to be considered valid."""

    overfit_threshold_pct: float = 30.0
    """Warn if best result outperforms 2nd-best by more than this %."""


# ---------------------------------------------------------------------------
# Grid Optimizer
# ---------------------------------------------------------------------------


class GridOptimizer:
    """Runs grid search over a parameter space.

    Smart features:

    * If the parameter space is too large (> *max_combinations*), random
      sampling is used instead of an exhaustive grid.
    * Tracks the top 10 results.
    * Detects potential overfitting.
    * Saves all results for later analysis.

    Usage::

        opt = GridOptimizer(OptimizerConfig(max_combinations=100))
        result = opt.optimize(
            strategy_name="ema_trend",
            signal_fn=generate_signal,
            prepare_fn=prepare_data,
            param_space=PARAM_SPACE,
            base_config=StrategyConfig(...),
        )
    """

    _VALID_METRICS = frozenset({
        "sharpe_ratio",
        "profit_factor",
        "expectancy_eur",
        "net_profit_eur",
        "win_rate_pct",
        "sortino_ratio",
        "calmar_ratio",
    })

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        self.config = config or OptimizerConfig()
        if self.config.scoring_metric not in self._VALID_METRICS:
            raise ValueError(
                f"Invalid scoring_metric '{self.config.scoring_metric}'. "
                f"Must be one of: {sorted(self._VALID_METRICS)}"
            )
        self._best_results: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        strategy_name: str,
        signal_fn: Callable,
        prepare_fn: Callable,
        param_space: dict[str, list],
        base_config: StrategyConfig,
        output_dir: str | None = None,
    ) -> OptimizationResult:
        """Run grid search optimization.

        Parameters
        ----------
        strategy_name : str
            Name used in reporting.
        signal_fn : callable
            ``signal_fn(df, bar_index, params) -> direction``
        prepare_fn : callable
            ``prepare_fn(df, params) -> df``  Computes indicators on the
            DataFrame before the backtest starts.
        param_space : dict
            ``{param_name: [value1, value2, ...]}``
        base_config : StrategyConfig
            Base strategy configuration (symbol, timeframes, ...).
        output_dir : str, optional
            Directory to save intermediate results.

        Returns
        -------
        OptimizationResult
        """
        logger.info(
            f"[{strategy_name}] Starting grid optimization "
            f"(metric={self.config.scoring_metric}, "
            f"max_combos={self.config.max_combinations})"
        )

        combinations = self._generate_combinations(param_space)
        logger.info(
            f"[{strategy_name}] Testing {len(combinations)} parameter combinations"
        )

        all_results: list[dict] = []
        self._best_results = []
        best_score = float("-inf")
        best_params: dict = {}
        best_metrics: dict = {}

        engine = BacktestEngine(base_config)

        for idx, combo in enumerate(combinations):
            # Reset engine state for fresh run
            engine._capital = base_config.starting_capital
            engine._peak_equity = base_config.starting_capital

            # Prepare data (indicators) with this param combo
            prepare_fn(None, combo)  # will be called per-run if needed

            result = engine.run(signal_fn, params=combo)

            if result.total_trades < self.config.min_trades:
                logger.debug(
                    f"[{strategy_name}] Skipping combo {idx + 1}: "
                    f"only {result.total_trades} trades (< {self.config.min_trades})"
                )
                continue

            score = self._score_result(result)
            record = {
                **combo,
                "sharpe_ratio": result.sharpe_ratio,
                "profit_factor": result.profit_factor,
                "net_profit_eur": result.net_profit_eur,
                "win_rate_pct": result.win_rate_pct,
                "expectancy_eur": result.expectancy_eur,
                "max_drawdown_pct": result.max_drawdown_pct,
                "total_trades": result.total_trades,
                "score": round(score, 4),
            }
            all_results.append(record)

            # Track best
            if score > best_score:
                best_score = score
                best_params = combo
                best_metrics = {
                    "score": round(score, 4),
                    "sharpe_ratio": result.sharpe_ratio,
                    "profit_factor": result.profit_factor,
                    "net_profit_eur": result.net_profit_eur,
                    "win_rate_pct": result.win_rate_pct,
                    "expectancy_eur": result.expectancy_eur,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "total_trades": result.total_trades,
                }

            # Keep top 10
            self._best_results.append(record)
            self._best_results.sort(key=lambda r: r["score"], reverse=True)
            self._best_results = self._best_results[:10]

            if (idx + 1) % 10 == 0 or idx == len(combinations) - 1:
                logger.info(
                    f"[{strategy_name}] Progress: {idx + 1}/{len(combinations)} "
                    f"| best {self.config.scoring_metric}={best_score:.4f}"
                )

        # Sort all results by score descending
        all_results.sort(key=lambda r: r["score"], reverse=True)

        if not best_params:
            logger.warning(f"[{strategy_name}] No valid results found!")
            return OptimizationResult(
                best_params={},
                best_metrics={},
                all_results=all_results,
                param_space={k: [str(v) for v in vals]
                             for k, vals in param_space.items()},
            )

        overfit = self._detect_overfitting(all_results)

        logger.success(
            f"[{strategy_name}] Optimization complete. "
            f"Best {self.config.scoring_metric}: {best_score:.4f}"
        )
        if overfit["warning"]:
            logger.warning(f"[{strategy_name}] OVERFITTING WARNING: {overfit['warning']}")

        # Save results if output_dir provided
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            json_path = out / f"{_sanitise_name(strategy_name)}_opt_results.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "best_params": best_params,
                    "best_metrics": best_metrics,
                    "all_results": all_results,
                    "param_space": {k: [str(v) for v in vals]
                                    for k, vals in param_space.items()},
                    "overfitting": overfit,
                }, f, indent=2, default=str)
            logger.info(f"[{strategy_name}] Results saved to {json_path}")

        return OptimizationResult(
            best_params=best_params,
            best_metrics=best_metrics,
            all_results=all_results,
            param_space={k: [str(v) for v in vals]
                         for k, vals in param_space.items()},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_combinations(self, param_space: dict) -> list[dict]:
        """Generate parameter combinations, random-sampling if too many.

        Computes the Cartesian product of all parameter values.  If the
        total exceeds *max_combinations*, samples randomly without
        replacement.
        """
        keys = list(param_space.keys())
        values = list(param_space.values())

        total = 1
        for v in values:
            total *= len(v)

        if total == 0:
            return []

        if total <= self.config.max_combinations:
            # Exhaustive grid
            combos = []
            for prod in _cartesian_product(values):
                combos.append(dict(zip(keys, prod)))
            return combos

        # Random sampling
        logger.warning(
            f"Parameter space has {total} combinations "
            f"> {self.config.max_combinations} max. "
            f"Sampling {self.config.max_combinations} randomly."
        )

        # Generate indices for the full grid and sample
        indices = list(range(total))
        sampled = random.sample(indices, self.config.max_combinations)

        # Pre-compute strides for index-to-combo mapping
        strides = [1]
        for v in reversed(values[1:]):
            strides.append(strides[-1] * len(v))
        strides.reverse()

        combos = []
        for idx in sampled:
            combo = {}
            remaining = idx
            for k, stride, val_list in zip(keys, strides, values):
                pos = remaining // stride
                combo[k] = val_list[pos]
                remaining %= stride
            combos.append(combo)

        return combos

    def _score_result(self, result: BacktestResult) -> float:
        """Score a result based on the configured scoring metric."""
        # Import advanced metrics for sortino/calmar
        from .metrics import compute_advanced_metrics

        metric = self.config.scoring_metric
        adv = compute_advanced_metrics(result)

        if metric == "sharpe_ratio":
            return float(result.sharpe_ratio)
        if metric == "profit_factor":
            return float(result.profit_factor)
        if metric == "expectancy_eur":
            return float(result.expectancy_eur)
        if metric == "net_profit_eur":
            return float(result.net_profit_eur)
        if metric == "win_rate_pct":
            return float(result.win_rate_pct)
        if metric == "sortino_ratio":
            return float(adv.get("sortino_ratio", 0))
        if metric == "calmar_ratio":
            val = adv.get("calmar_ratio", 0)
            if isinstance(val, float) and np.isinf(val):
                return 999.0  # cap infinite calmar
            return float(val)

        return 0.0

    def _detect_overfitting(self, results: list[dict]) -> dict:
        """Check for overfitting signs.

        Warning flags:

        * Best result significantly better than 2nd-best
          (> *overfit_threshold_pct* %).
        * Very few trades (< 50).
        * Win rate > 80 % (too good to be true for most strategies).
        * Profit factor > 5.0 (suspicious).

        Returns a dict with ``warning`` (str) and ``flags`` (list[str]).
        """
        flags: list[str] = []
        warning = ""

        if len(results) < 2:
            return {"warning": "Not enough results to check overfitting", "flags": flags}

        best = results[0]
        second = results[1]

        # 1. Best vs 2nd-best gap
        best_score = best.get("score", 0)
        second_score = second.get("score", 0)
        if second_score > 0:
            gap_pct = (best_score - second_score) / abs(second_score) * 100.0
            if gap_pct > self.config.overfit_threshold_pct:
                flags.append(
                    f"Best score ({best_score:.4f}) is {gap_pct:.1f}% better "
                    f"than 2nd-best ({second_score:.4f})"
                )

        # 2. Few trades
        if best.get("total_trades", 0) < 50:
            flags.append(
                f"Only {best.get('total_trades', 0)} trades - "
                f"not statistically significant"
            )

        # 3. Win rate too high
        if best.get("win_rate_pct", 0) > 80:
            flags.append(
                f"Win rate {best.get('win_rate_pct', 0):.1f}% is suspiciously high"
            )

        # 4. Profit factor too high
        if best.get("profit_factor", 0) > 5.0:
            flags.append(
                f"Profit factor {best.get('profit_factor', 0):.2f} is suspiciously high"
            )

        if flags:
            warning = "; ".join(flags)

        return {"warning": warning, "flags": flags}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cartesian_product(lists: list[list]) -> list[tuple]:
    """Recursive Cartesian product (avoids itertools for clarity)."""
    if not lists:
        return [()]
    result: list[tuple] = []
    for item in lists[0]:
        for rest in _cartesian_product(lists[1:]):
            result.append((item, *rest))
    return result


def _sanitise_name(name: str) -> str:
    """Sanitise a strategy name for use in filenames."""
    return name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
