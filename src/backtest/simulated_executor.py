"""Simulated executor for backtesting - tracks virtual positions and P&L.

Replaces `src/mt5/executor.py` during backtest runs. All positions are virtual:
no real orders are placed on MT5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SimulatedPosition:
    ticket: int
    symbol: str
    direction: str  # "BUY" or "SELL"
    volume: float
    open_price: float
    stop_loss: float
    take_profit: float
    open_time: str  # datetime string
    magic: int
    comment: str = ""


@dataclass
class SimulatedTradeResult:
    success: bool
    ticket: int | None
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    comment: str
    error: str | None = None


@dataclass
class ClosedTrade:
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    close_price: float
    open_time: str
    close_time: str
    profit: float
    exit_reason: str  # "SL", "TP", "MANUAL", "REVERSAL", "TIME_EXIT"
    stop_loss: float
    take_profit: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_gold(symbol: str) -> bool:
    return symbol.upper() == "XAUUSD"


def _spread_pips(symbol: str, slippage_pips: float, point: float) -> float:
    """Price distance corresponding to slippage_pips for the given symbol."""
    pip_factor = point if _is_gold(symbol) else 10 * point
    return slippage_pips * pip_factor


def _profit(symbol: str, open_price: float, close_price: float,
            volume: float, direction: str, point: float) -> float:
    """Profit in account currency."""
    if _is_gold(symbol):
        # Gold: 1 pip = point (0.01), profit = price_diff * volume * 100
        diff = close_price - open_price if direction == "BUY" else open_price - close_price
        return diff * volume * 100
    else:
        # Forex: profit = (price_diff) * volume * 100000
        diff = close_price - open_price if direction == "BUY" else open_price - close_price
        return diff * volume * 100000


# ---------------------------------------------------------------------------
# SimulatedExecutor
# ---------------------------------------------------------------------------

class SimulatedExecutor:
    """Virtual order executor for backtesting.

    Maintains virtual balance, equity, open positions and trade history.
    All fills are simulated with configurable slippage and commission.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        slippage_pips: float = 1.0,
        commission_per_lot: float = 0.0,
        point: float = 0.00001,
        magic: int = 123456,
    ):
        self._initial_balance = initial_balance
        self.slippage_pips = slippage_pips
        self.commission_per_lot = commission_per_lot
        self.point = point
        self.magic = magic

        self.balance: float = initial_balance
        self.equity: float = initial_balance
        self.open_positions: list[SimulatedPosition] = []
        self.closed_trades: list[ClosedTrade] = []
        self.next_ticket: int = 100000
        self.total_commission: float = 0.0

    # -- public API ---------------------------------------------------------

    def open_position(
        self,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        symbol: str,
        open_price: float,
        open_time: str,
        comment: str = "",
    ) -> SimulatedTradeResult:
        """Open a virtual position with slippage applied to entry price."""
        direction = direction.upper()

        spread = _spread_pips(symbol, self.slippage_pips, self.point)
        if direction == "BUY":
            entry_price = open_price + spread
        else:
            entry_price = open_price - spread

        ticket = self.next_ticket
        self.next_ticket += 1

        position = SimulatedPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            open_time=open_time,
            magic=self.magic,
            comment=comment,
        )
        self.open_positions.append(position)

        commission = volume * self.commission_per_lot
        self.balance -= commission
        self.total_commission += commission
        self.equity = self.balance

        return SimulatedTradeResult(
            success=True,
            ticket=ticket,
            volume=volume,
            price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def close_position(
        self,
        ticket: int,
        close_price: float,
        close_time: str,
        exit_reason: str = "MANUAL",
    ) -> SimulatedTradeResult:
        """Close an open virtual position by ticket."""
        for i, pos in enumerate(self.open_positions):
            if pos.ticket == ticket:
                break
        else:
            return SimulatedTradeResult(
                success=False,
                ticket=ticket,
                volume=0,
                price=close_price,
                stop_loss=0,
                take_profit=0,
                comment="",
                error="Position not found",
            )

        # Slippage: opposite direction of entry
        spread = _spread_pips(pos.symbol, self.slippage_pips, self.point)
        if pos.direction == "BUY":
            fill_price = close_price - spread
        else:
            fill_price = close_price + spread

        profit = _profit(pos.symbol, pos.open_price, fill_price, pos.volume,
                         pos.direction, self.point)

        commission = pos.volume * self.commission_per_lot
        self.balance += profit - commission
        self.total_commission += commission

        closed = ClosedTrade(
            ticket=pos.ticket,
            symbol=pos.symbol,
            direction=pos.direction,
            volume=pos.volume,
            open_price=pos.open_price,
            close_price=fill_price,
            open_time=pos.open_time,
            close_time=close_time,
            profit=profit - commission,
            exit_reason=exit_reason,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
        )
        self.closed_trades.append(closed)

        del self.open_positions[i]
        self.equity = self.balance + self.get_floating_pnl(close_price)

        return SimulatedTradeResult(
            success=True,
            ticket=ticket,
            volume=pos.volume,
            price=fill_price,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            comment=exit_reason,
        )

    def check_sl_tp(
        self,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_time: str,
    ) -> list[SimulatedTradeResult]:
        """Check every open position for SL/TP hits during this bar.

        Priority rule: when both SL and TP are reachable in the same bar,
        the level closer to the open price wins (assuming the price reaches
        that level first).
        """
        results: list[SimulatedTradeResult] = []
        closed_indices: list[int] = []

        for i, pos in enumerate(self.open_positions):
            hit = self._resolve_sl_tp(pos, bar_high, bar_low)
            if hit is None:
                continue

            close_price, reason = hit
            closed_indices.append(i)

            profit = _profit(pos.symbol, pos.open_price, close_price,
                             pos.volume, pos.direction, self.point)
            commission = pos.volume * self.commission_per_lot
            self.balance += profit - commission
            self.total_commission += commission

            closed = ClosedTrade(
                ticket=pos.ticket,
                symbol=pos.symbol,
                direction=pos.direction,
                volume=pos.volume,
                open_price=pos.open_price,
                close_price=close_price,
                open_time=pos.open_time,
                close_time=bar_time,
                profit=profit - commission,
                exit_reason=reason,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
            )
            self.closed_trades.append(closed)

            results.append(SimulatedTradeResult(
                success=True,
                ticket=pos.ticket,
                volume=pos.volume,
                price=close_price,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                comment=reason,
            ))

        # Remove from open positions in reverse order to preserve indices
        for idx in sorted(closed_indices, reverse=True):
            del self.open_positions[idx]

        if closed_indices:
            self.equity = self.balance + self.get_floating_pnl(bar_close)

        return results

    def _resolve_sl_tp(
        self,
        pos: SimulatedPosition,
        bar_high: float,
        bar_low: float,
    ) -> tuple[float, str] | None:
        """Determine whether SL or TP was hit during this bar.

        Returns (fill_price, reason) or None if neither was hit.
        """
        if pos.direction == "BUY":
            sl_hit = bar_low <= pos.stop_loss
            tp_hit = bar_high >= pos.take_profit

            if sl_hit and tp_hit:
                # Both hit: the level closer to open_price is hit first.
                dist_sl = abs(pos.open_price - pos.stop_loss)
                dist_tp = abs(pos.take_profit - pos.open_price)
                if dist_sl <= dist_tp:
                    return (pos.stop_loss, "SL")
                else:
                    return (pos.take_profit, "TP")

            if sl_hit:
                return (pos.stop_loss, "SL")
            if tp_hit:
                return (pos.take_profit, "TP")

        else:  # SELL
            sl_hit = bar_high >= pos.stop_loss
            tp_hit = bar_low <= pos.take_profit

            if sl_hit and tp_hit:
                dist_sl = abs(pos.stop_loss - pos.open_price)
                dist_tp = abs(pos.open_price - pos.take_profit)
                if dist_sl <= dist_tp:
                    return (pos.stop_loss, "SL")
                else:
                    return (pos.take_profit, "TP")

            if sl_hit:
                return (pos.stop_loss, "SL")
            if tp_hit:
                return (pos.take_profit, "TP")

        return None

    def get_open_positions(self, symbol: str | None = None) -> list[dict]:
        """Return open positions in MT5-compatible dict format.

        ``type`` is 0 for BUY, 1 for SELL.
        ``profit`` is the unrealized floating PnL computed at open_price
        (caller should update externally when a current price is available).
        """
        result: list[dict] = []
        for pos in self.open_positions:
            if symbol and pos.symbol != symbol:
                continue
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": 0 if pos.direction == "BUY" else 1,
                "volume": pos.volume,
                "price_open": pos.open_price,
                "sl": pos.stop_loss,
                "tp": pos.take_profit,
                "profit": 0.0,  # floating PnL computed separately
                "comment": pos.comment,
            })
        return result

    def count_open_positions(self, symbol: str | None = None) -> int:
        """Number of currently open positions, optionally filtered by symbol."""
        if symbol is None:
            return len(self.open_positions)
        return sum(1 for p in self.open_positions if p.symbol == symbol)

    def calculate_position_size(
        self,
        balance: float,
        stop_loss_pips: float,
        risk_pct: float = 1.0,
        point: float = 0.00001,
    ) -> float:
        """Calculate lot size based on risk parameters.

        Formula: lots = (balance * risk_pct/100) / (sl_pips * 10 * point * 100000)
        """
        pip_distance = stop_loss_pips * 10 * point
        if pip_distance <= 0:
            return 0.01
        lots = (balance * risk_pct / 100) / (pip_distance * 100000)
        lots = max(0.01, round(lots, 2))
        return lots

    def get_closed_trades(self) -> list[ClosedTrade]:
        """Return all closed trades history."""
        return list(self.closed_trades)

    def get_floating_pnl(self, close_price: float) -> float:
        """Total unrealized PnL across all open positions at *close_price*."""
        total = 0.0
        for pos in self.open_positions:
            total += _profit(pos.symbol, pos.open_price, close_price,
                             pos.volume, pos.direction, self.point)
        self.equity = self.balance + total
        return total

    def reset(self) -> None:
        """Reset all state back to initial values."""
        self.balance = self._initial_balance
        self.equity = self._initial_balance
        self.open_positions.clear()
        self.closed_trades.clear()
        self.next_ticket = 100000
        self.total_commission = 0.0
