"""Adaptateur de strategie pour le backtesting - replique les regles de risque sans MT5.

Replicates the logic from `src/ai/strategy.py` but uses SimulatedExecutor
instead of real MetaTrader 5 calls. All positions are virtual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from src.backtest.simulated_executor import (
    SimulatedExecutor,
    SimulatedTradeResult,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StrategyResult:
    """Result of one strategy execution cycle."""

    decision: dict | None
    trade_result: Optional[SimulatedTradeResult] = None
    closed_positions: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# StrategyAdapter
# ---------------------------------------------------------------------------


class StrategyAdapter:
    """Backtest-safe strategy adapter.

    Mirrors the real ``src/ai/strategy.py`` risk management rules without
    any MetaTrader 5 dependency. Uses a ``SimulatedExecutor`` per symbol
    for virtual order management.
    """

    def __init__(
        self,
        executor: SimulatedExecutor,
        max_daily_loss_pct: float = 3.0,
        max_risk_per_trade_pct: float = 1.0,
        max_open_positions: int = 1,
        min_confidence_threshold: int = 70,
        max_spread_points: int = 30,
        consecutive_loss_limit: int = 4,
        circuit_breaker_hours: int = 4,
    ) -> None:
        self.executor = executor
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_open_positions = max_open_positions
        self.min_confidence_threshold = min_confidence_threshold
        self.max_spread_points = max_spread_points
        self.consecutive_loss_limit = consecutive_loss_limit
        self.circuit_breaker_hours = circuit_breaker_hours

        # In-memory circuit breaker state (no database in backtesting)
        self._circuit_breaker_until: Optional[datetime] = None
        # Track daily P&L per simulated date for loss limit checks
        self._daily_pnl_cache: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Main execute method
    # ------------------------------------------------------------------

    def execute_decision(
        self,
        decision: dict,
        symbol: str,
        current_price: float,
        bar_datetime: str,
        point: float = 0.00001,
        indicators: dict | None = None,
    ) -> StrategyResult:
        """Execute a trading decision in backtest mode.

        Mirrors ``src/ai/strategy.execute_decision()`` but uses the
        simulated executor instead of MT5.

        Parameters
        ----------
        decision : dict
            Output from ``RuleEngine.evaluate()``. Keys: action, confidence,
            stop_loss_pips, take_profit_pips, ...
        symbol : str
            Trading symbol (e.g. "EURUSD").
        current_price : float
            Current bar close price used as entry price.
        bar_datetime : str
            ISO-formatted datetime of the current bar.
        point : float
            Pip value for the symbol (e.g. 0.00001 for EURUSD).
        indicators : dict or None
            Indicator values for RSI/BB pre-trade filters.

        Returns
        -------
        StrategyResult
        """
        result = StrategyResult(decision=decision)
        action = decision.get("action", "HOLD")

        # ---- HOLD ----
        if action == "HOLD":
            logger.debug(f"[{symbol}] HOLD - pas d'execution")
            return result

        # ---- Pre-trade guards ----
        balance = self.executor.balance
        daily_pnl = self.get_daily_pnl()
        if not self._check_daily_loss_limit(balance, daily_pnl):
            logger.warning(
                f"[{symbol}] LIMITE PERTE JOURNALIERE: "
                f"{abs(daily_pnl) / balance * 100:.1f}%"
            )
            return result

        # ---- CLOSE ----
        if action == "CLOSE":
            for pos in self.executor.get_open_positions(symbol):
                close_res = self.executor.close_position(
                    pos["ticket"], current_price, bar_datetime, "MANUAL"
                )
                result.closed_positions.append(close_res)
            return result

        # ---- BUY / SELL ----
        if action in ("BUY", "SELL"):
            open_positions = self.executor.get_open_positions(symbol)

            # Opposite direction position exists → close, no immediate reversal
            if open_positions:
                existing = open_positions[0]
                existing_dir = "BUY" if existing["type"] == 0 else "SELL"
                if existing_dir != action:
                    logger.info(
                        f"[{symbol}] Fermeture {existing_dir} (signaux opposes), "
                        f"pas de reversal immediat"
                    )
                    close_res = self.executor.close_position(
                        existing["ticket"], current_price, bar_datetime, "REVERSAL"
                    )
                    result.closed_positions.append(close_res)
                    return result
                else:
                    # Same direction: keep position, skip
                    logger.info(
                        f"[{symbol}] Deja {existing_dir} - position conservee"
                    )
                    return result

            # No position: apply trade filters
            spread = self.max_spread_points  # default; overridden by data source
            if not self._passes_trade_filters(decision, spread, indicators):
                return result

            # Position sizing
            sl_pips = decision.get("stop_loss_pips", 20)
            tp_pips = decision.get("take_profit_pips", 30)
            volume = self.executor.calculate_position_size(
                balance, sl_pips, self.max_risk_per_trade_pct, point
            )

            # SL / TP prices
            digits = 5
            if "JPY" in symbol.upper():
                digits = 3
            elif symbol.upper() == "XAUUSD":
                digits = 2

            if action == "BUY":
                sl_price = round(current_price - (sl_pips * 10 * point), digits)
                tp_price = round(current_price + (tp_pips * 10 * point), digits)
            else:
                sl_price = round(current_price + (sl_pips * 10 * point), digits)
                tp_price = round(current_price - (tp_pips * 10 * point), digits)

            trade_result = self.executor.open_position(
                direction=action,
                volume=volume,
                stop_loss=sl_price,
                take_profit=tp_price,
                symbol=symbol,
                open_price=current_price,
                open_time=bar_datetime,
                comment=f"BT confiance={decision.get('confidence', 0)}%",
            )
            result.trade_result = trade_result
            return result

        return result

    # ------------------------------------------------------------------
    # Pre-trade guards
    # ------------------------------------------------------------------

    def _check_daily_loss_limit(self, balance: float, daily_pnl: float) -> bool:
        """Return True if trading is allowed (daily loss limit NOT hit).

        Formula: ``abs(daily_pnl) / balance * 100 < max_daily_loss_pct``
        """
        if balance <= 0:
            return False
        if daily_pnl < 0 and abs(daily_pnl) / balance * 100 >= self.max_daily_loss_pct:
            return False
        return True

    # ------------------------------------------------------------------
    # Trade filters
    # ------------------------------------------------------------------

    def _passes_trade_filters(
        self, decision: dict, spread: float, indicators: dict | None
    ) -> bool:
        """Apply pre-trade filters: confidence, max positions, spread,
        circuit breaker, RSI/BB.

        Mirrors ``src/ai/strategy._passes_trade_filters``.
        """
        confidence = decision.get("confidence", 0)
        if confidence < self.min_confidence_threshold:
            logger.info(
                f"Confiance {confidence}% < seuil {self.min_confidence_threshold}%"
            )
            return False

        if self.executor.count_open_positions() >= self.max_open_positions:
            logger.info("Max positions atteint - pas d'execution")
            return False

        if spread > self.max_spread_points:
            logger.warning(f"Spread trop eleve: {spread} points > {self.max_spread_points} max")
            return False

        # Circuit breaker check
        if self._check_circuit_breaker():
            logger.info("Circuit breaker actif - pas d'execution")
            return False

        # Consecutive losses → activate circuit breaker
        consecutive_losses = self._count_consecutive_losses()
        if consecutive_losses >= self.consecutive_loss_limit:
            logger.warning(
                f"CIRCUIT BREAKER: {consecutive_losses} pertes consecutives - "
                f"pause {self.circuit_breaker_hours}h"
            )
            until = datetime.now() + timedelta(hours=self.circuit_breaker_hours)
            self._circuit_breaker_until = until
            return False

        # RSI / BB filters (PROB-8)
        ind = indicators or {}
        rsi = ind.get("rsi_14", 50) or 50
        bb_pos = ind.get("bb_position_pct", 50) or 50
        action = decision.get("action", "")

        if action == "BUY" and rsi > 75:
            logger.info(f"Filtre RSI/BB: BUY bloque (RSI={rsi:.1f} > 75 - zone surchetee)")
            return False
        if action == "SELL" and rsi < 25:
            logger.info(f"Filtre RSI/BB: SELL bloque (RSI={rsi:.1f} < 25 - zone survendue)")
            return False
        if action == "BUY" and isinstance(bb_pos, (int, float)) and bb_pos > 100:
            logger.info(
                f"Filtre RSI/BB: BUY bloque (BB_position={bb_pos:.0f}% > 100)"
            )
            return False
        if action == "SELL" and isinstance(bb_pos, (int, float)) and bb_pos < 0:
            logger.info(
                f"Filtre RSI/BB: SELL bloque (BB_position={bb_pos:.0f}% < 0)"
            )
            return False

        return True

    def _count_consecutive_losses(self) -> int:
        """Count consecutive losing closed trades from the executor history."""
        closed = self.executor.get_closed_trades()
        count = 0
        for trade in reversed(closed):
            if trade.profit < 0:
                count += 1
            else:
                break
        return count

    def _check_circuit_breaker(self) -> bool:
        """Return True if the circuit breaker is currently active."""
        if self._circuit_breaker_until is None:
            return False
        return datetime.now() < self._circuit_breaker_until

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def manage_open_positions(
        self,
        current_price: float,
        bar_datetime: str,
        open_time_threshold_hours: int = 8,
        point: float = 0.00001,
    ) -> list[SimulatedTradeResult]:
        """Apply breakeven, trailing stop, and time exit to all open positions.

        Called once per bar for each symbol.

        Parameters
        ----------
        current_price : float
            Current bar close price (used as bid/ask approximation).
        bar_datetime : str
            ISO-formatted datetime of the current bar.
        open_time_threshold_hours : int
            Max hours a position can stay open before forced time exit.
        point : float
            Pip value for the symbol.

        Returns
        -------
        list[SimulatedTradeResult]
            Results of any modifications or closures made.
        """
        results: list[SimulatedTradeResult] = []

        for pos_dict in self.executor.get_open_positions():
            pos = self._find_position_by_ticket(pos_dict["ticket"])
            if pos is None:
                continue

            entry_price = pos.open_price
            current_sl = pos.stop_loss
            ticket = pos.ticket
            direction = pos.direction

            # Compute SL distance in pips
            sl_distance_pips = (
                abs(entry_price - current_sl) / (10 * point)
                if current_sl and point > 0
                else 0
            )

            # Current profit in pips
            if direction == "BUY":
                profit_pips = (current_price - entry_price) / (10 * point) if point > 0 else 0
            else:
                profit_pips = (entry_price - current_price) / (10 * point) if point > 0 else 0

            # -- Breakeven: profit >= 50% of SL distance, move SL to entry --
            if sl_distance_pips > 0 and profit_pips >= sl_distance_pips * 0.5:
                if direction == "BUY" and current_sl < entry_price:
                    pos.stop_loss = entry_price
                    logger.info(
                        f"BREAKEVEN: ticket {ticket}, SL deplace a l'entree {entry_price}"
                    )
                elif direction == "SELL" and current_sl > entry_price:
                    pos.stop_loss = entry_price
                    logger.info(
                        f"BREAKEVEN: ticket {ticket}, SL deplace a l'entree {entry_price}"
                    )

            # -- Trailing stop: profit >= 2x initial SL distance --
            elif sl_distance_pips > 0 and profit_pips >= sl_distance_pips * 2:
                trail_pips = 15
                trail_distance = trail_pips * 10 * point
                if direction == "BUY":
                    new_sl = round(current_price - trail_distance, 5)
                    if new_sl > current_sl + point:
                        pos.stop_loss = new_sl
                        logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")
                else:
                    new_sl = round(current_price + trail_distance, 5)
                    if new_sl < current_sl - point:
                        pos.stop_loss = new_sl
                        logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")

            # -- Time exit: close if position has been open too long --
            try:
                open_dt = datetime.fromisoformat(pos.open_time)
                bar_dt = datetime.fromisoformat(bar_datetime)
                age_hours = (bar_dt - open_dt).total_seconds() / 3600

                # Close losers stagnating > 2h
                floating = (
                    (current_price - entry_price) if direction == "BUY"
                    else (entry_price - current_price)
                )
                floating_pnl = floating * pos.volume * 100000 if "XAUUSD" not in pos.symbol.upper() else floating * pos.volume * 100

                if age_hours > 2 and -5.0 < floating_pnl < -0.5:
                    logger.info(
                        f"TIME EXIT: ticket {ticket}, perte stagnante "
                        f"{floating_pnl:.2f}$ depuis {age_hours:.0f}h"
                    )
                    close_res = self.executor.close_position(
                        ticket, current_price, bar_datetime, "TIME_EXIT"
                    )
                    results.append(close_res)
                    continue

                if age_hours > open_time_threshold_hours:
                    logger.info(
                        f"TIME EXIT: ticket {ticket}, stagnation "
                        f"totale depuis {age_hours:.0f}h"
                    )
                    close_res = self.executor.close_position(
                        ticket, current_price, bar_datetime, "TIME_EXIT"
                    )
                    results.append(close_res)
                    continue

            except (ValueError, TypeError):
                pass

        return results

    # ------------------------------------------------------------------
    # P&L helpers
    # ------------------------------------------------------------------

    def get_daily_pnl(self) -> float:
        """Calculate daily P&L: closed trades profit + floating P&L.

        Uses closed trades from today (simulated) plus unrealized P&L.
        """
        realized = 0.0
        for trade in self.executor.get_closed_trades():
            # Treat all closed trades in backtest as "today" for simplicity
            realized += trade.profit

        # Floating P&L (computed at last known price - approximate)
        floating = 0.0
        for pos in self.executor.open_positions:
            # Use open_price as proxy; caller should provide real current price
            if pos.direction == "BUY":
                floating += (pos.open_price - pos.open_price) * pos.volume * 100000
            else:
                floating += (pos.open_price - pos.open_price) * pos.volume * 100000

        return realized + floating

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_position_by_ticket(self, ticket: int):
        """Find an open position object by ticket number."""
        from src.backtest.simulated_executor import SimulatedPosition

        for pos in self.executor.open_positions:
            if pos.ticket == ticket:
                return pos
        return None
