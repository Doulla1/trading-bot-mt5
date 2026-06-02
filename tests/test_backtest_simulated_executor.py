"""Tests unitaires pour SimulatedExecutor (backtesting)."""

import pytest

from src.backtest.simulated_executor import (
    ClosedTrade,
    SimulatedExecutor,
    SimulatedPosition,
    SimulatedTradeResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def executor() -> SimulatedExecutor:
    """Fresh executor with default settings."""
    return SimulatedExecutor(initial_balance=10000.0, slippage_pips=1.0, point=0.00001)


@pytest.fixture
def gold_executor() -> SimulatedExecutor:
    """Executor configured for XAUUSD."""
    return SimulatedExecutor(initial_balance=10000.0, slippage_pips=1.0, point=0.01)


# ---------------------------------------------------------------------------
# open_position
# ---------------------------------------------------------------------------


class TestOpenPosition:
    """Tests for open_position()."""

    def test_creates_position_correctly(self, executor: SimulatedExecutor) -> None:
        result = executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        assert result.success is True
        assert result.ticket is not None
        assert result.ticket >= 100000
        assert len(executor.open_positions) == 1

    def test_opening_increments_ticket(self, executor: SimulatedExecutor) -> None:
        r1 = executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        r2 = executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:15:00",
        )
        assert r2.ticket == r1.ticket + 1

    def test_buy_has_slippage_above_open(self, executor: SimulatedExecutor) -> None:
        result = executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        # BUY entry = open_price + spread (1 pip * 10 * point = 0.00010)
        assert result.price > 1.0850

    def test_sell_has_slippage_below_open(self, executor: SimulatedExecutor) -> None:
        result = executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        # SELL entry = open_price - spread
        assert result.price < 1.0850

    def test_position_appears_in_open_list(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        positions = executor.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "EURUSD"
        assert positions[0]["type"] == 0  # BUY


# ---------------------------------------------------------------------------
# close_position
# ---------------------------------------------------------------------------


class TestClosePosition:
    """Tests for close_position()."""

    def test_close_buy_with_profit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        result = executor.close_position(ticket, close_price=1.0900, close_time="2026-06-01 13:00:00")
        assert result.success is True
        assert len(executor.open_positions) == 0
        assert len(executor.closed_trades) == 1
        assert executor.closed_trades[0].profit > 0

    def test_close_buy_with_loss(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        result = executor.close_position(ticket, close_price=1.0800, close_time="2026-06-01 13:00:00")
        assert result.success is True
        assert executor.closed_trades[0].profit < 0

    def test_close_sell_with_profit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        result = executor.close_position(ticket, close_price=1.0800, close_time="2026-06-01 13:00:00")
        assert result.success is True
        assert executor.closed_trades[0].profit > 0

    def test_close_sell_with_loss(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        result = executor.close_position(ticket, close_price=1.0900, close_time="2026-06-01 13:00:00")
        assert result.success is True
        assert executor.closed_trades[0].profit < 0

    def test_close_nonexistent_ticket_returns_failure(self, executor: SimulatedExecutor) -> None:
        result = executor.close_position(99999, close_price=1.0850, close_time="2026-06-01 13:00:00")
        assert result.success is False
        assert result.error == "Position not found"

    def test_closed_trade_has_correct_fields(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.2, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00", comment="test_trade",
        )
        ticket = executor.open_positions[0].ticket
        executor.close_position(ticket, close_price=1.0900, close_time="2026-06-01 13:00:00", exit_reason="TP")
        ct = executor.closed_trades[0]
        assert isinstance(ct, ClosedTrade)
        assert ct.symbol == "EURUSD"
        assert ct.direction == "BUY"
        assert ct.volume == 0.2
        assert ct.exit_reason == "TP"


# ---------------------------------------------------------------------------
# check_sl_tp
# ---------------------------------------------------------------------------


class TestCheckSLTP:
    """Tests for check_sl_tp()."""

    def test_buy_sl_hit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0860, bar_low=1.0790, bar_close=1.0800,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].comment == "SL"
        assert len(executor.open_positions) == 0

    def test_buy_tp_hit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0910, bar_low=1.0840, bar_close=1.0900,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 1
        assert results[0].comment == "TP"

    def test_sell_sl_hit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0910, bar_low=1.0840, bar_close=1.0900,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 1
        assert results[0].comment == "SL"

    def test_sell_tp_hit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0860, bar_low=1.0790, bar_close=1.0800,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 1
        assert results[0].comment == "TP"

    def test_neither_hit_position_stays(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0870, bar_low=1.0830, bar_close=1.0850,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 0
        assert len(executor.open_positions) == 1

    def test_both_hit_priority_closer_buy(self, executor: SimulatedExecutor) -> None:
        """When both SL and TP hit, the closer level to open price wins."""
        executor.open_position(
            direction="BUY", volume=0.1,
            stop_loss=1.0800,   # 50 pips from open
            take_profit=1.0870,  # 20 pips from open (closer)
            symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0880, bar_low=1.0790, bar_close=1.0870,
            bar_time="2026-06-01 13:00:00",
        )
        # TP is closer (20 pips vs 50 pips), so TP should win
        assert len(results) == 1
        assert results[0].comment == "TP"

    def test_both_hit_priority_closer_sell(self, executor: SimulatedExecutor) -> None:
        """SELL: when both hit, closer level wins."""
        executor.open_position(
            direction="SELL", volume=0.1,
            stop_loss=1.0900,   # 50 pips from open
            take_profit=1.0830,  # 20 pips from open (closer)
            symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0910, bar_low=1.0820, bar_close=1.0830,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 1
        assert results[0].comment == "TP"

    def test_both_hit_equal_distance_goes_sl(self) -> None:
        """When both are equally distant, SL wins (<= comparison).

        Use zero slippage so entry price equals open_price exactly."""
        executor = SimulatedExecutor(initial_balance=10000.0, slippage_pips=0.0, point=0.00001)
        executor.open_position(
            direction="BUY", volume=0.1,
            stop_loss=1.0800,   # 50 pips from open
            take_profit=1.0900,  # 50 pips from open (equal distance)
            symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        results = executor.check_sl_tp(
            bar_high=1.0910, bar_low=1.0790, bar_close=1.0800,
            bar_time="2026-06-01 13:00:00",
        )
        # dist_sl == dist_tp == 50 pips, so SL wins (<= comparison)
        assert len(results) == 1
        assert results[0].comment == "SL"

    def test_multiple_positions_checked(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        # Bar low goes below BUY SL, bar high goes above SELL SL
        results = executor.check_sl_tp(
            bar_high=1.0910, bar_low=1.0790, bar_close=1.0850,
            bar_time="2026-06-01 13:00:00",
        )
        assert len(results) == 2


# ---------------------------------------------------------------------------
# calculate_position_size
# ---------------------------------------------------------------------------


class TestCalculatePositionSize:
    """Tests for calculate_position_size()."""

    def test_standard_forex_lot(self, executor: SimulatedExecutor) -> None:
        lots = executor.calculate_position_size(10000, 20, risk_pct=1.0, point=0.00001)
        assert 0.01 <= lots <= 1.0
        assert round(lots, 2) == 0.5

    def test_larger_balance_increases_volume(self, executor: SimulatedExecutor) -> None:
        lots_10k = executor.calculate_position_size(10000, 20, risk_pct=1.0, point=0.00001)
        lots_30k = executor.calculate_position_size(30000, 20, risk_pct=1.0, point=0.00001)
        assert lots_30k > lots_10k

    def test_wider_stop_loss_decreases_volume(self, executor: SimulatedExecutor) -> None:
        lots_tight = executor.calculate_position_size(10000, 15, risk_pct=1.0, point=0.00001)
        lots_wide = executor.calculate_position_size(10000, 40, risk_pct=1.0, point=0.00001)
        assert lots_tight > lots_wide

    def test_minimum_lot_floor(self, executor: SimulatedExecutor) -> None:
        lots = executor.calculate_position_size(500, 50, risk_pct=1.0, point=0.00001)
        assert lots == 0.01

    def test_zero_stop_loss_returns_minimum(self, executor: SimulatedExecutor) -> None:
        lots = executor.calculate_position_size(10000, 0, risk_pct=1.0, point=0.00001)
        assert lots == 0.01

    def test_higher_risk_pct_increases_volume(self, executor: SimulatedExecutor) -> None:
        lots_1pct = executor.calculate_position_size(10000, 20, risk_pct=1.0, point=0.00001)
        lots_3pct = executor.calculate_position_size(10000, 20, risk_pct=3.0, point=0.00001)
        assert lots_3pct > lots_1pct


# ---------------------------------------------------------------------------
# get_open_positions
# ---------------------------------------------------------------------------


class TestGetOpenPositions:
    """Tests for get_open_positions()."""

    def test_returns_mt5_compatible_format(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00", comment="test",
        )
        positions = executor.get_open_positions()
        assert len(positions) == 1
        p = positions[0]
        assert "ticket" in p
        assert "symbol" in p
        assert "type" in p
        assert "volume" in p
        assert "price_open" in p
        assert "sl" in p
        assert "tp" in p
        assert "profit" in p
        assert "comment" in p
        assert p["type"] == 0  # BUY is type 0
        assert p["comment"] == "test"

    def test_sell_type_is_1(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="SELL", volume=0.1, stop_loss=1.0900,
            take_profit=1.0800, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        positions = executor.get_open_positions()
        assert positions[0]["type"] == 1

    def test_filter_by_symbol(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=158.0,
            take_profit=162.0, symbol="USDJPY", open_price=160.0,
            open_time="2026-06-01 12:00:00",
        )
        eur_positions = executor.get_open_positions(symbol="EURUSD")
        assert len(eur_positions) == 1
        assert eur_positions[0]["symbol"] == "EURUSD"

    def test_empty_when_no_positions(self, executor: SimulatedExecutor) -> None:
        positions = executor.get_open_positions()
        assert positions == []


# ---------------------------------------------------------------------------
# count_open_positions
# ---------------------------------------------------------------------------


class TestCountOpenPositions:
    """Tests for count_open_positions()."""

    def test_counts_correctly(self, executor: SimulatedExecutor) -> None:
        assert executor.count_open_positions() == 0
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        assert executor.count_open_positions() == 1

    def test_filter_by_symbol(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=158.0,
            take_profit=162.0, symbol="USDJPY", open_price=160.0,
            open_time="2026-06-01 12:00:00",
        )
        assert executor.count_open_positions() == 2
        assert executor.count_open_positions(symbol="EURUSD") == 1
        assert executor.count_open_positions(symbol="USDJPY") == 1


# ---------------------------------------------------------------------------
# Gold (XAUUSD) profit
# ---------------------------------------------------------------------------


class TestGoldProfit:
    """Tests for XAUUSD-specific profit calculation."""

    def test_gold_buy_profit_different_from_forex(self, gold_executor: SimulatedExecutor) -> None:
        gold_executor.open_position(
            direction="BUY", volume=0.1, stop_loss=2600.0,
            take_profit=2700.0, symbol="XAUUSD", open_price=2650.0,
            open_time="2026-06-01 12:00:00",
        )
        ticket = gold_executor.open_positions[0].ticket
        gold_executor.close_position(ticket, close_price=2660.0, close_time="2026-06-01 13:00:00")
        trade = gold_executor.closed_trades[0]
        # Gold profit = (2660 - 2650) * 0.1 * 100 = 100
        # minus slippage on close (SELL side), minus commission
        assert trade.profit > 0

    def test_gold_sell_profit(self, gold_executor: SimulatedExecutor) -> None:
        gold_executor.open_position(
            direction="SELL", volume=0.1, stop_loss=2700.0,
            take_profit=2600.0, symbol="XAUUSD", open_price=2650.0,
            open_time="2026-06-01 12:00:00",
        )
        ticket = gold_executor.open_positions[0].ticket
        gold_executor.close_position(ticket, close_price=2640.0, close_time="2026-06-01 13:00:00")
        trade = gold_executor.closed_trades[0]
        # Gold profit = (2650 - 2640) * 0.1 * 100 = 100
        assert trade.profit > 0


# ---------------------------------------------------------------------------
# Slippage & commission
# ---------------------------------------------------------------------------


class TestSlippageAndCommission:
    """Tests for slippage and commission application."""

    def test_slippage_on_entry(self, executor: SimulatedExecutor) -> None:
        result = executor.open_position(
            direction="BUY", volume=1.0, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        # 1 pip slippage for EURUSD = 0.00010
        assert abs(result.price - 1.0850) > 0.00001

    def test_slippage_on_exit_reduces_profit(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        result = executor.close_position(ticket, close_price=1.0860, close_time="2026-06-01 13:00:00")
        # Close price has slippage: 1.0860 - 0.00010 = 1.08590
        assert result.price < 1.0860

    def test_commission_deducted_no_commission(self, executor: SimulatedExecutor) -> None:
        """With zero commission_per_lot, no commission is deducted."""
        assert executor.commission_per_lot == 0.0
        initial_balance = executor.balance
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        assert executor.balance == initial_balance

    def test_commission_is_deducted(self) -> None:
        executor = SimulatedExecutor(
            initial_balance=10000.0, slippage_pips=1.0,
            commission_per_lot=7.0, point=0.00001,
        )
        result = executor.open_position(
            direction="BUY", volume=1.0, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        # 1.0 lot * 7.0 = 7.0 commission
        assert executor.balance == 10000.0 - 7.0
        assert executor.total_commission == 7.0

    def test_total_commission_accumulates(self) -> None:
        executor = SimulatedExecutor(
            initial_balance=10000.0, slippage_pips=0.0,
            commission_per_lot=5.0, point=0.00001,
        )
        executor.open_position(
            direction="BUY", volume=1.0, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        executor.close_position(ticket, close_price=1.0850, close_time="2026-06-01 13:00:00")
        # Commission: 5.0 on open + 5.0 on close = 10.0
        assert executor.total_commission == 10.0


# ---------------------------------------------------------------------------
# get_closed_trades
# ---------------------------------------------------------------------------


class TestGetClosedTrades:
    """Tests for get_closed_trades()."""

    def test_empty_initially(self, executor: SimulatedExecutor) -> None:
        assert executor.get_closed_trades() == []

    def test_returns_closed_trades(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        ticket = executor.open_positions[0].ticket
        executor.close_position(ticket, close_price=1.0860, close_time="2026-06-01 13:00:00")
        trades = executor.get_closed_trades()
        assert len(trades) == 1
        assert isinstance(trades[0], ClosedTrade)


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for resetting state - verifying initial state."""

    def test_initial_state(self) -> None:
        executor = SimulatedExecutor(initial_balance=5000.0)
        assert executor.balance == 5000.0
        assert executor.equity == 5000.0
        assert executor.open_positions == []
        assert executor.closed_trades == []
        assert executor.total_commission == 0.0


# ---------------------------------------------------------------------------
# get_floating_pnl
# ---------------------------------------------------------------------------


class TestFloatingPnL:
    """Tests for get_floating_pnl()."""

    def test_floating_pnl_positive_buy(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        pnl = executor.get_floating_pnl(close_price=1.0900)
        assert pnl > 0

    def test_floating_pnl_negative_buy(self, executor: SimulatedExecutor) -> None:
        executor.open_position(
            direction="BUY", volume=0.1, stop_loss=1.0800,
            take_profit=1.0900, symbol="EURUSD", open_price=1.0850,
            open_time="2026-06-01 12:00:00",
        )
        pnl = executor.get_floating_pnl(close_price=1.0800)
        assert pnl < 0

    def test_floating_pnl_zero_when_no_positions(self, executor: SimulatedExecutor) -> None:
        assert executor.get_floating_pnl(close_price=1.0850) == 0.0
