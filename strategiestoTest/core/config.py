from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Strategy Configuration
# ---------------------------------------------------------------------------

@dataclass
class StrategyConfig:
    """Base config for any strategy.

    All risk/trade-management parameters have sensible defaults so that a
    strategy author only needs to specify ``name``, ``symbol`` and
    ``timeframes`` to get started.
    """

    name: str
    symbol: str                       # e.g. "EURUSD"
    timeframes: list[str]             # e.g. ["M15", "D1"]

    # --- capital & risk ---
    starting_capital: float = 1000.0
    risk_per_trade_pct: float = 0.01  # 1 % of capital per trade
    max_positions: int = 1

    # --- execution costs ---
    commission_pips: float = 0.0
    slippage_pips: float = 1.0
    spread_pips: float = 1.5

    # --- trade management ---
    use_trailing_stop: bool = True
    trailing_activation_r: float = 1.0   # activate trailing at 1R profit
    trailing_distance_r: float = 0.5     # trail at 0.5R behind price
    breakeven_activation_r: float = 0.7  # move SL to entry at 0.7R profit
    time_exit_bars: int = 0              # 0 = disabled

    # --- date range ---
    start_date: str = ""               # YYYY-MM-DD, empty = 365 days ago
    end_date: str = ""                 # YYYY-MM-DD, empty = now

    # --- session / filter ---
    session_filter: str = ""           # "asian", "london", "ny", "" = all
    trend_filter_ema: int = 0          # 0 = disabled, e.g. 200 for EMA200
    min_atr_pips: float = 0.0          # minimum ATR (in pips) to allow a trade
    max_spread_pips: float = 5.0       # maximum spread to allow a trade

    def to_dict(self) -> dict:
        """Return a plain dict suitable for serialisation / reporting."""
        return {
            "name": self.name,
            "symbol": self.symbol,
            "timeframes": self.timeframes,
            "starting_capital": self.starting_capital,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_positions": self.max_positions,
            "commission_pips": self.commission_pips,
            "slippage_pips": self.slippage_pips,
            "spread_pips": self.spread_pips,
            "use_trailing_stop": self.use_trailing_stop,
            "trailing_activation_r": self.trailing_activation_r,
            "trailing_distance_r": self.trailing_distance_r,
            "breakeven_activation_r": self.breakeven_activation_r,
            "time_exit_bars": self.time_exit_bars,
            "session_filter": self.session_filter,
            "trend_filter_ema": self.trend_filter_ema,
            "min_atr_pips": self.min_atr_pips,
            "max_spread_pips": self.max_spread_pips,
        }


# ---------------------------------------------------------------------------
# Result Data Classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Full backtest result produced by a single strategy run."""

    strategy_name: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str

    # --- trade counts ---
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate_pct: float = 0.0

    # --- profit metrics ---
    profit_factor: float = 0.0
    total_profit_eur: float = 0.0
    total_loss_eur: float = 0.0
    net_profit_eur: float = 0.0

    # --- drawdown ---
    max_drawdown_pct: float = 0.0
    max_drawdown_eur: float = 0.0

    # --- per-trade stats ---
    avg_win_eur: float = 0.0
    avg_loss_eur: float = 0.0
    expectancy_eur: float = 0.0
    sharpe_ratio: float = 0.0
    avg_rr_ratio: float = 0.0
    avg_bars_held: float = 0.0

    # --- detailed data ---
    exit_reasons: dict = field(default_factory=dict)   # {"SL": 10, "TP": 5, ...}
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)  # [{bar_idx, equity, drawdown_pct}]
    params: dict = field(default_factory=dict)               # strategy params snapshot

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict for export / reporting."""
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_trades": self.total_trades,
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "total_profit_eur": self.total_profit_eur,
            "total_loss_eur": self.total_loss_eur,
            "net_profit_eur": self.net_profit_eur,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_eur": self.max_drawdown_eur,
            "avg_win_eur": self.avg_win_eur,
            "avg_loss_eur": self.avg_loss_eur,
            "expectancy_eur": self.expectancy_eur,
            "sharpe_ratio": self.sharpe_ratio,
            "avg_rr_ratio": self.avg_rr_ratio,
            "avg_bars_held": self.avg_bars_held,
            "exit_reasons": self.exit_reasons,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "params": self.params,
        }


@dataclass
class OptimizationResult:
    """Result of a parameter-optimisation sweep."""

    best_params: dict = field(default_factory=dict)
    best_metrics: dict = field(default_factory=dict)
    all_results: list[dict] = field(default_factory=list)
    param_space: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "all_results": self.all_results,
            "param_space": self.param_space,
        }
