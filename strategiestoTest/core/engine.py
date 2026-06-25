"""
Central backtest engine - bar-by-bar simulation for a single strategy on a single symbol.

Usage::

    from strategiestoTest.core.config import StrategyConfig
    from strategiestoTest.core.engine import BacktestEngine

    config = StrategyConfig(name="my_strat", symbol="EURUSD", timeframes=["M15"])
    engine = BacktestEngine(config)

    def my_signal(df, i, params):
        ...

    result = engine.run(my_signal, params={"rsi_period": 14})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger

from .config import BacktestResult, StrategyConfig
from .data_loader import get_pip_size, get_pip_value, load_data

# ---------------------------------------------------------------------------
# Timeframe helpers
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

_XAU_SYMBOLS: set[str] = {"XAUUSD", "GOLD"}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Position:
    """Open position state during simulation."""

    entry_time: datetime
    entry_price: float
    direction: int  # 1=BUY, -1=SELL
    volume: float
    stop_loss: float
    take_profit: float
    highest_favorable: float
    entry_bar: int
    bars_held: int = 0
    trailing_activated: bool = False
    breakeven_activated: bool = False


@dataclass
class ClosedTrade:
    """Record of a completed trade."""

    entry_time: datetime
    exit_time: datetime
    direction: int
    entry_price: float
    exit_price: float
    volume: float
    profit_eur: float
    exit_reason: str
    bars_held: int
    stop_loss: float
    take_profit: float


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Bar-by-bar backtest engine.

    Parameters
    ----------
    config : StrategyConfig
        Strategy configuration (symbol, timeframe, risk params, filters, ...).
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.pip_size = get_pip_size(config.symbol)
        self.pip_value = get_pip_value(config.symbol)
        self._is_gold = config.symbol.upper() in _XAU_SYMBOLS
        self._trades: list[ClosedTrade] = []
        self._equity_curve: list[dict] = []
        self._capital: float = config.starting_capital
        self._peak_equity: float = config.starting_capital

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        signal_fn: Callable[[pd.DataFrame, int, dict], Union[int, dict]],
        params: dict | None = None,
    ) -> BacktestResult:
        """Run the backtest.

        Parameters
        ----------
        signal_fn : callable
            ``signal_fn(df, bar_index, params) -> direction``

            Called at **every** bar.  Must return:

            * ``1``  - BUY signal (SL/TP derived from ATR)
            * ``-1`` - SELL signal (SL/TP derived from ATR)
            * ``0``  - HOLD (no trade)
            * ``{"direction": 1, "sl": 1.08500, "tp": 1.08700}``
              for custom stop-loss / take-profit.

        params : dict, optional
            Strategy parameters forwarded to *signal_fn* and used for
            default SL/TP multipliers.

        Returns
        -------
        BacktestResult
        """
        params = dict(params or {})
        self._trades = []
        self._equity_curve = []
        self._capital = self.config.starting_capital
        self._peak_equity = self.config.starting_capital

        tf = self.config.timeframes[0]
        sd = self.config.start_date or None
        ed = self.config.end_date or None
        df = load_data(self.config.symbol, tf, start_date=sd, end_date=ed)
        if len(df) == 0:
            logger.warning(f"[{self.config.symbol}] No data loaded")
            return self._empty_result(params)

        warmup = params.get("warmup_bars", 50)
        start_bar = max(warmup, 0)
        position: Position | None = None

        for i in range(len(df)):
            row = df.iloc[i]
            bar_dt: datetime = row["datetime"]
            close: float = float(row["close"])
            high: float = float(row["high"])
            low: float = float(row["low"])

            # ---- manage open position ----
            if position is not None:
                position.bars_held = i - position.entry_bar
                exit_reason, exit_price = self._check_exit(position, row)

                if exit_reason is not None:
                    profit = self._calc_profit(
                        position.direction,
                        position.entry_price,
                        exit_price,
                        position.volume,
                    )
                    self._capital += profit
                    if self._capital > self._peak_equity:
                        self._peak_equity = self._capital

                    self._trades.append(
                        ClosedTrade(
                            entry_time=position.entry_time,
                            exit_time=bar_dt,
                            direction=position.direction,
                            entry_price=position.entry_price,
                            exit_price=exit_price,
                            volume=position.volume,
                            profit_eur=profit,
                            exit_reason=exit_reason,
                            bars_held=position.bars_held,
                            stop_loss=position.stop_loss,
                            take_profit=position.take_profit,
                        )
                    )
                    position = None
                else:
                    self._update_trailing(position, row, params)

            # ---- equity curve ----
            dd_pct = (
                (self._peak_equity - self._capital) / self._peak_equity * 100.0
                if self._peak_equity > 0
                else 0.0
            )
            self._equity_curve.append({
                "datetime": bar_dt,
                "equity": round(self._capital, 2),
                "drawdown_pct": round(dd_pct, 2),
            })

            # ---- seek new entry ----
            if position is not None:
                continue
            if i < start_bar:
                continue
            if not self._session_allows(bar_dt):
                continue
            if not self._spread_ok(row):
                continue
            if not self._atr_ok(row, params):
                continue
            if not self._trend_ok(row):
                continue

            signal = signal_fn(df.iloc[: i + 1], i, params)
            direction, custom_sl, custom_tp = self._parse_signal(signal)
            if direction == 0:
                continue

            atr_val = self._get_atr(row, params)
            slippage = self.config.slippage_pips * self.pip_size

            if direction == 1:
                entry = close + slippage
            else:
                entry = close - slippage

            # Stop-loss
            if custom_sl is not None:
                sl = custom_sl
            else:
                sl_atr_mult = float(params.get("sl_atr_mult", 2.0))
                sl_dist = sl_atr_mult * atr_val
                min_sl_pips = 50.0 if self._is_gold else 15.0
                min_sl_dist = min_sl_pips * self.pip_size
                sl_dist = max(sl_dist, min_sl_dist)
                if direction == 1:
                    sl = entry - sl_dist
                else:
                    sl = entry + sl_dist

            # Take-profit
            if custom_tp is not None:
                tp = custom_tp
            else:
                tp_atr_mult = float(params.get("tp_atr_mult", 4.0))
                tp_dist = tp_atr_mult * atr_val
                if direction == 1:
                    tp = entry + tp_dist
                else:
                    tp = entry - tp_dist

            # Validate SL/TP
            if direction == 1:
                if sl >= entry or tp <= entry:
                    continue
            else:
                if sl <= entry or tp >= entry:
                    continue

            # Position sizing
            sl_pips = abs(entry - sl) / self.pip_size
            if sl_pips <= 0:
                continue
            risk_eur = self._capital * self.config.risk_per_trade_pct
            volume = risk_eur / (sl_pips * self.pip_value)
            volume = max(0.01, round(float(volume), 2))

            position = Position(
                entry_time=bar_dt,
                entry_price=entry,
                direction=direction,
                volume=volume,
                stop_loss=sl,
                take_profit=tp,
                highest_favorable=entry,
                entry_bar=i,
            )

        # ---- close remaining position ----
        if position is not None:
            last_row = df.iloc[-1]
            exit_price = float(last_row["close"])
            profit = self._calc_profit(
                position.direction,
                position.entry_price,
                exit_price,
                position.volume,
            )
            self._capital += profit
            if self._capital > self._peak_equity:
                self._peak_equity = self._capital
            self._trades.append(
                ClosedTrade(
                    entry_time=position.entry_time,
                    exit_time=last_row["datetime"],
                    direction=position.direction,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    volume=position.volume,
                    profit_eur=profit,
                    exit_reason="END_OF_TEST",
                    bars_held=len(df) - 1 - position.entry_bar,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                )
            )
            dd_pct = (
                (self._peak_equity - self._capital) / self._peak_equity * 100.0
                if self._peak_equity > 0
                else 0.0
            )
            self._equity_curve.append({
                "datetime": last_row["datetime"],
                "equity": round(self._capital, 2),
                "drawdown_pct": round(dd_pct, 2),
            })

        return self._compute_metrics(df, params)


    # ------------------------------------------------------------------
    # Exit / Trade Management
    # ------------------------------------------------------------------

    def _check_exit(
        self, pos: Position, row: pd.Series
    ) -> tuple[str | None, float]:
        """Check if the position should be closed on this bar.

        Returns ``(exit_reason, exit_price)`` or ``(None, 0.0)``.
        """
        high: float = float(row["high"])
        low: float = float(row["low"])
        close: float = float(row["close"])
        open_: float = float(row["open"])

        if pos.direction == 1:
            hit_sl = low <= pos.stop_loss
            hit_tp = high >= pos.take_profit
        else:
            hit_sl = high >= pos.stop_loss
            hit_tp = low <= pos.take_profit

        if hit_sl and hit_tp:
            dist_sl = abs(open_ - pos.stop_loss)
            dist_tp = abs(open_ - pos.take_profit)
            if dist_sl < dist_tp:
                hit_tp = False
            else:
                hit_sl = False

        if hit_sl:
            slippage = self.config.slippage_pips * self.pip_size
            if pos.direction == 1:
                exit_p = pos.stop_loss - slippage
            else:
                exit_p = pos.stop_loss + slippage
            return ("SL", exit_p)

        if hit_tp:
            return ("TP", pos.take_profit)

        if (
            self.config.time_exit_bars > 0
            and pos.bars_held >= self.config.time_exit_bars
        ):
            return ("TIME_EXIT", close)

        return (None, 0.0)

    def _update_trailing(
        self, pos: Position, row: pd.Series, params: dict
    ) -> None:
        """Update highest_favorable, breakeven, and trailing stop."""
        high: float = float(row["high"])
        low: float = float(row["low"])

        if pos.direction == 1:
            pos.highest_favorable = max(pos.highest_favorable, high)
        else:
            pos.highest_favorable = min(pos.highest_favorable, low)

        sl_distance = abs(pos.entry_price - pos.stop_loss)

        # Breakeven
        if self.config.breakeven_activation_r > 0 and not pos.breakeven_activated:
            profit_r = self._profit_in_r(pos)
            if profit_r >= self.config.breakeven_activation_r:
                pos.stop_loss = pos.entry_price
                pos.breakeven_activated = True

        # Trailing stop
        if (
            self.config.use_trailing_stop
            and self.config.trailing_activation_r > 0
        ):
            profit_r = self._profit_in_r(pos)
            if profit_r >= self.config.trailing_activation_r:
                pos.trailing_activated = True

            if pos.trailing_activated and sl_distance > 0:
                trail_dist = self.config.trailing_distance_r * sl_distance
                if pos.direction == 1:
                    new_sl = pos.highest_favorable - trail_dist
                    if new_sl > pos.stop_loss:
                        pos.stop_loss = new_sl
                else:
                    new_sl = pos.highest_favorable + trail_dist
                    if new_sl < pos.stop_loss:
                        pos.stop_loss = new_sl

    def _profit_in_r(self, pos: Position) -> float:
        """Current profit expressed as multiples of the initial SL distance."""
        sl_distance = abs(pos.entry_price - pos.stop_loss)
        if sl_distance <= 0:
            return 0.0
        if pos.direction == 1:
            profit_dist = pos.highest_favorable - pos.entry_price
        else:
            profit_dist = pos.entry_price - pos.highest_favorable
        return profit_dist / sl_distance

    # ------------------------------------------------------------------
    # Profit Calculation
    # ------------------------------------------------------------------

    def _calc_profit(
        self, direction: int, entry: float, exit_p: float, volume: float
    ) -> float:
        """Calculate profit in EUR for a closed trade."""
        if direction == 1:
            pips = (exit_p - entry) / self.pip_size
        else:
            pips = (entry - exit_p) / self.pip_size
        return pips * volume * self.pip_value

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _session_allows(self, bar_dt: datetime) -> bool:
        """Check session filter (UTC hours).

        Sessions:
        - asian:  00:00 - 08:00
        - london: 08:00 - 16:00
        - ny:     13:00 - 21:00
        """
        session = self.config.session_filter
        if not session:
            return True
        hour = bar_dt.hour + bar_dt.minute / 60.0
        if session == "asian":
            return 0.0 <= hour < 8.0
        if session == "london":
            return 8.0 <= hour < 16.0
        if session == "ny":
            return 13.0 <= hour < 21.0
        return True

    def _spread_ok(self, row: pd.Series) -> bool:
        """Return True if the current spread is within limits."""
        if self.config.max_spread_pips <= 0:
            return True
        if "spread" not in row.index:
            return True
        spread = float(row["spread"])
        if self.pip_size > 0:
            spread_pips = spread * self.pip_size
        else:
            spread_pips = spread
        return spread_pips <= self.config.max_spread_pips

    def _atr_ok(self, row: pd.Series, params: dict) -> bool:
        """Return True if ATR meets the minimum threshold."""
        min_atr = self.config.min_atr_pips
        if min_atr <= 0:
            return True
        atr = self._get_atr(row, params)
        atr_pips = atr / self.pip_size if self.pip_size > 0 else 0.0
        return atr_pips >= min_atr

    def _trend_ok(self, row: pd.Series) -> bool:
        """Trend filter gate - ensures EMA column exists and is not NaN."""
        if self.config.trend_filter_ema <= 0:
            return True
        col = f"ema_{self.config.trend_filter_ema}"
        if col not in row.index:
            return True
        return not pd.isna(row[col])

    # ------------------------------------------------------------------
    # Signal parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_signal(
        signal: Union[int, dict],
    ) -> tuple[int, float | None, float | None]:
        """Normalise a signal return value.

        Returns ``(direction, custom_sl, custom_tp)``.
        """
        if isinstance(signal, dict):
            direction = int(signal.get("direction", 0))
            sl = signal.get("sl")
            tp = signal.get("tp")
            return (
                direction,
                float(sl) if sl is not None else None,
                float(tp) if tp is not None else None,
            )
        return int(signal), None, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_atr(row: pd.Series, params: dict) -> float:
        """Extract ATR from a row, falling back to bar range."""
        if "atr" in row.index and not pd.isna(row["atr"]):
            return float(row["atr"])
        return float(row["high"]) - float(row["low"])

    def _empty_result(self, params: dict) -> BacktestResult:
        """Return a zero-filled result when no data is available."""
        return BacktestResult(
            strategy_name=self.config.name,
            symbol=self.config.symbol,
            timeframe=self.config.timeframes[0],
            start_date="",
            end_date="",
            params=params,
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _compute_metrics(
        self, df: pd.DataFrame, params: dict
    ) -> BacktestResult:
        """Aggregate closed trades into a ``BacktestResult``."""
        trades = self._trades
        total = len(trades)

        wins = [t for t in trades if t.profit_eur > 0]
        losses = [t for t in trades if t.profit_eur <= 0]

        total_profit = sum(t.profit_eur for t in wins)
        total_loss = abs(sum(t.profit_eur for t in losses))

        win_rate = len(wins) / total * 100.0 if total > 0 else 0.0

        if total_loss > 0:
            profit_factor = total_profit / total_loss
        elif total_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        avg_win = total_profit / len(wins) if wins else 0.0
        avg_loss = total_loss / len(losses) if losses else 0.0

        expectancy = (win_rate / 100.0 * avg_win) - (
            (1.0 - win_rate / 100.0) * avg_loss
        )

        equity = np.array(
            [e["equity"] for e in self._equity_curve], dtype=float
        )
        if len(equity) > 0:
            peak = np.maximum.accumulate(equity)
            drawdown = np.where(peak > 0, (peak - equity) / peak * 100.0, 0.0)
            max_dd = float(np.max(drawdown))
            max_dd_eur = float(np.max(peak - equity))
        else:
            max_dd = 0.0
            max_dd_eur = 0.0

        tf = self.config.timeframes[0]
        tf_minutes = _TIMEFRAME_MINUTES.get(tf, 15)
        bars_per_year = 252.0 * 24.0 * (60.0 / tf_minutes)

        if len(equity) > 1:
            returns = np.diff(equity) / equity[:-1]
            std_ret = np.std(returns)
            if std_ret > 0:
                sharpe = float(
                    np.mean(returns) / std_ret * np.sqrt(bars_per_year)
                )
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        if trades:
            rr_values: list[float] = []
            for t in trades:
                sl_dist = abs(t.entry_price - t.stop_loss)
                if sl_dist > 0:
                    rr = t.profit_eur / (
                        sl_dist / self.pip_size * t.volume * self.pip_value
                    )
                else:
                    rr = 0.0
                rr_values.append(rr if t.profit_eur > 0 else -1.0)
            avg_rr = float(np.mean(rr_values))
        else:
            avg_rr = 0.0

        exit_reasons: dict[str, int] = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        avg_bars = (
            float(np.mean([t.bars_held for t in trades])) if trades else 0.0
        )

        start_date = (
            str(self._equity_curve[0]["datetime"])
            if self._equity_curve
            else ""
        )
        end_date = (
            str(self._equity_curve[-1]["datetime"])
            if self._equity_curve
            else ""
        )

        return BacktestResult(
            strategy_name=self.config.name,
            symbol=self.config.symbol,
            timeframe=tf,
            start_date=start_date,
            end_date=end_date,
            total_trades=total,
            win_trades=len(wins),
            loss_trades=len(losses),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2)
            if profit_factor != float("inf")
            else 999.99,
            total_profit_eur=round(total_profit, 2),
            total_loss_eur=round(total_loss, 2),
            net_profit_eur=round(total_profit - total_loss, 2),
            max_drawdown_pct=round(max_dd, 2),
            max_drawdown_eur=round(max_dd_eur, 2),
            avg_win_eur=round(avg_win, 2),
            avg_loss_eur=round(avg_loss, 2),
            expectancy_eur=round(expectancy, 2),
            sharpe_ratio=round(sharpe, 2),
            avg_rr_ratio=round(avg_rr, 2),
            avg_bars_held=round(avg_bars, 1),
            exit_reasons=exit_reasons,
            trades=[
                {
                    "entry_time": str(t.entry_time),
                    "exit_time": str(t.exit_time),
                    "direction": "BUY" if t.direction == 1 else "SELL",
                    "entry_price": round(t.entry_price, 5),
                    "exit_price": round(t.exit_price, 5),
                    "volume": t.volume,
                    "profit_eur": round(t.profit_eur, 2),
                    "exit_reason": t.exit_reason,
                    "bars_held": t.bars_held,
                    "sl": round(t.stop_loss, 5),
                    "tp": round(t.take_profit, 5),
                }
                for t in trades
            ],
            equity_curve=self._equity_curve,
            params=params,
        )
