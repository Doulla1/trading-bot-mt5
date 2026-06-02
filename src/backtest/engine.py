"""Moteur de backtesting principal - boucle barre-par-barre.

Ties together HistoricalDataSource, SimulatedExecutor, StrategyAdapter,
and RuleEngine to run a full backtest against historical CSV data.
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.backtest.data_source import HistoricalDataSource
from src.backtest.rules_engine import RuleEngine
from src.backtest.simulated_executor import SimulatedExecutor
from src.backtest.strategy_adapter import StrategyAdapter
from src.mt5.indicators import compute_all


# ---------------------------------------------------------------------------
# BacktestEngine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Main backtesting engine.

    Loads historical data for multiple symbols, runs a bar-by-bar simulation,
    and returns aggregated results.

    Parameters
    ----------
    symbols_config : list[dict]
        List of symbol configurations. Each dict must contain:
        ``symbol``, ``timeframe``, ``magic``, ``interval_min``.
    start_date : str
        Start date in "YYYY-MM-DD" format.
    end_date : str
        End date in "YYYY-MM-DD" format.
    initial_balance : float
        Starting account balance for the simulation.
    rule_engine : RuleEngine or None
        Pre-configured rule engine. If None, a default one is created.
    data_dir : str
        Directory containing historical CSV files, organised as
        ``{symbol_lower}/{symbol_lower}_{timeframe}_{year}-{month}.csv``.
    """

    def __init__(
        self,
        symbols_config: list[dict],
        start_date: str,
        end_date: str,
        initial_balance: float = 10000.0,
        rule_engine: RuleEngine | None = None,
        data_dir: str = "data/historical",
    ) -> None:
        self.symbols_config = symbols_config
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.data_dir = Path(data_dir)

        self.rule_engine = rule_engine if rule_engine is not None else RuleEngine()

        # Per-symbol components: {symbol: {source, executor, strategy, interval_min, ...}}
        self.symbols: dict[str, dict[str, Any]] = {}

        self._init_components()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        """Create data sources, executors, and strategy adapters for each symbol."""
        for cfg in self.symbols_config:
            sym = cfg["symbol"]
            timeframe = cfg["timeframe"]
            magic = cfg["magic"]
            interval_min = cfg["interval_min"]
            sym_lower = sym.lower()

            # Build CSV path: data/historical/eurusd/eurusd_M15_2024-01.csv
            # We use start_date to derive year-month for the filename.
            start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            csv_filename = f"{sym_lower}_{timeframe}_{start_dt.year}-{start_dt.month:02d}.csv"
            csv_path = self.data_dir / sym_lower / csv_filename

            # Create data source
            source = HistoricalDataSource(
                csv_path=str(csv_path),
                symbol=sym,
                initial_balance=self.initial_balance,
            )
            source.load_data()

            # Get point from source
            symbol_info = source.get_symbol_info()
            point = float(symbol_info["point"])

            # Create executor
            executor = SimulatedExecutor(
                initial_balance=self.initial_balance,
                point=point,
                magic=magic,
            )

            # Create strategy adapter
            strategy = StrategyAdapter(executor=executor)

            self.symbols[sym] = {
                "source": source,
                "executor": executor,
                "strategy": strategy,
                "interval_min": interval_min,
                "timeframe": timeframe,
                "point": point,
                "magic": magic,
            }

            logger.info(
                f"[{sym}] Initialise: {source.get_bar_count()} barres "
                f"depuis {csv_filename}, point={point}"
            )

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Execute the backtest across all configured symbols.

        Each symbol is processed independently, bar-by-bar. For each bar:
        1. Check SL/TP hits (bar high/low)
        2. Apply position management (breakeven, trailing, time exit)
        3. If analysis interval matches, compute indicators and evaluate

        Returns
        -------
        dict
            ``{symbol: {"executor": SimulatedExecutor, "source": HistoricalDataSource}}``
        """
        all_results: dict[str, dict] = {}

        for sym, components in self.symbols.items():
            logger.info(f"=== Backtest {sym} ===")

            source: HistoricalDataSource = components["source"]
            executor: SimulatedExecutor = components["executor"]
            strategy: StrategyAdapter = components["strategy"]
            interval_min: int = components["interval_min"]
            point: float = components["point"]

            df = source.get_dataframe()

            if len(df) < 200:
                logger.warning(
                    f"[{sym}] Pas assez de donnees ({len(df)} barres), "
                    f"minimum 200 requis"
                )
                all_results[sym] = {"executor": executor, "source": source}
                continue

            # Warm-up: we need 200 bars for indicators
            for i in range(200, len(df)):
                bar = df.iloc[i]
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])
                bar_close = float(bar["close"])
                bar_time = str(bar["datetime"])

                # ---- 1. Check SL/TP hits ----
                sl_tp_results = executor.check_sl_tp(
                    bar_high, bar_low, bar_close, bar_time
                )
                for res in sl_tp_results:
                    if res.success:
                        logger.debug(
                            f"[{sym}] {res.comment} ticket={res.ticket} "
                            f"@ {res.price}"
                        )

                # ---- 2. Position management ----
                strategy.manage_open_positions(
                    bar_close, bar_time, point=point
                )

                # ---- 3. Analysis cycle ----
                first_bar_time = str(df.iloc[0]["datetime"])
                minutes_from_start = (
                    pd.Timestamp(bar_time) - pd.Timestamp(first_bar_time)
                ).total_seconds() / 60.0

                if minutes_from_start % interval_min == 0:
                    # Get indicator data: last 200 bars
                    start_idx = max(0, i - 200)
                    df_slice = df.iloc[start_idx : i + 1].copy()

                    indicators = compute_all(df_slice)
                    if not indicators:
                        continue

                    # Ensure current_price is set
                    if "current_price" not in indicators:
                        indicators["current_price"] = bar_close

                    # Rule engine decision
                    decision = self.rule_engine.evaluate(indicators)

                    # Execute via strategy adapter
                    strategy.execute_decision(
                        decision=decision,
                        symbol=sym,
                        current_price=bar_close,
                        bar_datetime=bar_time,
                        point=point,
                        indicators=indicators,
                    )

            # ---- Close all remaining positions at end of test ----
            final_bar = df.iloc[-1]
            final_close = float(final_bar["close"])
            final_time = str(final_bar["datetime"])

            for pos in executor.get_open_positions():
                executor.close_position(
                    pos["ticket"], final_close, final_time, "END_OF_TEST"
                )
                logger.info(
                    f"[{sym}] Fermeture fin de test: ticket={pos['ticket']}"
                )

            # ---- Summary ----
            closed = executor.get_closed_trades()
            total_profit = sum(t.profit for t in closed)
            wins = sum(1 for t in closed if t.profit > 0)
            losses = sum(1 for t in closed if t.profit < 0)
            win_rate = (wins / len(closed) * 100) if closed else 0.0

            logger.info(
                f"[{sym}] Resultats: {len(closed)} trades, "
                f"win_rate={win_rate:.1f}%, "
                f"profit_total={total_profit:.2f}$, "
                f"balance_finale={executor.balance:.2f}$, "
                f"commission={executor.total_commission:.2f}$"
            )

            all_results[sym] = {"executor": executor, "source": source}

        return all_results

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    def get_summary(self) -> pd.DataFrame:
        """Return a summary DataFrame with one row per symbol."""
        rows: list[dict] = []
        for sym, components in self.symbols.items():
            executor: SimulatedExecutor = components["executor"]
            closed = executor.get_closed_trades()
            total_profit = sum(t.profit for t in closed)
            wins = sum(1 for t in closed if t.profit > 0)
            losses = sum(1 for t in closed if t.profit < 0)
            win_rate = (wins / len(closed) * 100) if closed else 0.0

            rows.append({
                "symbol": sym,
                "trades": len(closed),
                "wins": wins,
                "losses": losses,
                "win_rate_pct": round(win_rate, 1),
                "total_profit": round(total_profit, 2),
                "final_balance": round(executor.balance, 2),
                "commission": round(executor.total_commission, 2),
            })

        return pd.DataFrame(rows)

    def export_trades(self, symbol: str) -> pd.DataFrame:
        """Export closed trades for a single symbol as a DataFrame."""
        if symbol not in self.symbols:
            raise KeyError(f"Symbol {symbol} not found in backtest results")

        executor: SimulatedExecutor = self.symbols[symbol]["executor"]
        trades = executor.get_closed_trades()

        return pd.DataFrame([
            {
                "ticket": t.ticket,
                "symbol": t.symbol,
                "direction": t.direction,
                "volume": t.volume,
                "open_price": t.open_price,
                "close_price": t.close_price,
                "open_time": t.open_time,
                "close_time": t.close_time,
                "profit": round(t.profit, 2),
                "exit_reason": t.exit_reason,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
            }
            for t in trades
        ])
