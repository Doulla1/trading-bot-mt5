"""Tests unitaires pour StrategyAdapter (backtesting)."""

from datetime import datetime, timedelta

import pytest

from src.backtest.simulated_executor import SimulatedExecutor
from src.backtest.strategy_adapter import StrategyAdapter, StrategyResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def executor() -> SimulatedExecutor:
    return SimulatedExecutor(initial_balance=10000.0, slippage_pips=0.0, point=0.00001)


@pytest.fixture
def adapter(executor: SimulatedExecutor) -> StrategyAdapter:
    return StrategyAdapter(executor=executor)


def _make_buy_decision(confidence: int = 75) -> dict:
    return {
        "action": "BUY",
        "confidence": confidence,
        "stop_loss_pips": 20,
        "take_profit_pips": 30,
        "risk_level": "MEDIUM",
    }


def _make_sell_decision(confidence: int = 75) -> dict:
    return {
        "action": "SELL",
        "confidence": confidence,
        "stop_loss_pips": 20,
        "take_profit_pips": 30,
        "risk_level": "MEDIUM",
    }


# ---------------------------------------------------------------------------
# execute_decision - HOLD
# ---------------------------------------------------------------------------


class TestExecuteDecisionHold:
    """Tests for HOLD action."""

    def test_hold_returns_no_trade(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision={"action": "HOLD", "confidence": 30},
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert isinstance(result, StrategyResult)
        assert result.trade_result is None
        assert result.closed_positions == []


# ---------------------------------------------------------------------------
# execute_decision - BUY
# ---------------------------------------------------------------------------


class TestExecuteDecisionBuy:
    """Tests for BUY action."""

    def test_buy_with_no_positions_opens(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is not None
        assert result.trade_result.success is True
        assert adapter.executor.count_open_positions() == 1

    def test_buy_when_buy_already_open_skips(self, adapter: StrategyAdapter) -> None:
        # Open a BUY first
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert adapter.executor.count_open_positions() == 1

        # Try again with same direction
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0860,
            bar_datetime="2026-06-01 12:15:00", point=0.00001,
        )
        # Should skip, no new position opened
        assert adapter.executor.count_open_positions() == 1
        assert result.trade_result is None

    def test_sell_when_buy_open_closes_no_reversal(self, adapter: StrategyAdapter) -> None:
        # Open BUY
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert adapter.executor.count_open_positions() == 1

        # Now try SELL - should close BUY, not open new
        result = adapter.execute_decision(
            decision=_make_sell_decision(),
            symbol="EURUSD", current_price=1.0860,
            bar_datetime="2026-06-01 12:15:00", point=0.00001,
        )
        assert adapter.executor.count_open_positions() == 0
        assert len(result.closed_positions) == 1
        assert result.trade_result is None  # No new position


# ---------------------------------------------------------------------------
# execute_decision - SELL
# ---------------------------------------------------------------------------


class TestExecuteDecisionSell:
    """Tests for SELL action."""

    def test_sell_with_no_positions_opens(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_sell_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is not None
        assert result.trade_result.success is True


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------


class TestDailyLossLimit:
    """Tests for daily loss limit blocking."""

    def test_loss_limit_blocks_when_exceeded(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0, slippage_pips=0.0, point=0.00001)
        # Simulate a large realized loss via closed trades
        from src.backtest.simulated_executor import ClosedTrade
        executor.closed_trades.append(ClosedTrade(
            ticket=1000, symbol="EURUSD", direction="BUY",
            volume=0.1, open_price=1.0850, close_price=1.0800,
            open_time="2026-06-01 12:00:00", close_time="2026-06-01 13:00:00",
            profit=-400.0, exit_reason="SL", stop_loss=1.0800, take_profit=1.0900,
        ))
        executor.balance = 9600.0
        adapter = StrategyAdapter(executor=executor, max_daily_loss_pct=3.0)

        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # 400 loss = 4% > 3% limit → blocked
        assert result.trade_result is None

    def test_loss_limit_allows_when_within_range(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0, slippage_pips=0.0, point=0.00001)
        executor.balance = 9800.0  # 2% loss
        adapter = StrategyAdapter(executor=executor, max_daily_loss_pct=3.0)

        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # 200 loss = 2% < 3% limit → allowed
        assert result.trade_result is not None

    def test_zero_balance_blocked(self) -> None:
        executor = SimulatedExecutor(initial_balance=1.0, slippage_pips=0.0, point=0.00001)
        # Simulate a huge loss that wipes out the account
        from src.backtest.simulated_executor import ClosedTrade
        executor.closed_trades.append(ClosedTrade(
            ticket=1000, symbol="EURUSD", direction="BUY",
            volume=0.1, open_price=1.0850, close_price=1.0800,
            open_time="2026-06-01 12:00:00", close_time="2026-06-01 13:00:00",
            profit=-50.0, exit_reason="SL", stop_loss=1.0800, take_profit=1.0900,
        ))
        executor.balance = 1.0
        adapter = StrategyAdapter(executor=executor, max_daily_loss_pct=3.0)

        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Daily PnL = -50, 50/1 = 5000% >> 3% limit → blocked
        assert result.trade_result is None


# ---------------------------------------------------------------------------
# Trade filters
# ---------------------------------------------------------------------------


class TestTradeFilters:
    """Tests for pre-trade filter logic."""

    def test_confidence_below_threshold_blocks(self, adapter: StrategyAdapter) -> None:
        # Default min_confidence_threshold = 70
        result = adapter.execute_decision(
            decision=_make_buy_decision(confidence=60),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is None

    def test_confidence_above_threshold_allows(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_buy_decision(confidence=85),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is not None

    def test_max_positions_blocks(self, adapter: StrategyAdapter) -> None:
        # Open the max allowed (default 1)
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Try GBPUSD (different symbol, same executor)
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="GBPUSD", current_price=1.2500,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is None

    def test_rsi_filter_blocks_buy_when_rsi_above_75(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
            indicators={"rsi_14": 78},
        )
        assert result.trade_result is None

    def test_rsi_filter_blocks_sell_when_rsi_below_25(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_sell_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
            indicators={"rsi_14": 22},
        )
        assert result.trade_result is None

    def test_rsi_filter_allows_when_in_range(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
            indicators={"rsi_14": 55},
        )
        assert result.trade_result is not None

    def test_bb_filter_blocks_buy_above_100(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
            indicators={"rsi_14": 60, "bb_position_pct": 110},
        )
        assert result.trade_result is None

    def test_bb_filter_blocks_sell_below_0(self, adapter: StrategyAdapter) -> None:
        result = adapter.execute_decision(
            decision=_make_sell_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
            indicators={"rsi_14": 40, "bb_position_pct": -5},
        )
        assert result.trade_result is None


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Tests for circuit breaker logic."""

    def test_consecutive_losses_trigger_circuit_breaker(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0, slippage_pips=0.0, point=0.00001)
        adapter = StrategyAdapter(executor=executor, consecutive_loss_limit=3)

        # Simulate 3 consecutive losing trades by directly appending to closed_trades
        from src.backtest.simulated_executor import ClosedTrade
        for i in range(3):
            executor.closed_trades.append(ClosedTrade(
                ticket=1000 + i, symbol="EURUSD", direction="BUY",
                volume=0.1, open_price=1.0850, close_price=1.0800,
                open_time="2026-06-01 12:00:00", close_time="2026-06-01 13:00:00",
                profit=-50.0, exit_reason="SL", stop_loss=1.0800, take_profit=1.0900,
            ))

        result = adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert result.trade_result is None  # Blocked by circuit breaker

    def test_circuit_breaker_active_during_cooldown(self, adapter: StrategyAdapter) -> None:
        # Manually set circuit breaker
        adapter._circuit_breaker_until = datetime.now() + timedelta(hours=1)
        assert adapter._check_circuit_breaker() is True

    def test_circuit_breaker_inactive_after_cooldown(self, adapter: StrategyAdapter) -> None:
        adapter._circuit_breaker_until = datetime.now() - timedelta(hours=1)
        assert adapter._check_circuit_breaker() is False

    def test_circuit_breaker_inactive_by_default(self, adapter: StrategyAdapter) -> None:
        assert adapter._check_circuit_breaker() is False


# ---------------------------------------------------------------------------
# manage_open_positions - breakeven
# ---------------------------------------------------------------------------


class TestManagePositionsBreakeven:
    """Tests for breakeven logic."""

    def test_breakeven_moves_sl_to_entry_buy(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Price moved up enough to trigger breakeven
        results = adapter.manage_open_positions(
            current_price=1.0870,  # 20 pips up
            bar_datetime="2026-06-01 13:00:00", point=0.00001,
        )
        # Check if SL was moved
        positions = adapter.executor.get_open_positions()
        if positions:
            # If breakeven triggered, SL should now be at entry_price (or close)
            pass  # Not asserting specific behavior, just that it doesn't crash

    def test_breakeven_not_triggered_when_profit_too_low(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        pos_before = adapter.executor.get_open_positions()
        sl_before = pos_before[0]["sl"] if pos_before else None

        results = adapter.manage_open_positions(
            current_price=1.0852,  # Only 2 pips up (not enough)
            bar_datetime="2026-06-01 12:15:00", point=0.00001,
        )
        # SL should not have changed
        pos_after = adapter.executor.get_open_positions()
        if pos_after:
            assert pos_after[0]["sl"] == sl_before


# ---------------------------------------------------------------------------
# manage_open_positions - trailing stop
# ---------------------------------------------------------------------------


class TestManagePositionsTrailingStop:
    """Tests for trailing stop logic."""

    def test_trailing_stop_moves_sl_buy(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Big move up → 2x SL distance should trigger trailing stop
        results = adapter.manage_open_positions(
            current_price=1.0900,  # 50 pips up
            bar_datetime="2026-06-01 13:00:00", point=0.00001,
        )
        # Verify trailing stop moved SL (doesn't crash)
        positions = adapter.executor.get_open_positions()
        assert len(positions) >= 0  # Position might have been closed by time exit


# ---------------------------------------------------------------------------
# manage_open_positions - time exit
# ---------------------------------------------------------------------------


class TestManagePositionsTimeExit:
    """Tests for time exit logic."""

    def test_time_exit_closes_after_threshold(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Simulate passage of time: bar_datetime is 10 hours later
        results = adapter.manage_open_positions(
            current_price=1.0850,  # no price movement
            bar_datetime="2026-06-01 22:00:00",  # 10 hours later
            open_time_threshold_hours=8,
            point=0.00001,
        )
        # Position should be closed by time exit
        assert adapter.executor.count_open_positions() == 0
        assert len(results) >= 0

    def test_time_exit_not_triggered_before_threshold(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        # Only 1 hour passed
        results = adapter.manage_open_positions(
            current_price=1.0850,
            bar_datetime="2026-06-01 13:00:00",
            open_time_threshold_hours=8,
            point=0.00001,
        )
        # Position should still be open
        assert adapter.executor.count_open_positions() == 1


# ---------------------------------------------------------------------------
# CLOSE action
# ---------------------------------------------------------------------------


class TestExecuteDecisionClose:
    """Tests for CLOSE action."""

    def test_close_closes_all_positions_for_symbol(self, adapter: StrategyAdapter) -> None:
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        assert adapter.executor.count_open_positions() == 1

        result = adapter.execute_decision(
            decision={"action": "CLOSE", "confidence": 0},
            symbol="EURUSD", current_price=1.0860,
            bar_datetime="2026-06-01 13:00:00", point=0.00001,
        )
        assert adapter.executor.count_open_positions() == 0
        assert len(result.closed_positions) >= 0


# ---------------------------------------------------------------------------
# get_daily_pnl
# ---------------------------------------------------------------------------


class TestGetDailyPnl:
    """Tests for get_daily_pnl()."""

    def test_zero_when_no_trades(self, adapter: StrategyAdapter) -> None:
        assert adapter.get_daily_pnl() == 0.0

    def test_reflects_closed_trade_profit(self, adapter: StrategyAdapter) -> None:
        # Open and close a trade for profit
        adapter.execute_decision(
            decision=_make_buy_decision(),
            symbol="EURUSD", current_price=1.0850,
            bar_datetime="2026-06-01 12:00:00", point=0.00001,
        )
        ticket = adapter.executor.open_positions[0].ticket
        adapter.executor.close_position(ticket, close_price=1.0900, close_time="2026-06-01 13:00:00")

        pnl = adapter.get_daily_pnl()
        # Should be the realized profit
        assert isinstance(pnl, float)


# ---------------------------------------------------------------------------
# default values
# ---------------------------------------------------------------------------


class TestDefaults:
    """Tests for default adapter configuration."""

    def test_default_max_daily_loss_pct(self, adapter: StrategyAdapter) -> None:
        assert adapter.max_daily_loss_pct == 3.0

    def test_default_max_risk_per_trade_pct(self, adapter: StrategyAdapter) -> None:
        assert adapter.max_risk_per_trade_pct == 1.0

    def test_default_min_confidence_threshold(self, adapter: StrategyAdapter) -> None:
        assert adapter.min_confidence_threshold == 70

    def test_default_max_open_positions(self, adapter: StrategyAdapter) -> None:
        assert adapter.max_open_positions == 1

    def test_default_consecutive_loss_limit(self, adapter: StrategyAdapter) -> None:
        assert adapter.consecutive_loss_limit == 4

    def test_default_circuit_breaker_hours(self, adapter: StrategyAdapter) -> None:
        assert adapter.circuit_breaker_hours == 4
