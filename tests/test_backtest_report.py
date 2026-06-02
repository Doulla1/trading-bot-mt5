"""Tests unitaires pour BacktestReport (backtesting)."""

import json

import pandas as pd
import pytest

from src.backtest.report import (
    BacktestMetrics,
    BacktestReport,
    generate_multi_symbol_report,
)
from src.backtest.simulated_executor import (
    ClosedTrade,
    SimulatedExecutor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(
    ticket: int,
    profit: float,
    exit_reason: str = "TP",
    open_time: str = "2026-06-01 12:00:00",
    close_time: str = "2026-06-01 15:00:00",
    direction: str = "BUY",
    symbol: str = "EURUSD",
) -> ClosedTrade:
    return ClosedTrade(
        ticket=ticket,
        symbol=symbol,
        direction=direction,
        volume=0.1,
        open_price=1.0850,
        close_price=1.0900 if direction == "BUY" else 1.0800,
        open_time=open_time,
        close_time=close_time,
        profit=profit,
        exit_reason=exit_reason,
        stop_loss=1.0800,
        take_profit=1.0900,
    )


def _executor_with_trades(trades: list[ClosedTrade], balance: float = 10000.0) -> SimulatedExecutor:
    """Create a SimulatedExecutor with pre-populated closed trades."""
    executor = SimulatedExecutor(initial_balance=balance, point=0.00001)
    executor.closed_trades = list(trades)
    # Adjust balance based on trades
    total_profit = sum(t.profit for t in trades)
    executor.balance = balance + total_profit
    executor.equity = executor.balance
    return executor


# ---------------------------------------------------------------------------
# compute()
# ---------------------------------------------------------------------------


class TestCompute:
    """Tests for BacktestReport.compute()."""

    def test_compute_with_wins_and_losses(self) -> None:
        trades = [
            _make_trade(1, 100.0, "TP"),
            _make_trade(2, -50.0, "SL"),
            _make_trade(3, 75.0, "TP"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.net_profit == 125.0

    def test_compute_with_zero_trades(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.total_trades == 0
        assert metrics.net_profit == 0.0

    def test_gross_profit_and_loss(self) -> None:
        trades = [
            _make_trade(1, 200.0, "TP"),
            _make_trade(2, -100.0, "SL"),
            _make_trade(3, 50.0, "TP"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.gross_profit == 250.0
        assert metrics.gross_loss == -100.0

    def test_largest_win_and_loss(self) -> None:
        trades = [
            _make_trade(1, 200.0, "TP"),
            _make_trade(2, -50.0, "SL"),
            _make_trade(3, 80.0, "TP"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.largest_win == 200.0
        assert metrics.largest_loss == -50.0

    def test_exit_reasons_counted(self) -> None:
        trades = [
            _make_trade(1, 100.0, "TP", close_time="2026-06-01 14:00:00"),
            _make_trade(2, -50.0, "SL", close_time="2026-06-01 16:00:00"),
            _make_trade(3, 30.0, "TP", close_time="2026-06-01 18:00:00"),
            _make_trade(4, -20.0, "TIME_EXIT", close_time="2026-06-01 20:00:00"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01 12:00:00", end_date="2026-06-01 20:00:00",
        )
        metrics = report.compute()

        assert metrics.exit_reasons.get("TP") == 2
        assert metrics.exit_reasons.get("SL") == 1
        assert metrics.exit_reasons.get("TIME_EXIT") == 1


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------


class TestWinRate:
    """Tests for win_rate calculation."""

    def test_2_wins_1_loss_66_7_pct(self) -> None:
        trades = [
            _make_trade(1, 100.0),
            _make_trade(2, 50.0),
            _make_trade(3, -80.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.win_rate_pct == pytest.approx(66.67, rel=0.1)

    def test_all_wins_100_pct(self) -> None:
        trades = [
            _make_trade(1, 100.0),
            _make_trade(2, 50.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.win_rate_pct == 100.0

    def test_all_losses_0_pct(self) -> None:
        trades = [
            _make_trade(1, -50.0),
            _make_trade(2, -30.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.win_rate_pct == 0.0


# ---------------------------------------------------------------------------
# profit_factor
# ---------------------------------------------------------------------------


class TestProfitFactor:
    """Tests for profit_factor calculation."""

    def test_profit_factor_greater_than_1_when_profitable(self) -> None:
        trades = [
            _make_trade(1, 200.0),
            _make_trade(2, -100.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.profit_factor == 2.0

    def test_profit_factor_less_than_1_when_losing(self) -> None:
        trades = [
            _make_trade(1, 100.0),
            _make_trade(2, -200.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.profit_factor == 0.5

    def test_profit_factor_zero_when_no_trades(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.profit_factor == 0.0

    def test_profit_factor_inf_when_no_losses(self) -> None:
        trades = [
            _make_trade(1, 100.0),
            _make_trade(2, 50.0),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.profit_factor == float("inf")


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    """Tests for max_drawdown calculation."""

    def test_drawdown_from_equity_curve(self) -> None:
        trades = [
            _make_trade(1, 200.0, close_time="2026-06-01 14:00:00"),
            _make_trade(2, -300.0, close_time="2026-06-01 16:00:00"),
            _make_trade(3, 100.0, close_time="2026-06-01 18:00:00"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        # Peak at 10200, drop to 9900 = 300 drawdown = 2.94%
        assert metrics.max_drawdown_pct > 0

    def test_drawdown_zero_when_only_profits(self) -> None:
        trades = [
            _make_trade(1, 100.0, close_time="2026-06-01 14:00:00"),
            _make_trade(2, 50.0, close_time="2026-06-01 16:00:00"),
        ]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        metrics = report.compute()

        assert metrics.max_drawdown_pct == 0.0

    def test_explicit_equity_curve_used(self) -> None:
        trades = [_make_trade(1, 50.0)]
        executor = _executor_with_trades(trades)
        equity_curve = [
            ("2026-06-01 12:00:00", 10000.0),
            ("2026-06-01 14:00:00", 9800.0),  # -2%
            ("2026-06-01 16:00:00", 9900.0),
            ("2026-06-01 18:00:00", 10200.0),
        ]
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
            equity_curve=equity_curve,
        )
        metrics = report.compute()
        # max DD from 10000 to 9800 = 200, 200/10000 * 100 = 2.0%
        assert metrics.max_drawdown_pct == pytest.approx(2.0, rel=0.1)


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------


class TestSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_sharpe_with_known_returns(self) -> None:
        """
        Create a multi-day equity curve with known daily returns.
        Equity: 10000, 10100, 10050, 10200, 10180
        Daily returns: +1%, -0.5%, +1.5%, -0.2%
        Sharpe = mean(daily_ret) / std(daily_ret) * sqrt(252)
        """
        trades = [_make_trade(1, 180.0, close_time="2026-06-05 12:00:00")]
        executor = _executor_with_trades(trades)
        equity_curve = [
            ("2026-06-01 12:00:00", 10000.0),
            ("2026-06-02 12:00:00", 10100.0),
            ("2026-06-03 12:00:00", 10050.0),
            ("2026-06-04 12:00:00", 10200.0),
            ("2026-06-05 12:00:00", 10180.0),
        ]
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-05",
            equity_curve=equity_curve,
        )
        metrics = report.compute()

        # Sharpe should be a finite number (positive since net return is positive)
        assert isinstance(metrics.sharpe_ratio, float)
        assert not (metrics.sharpe_ratio != metrics.sharpe_ratio)  # not NaN

    def test_sharpe_zero_with_insufficient_data(self) -> None:
        executor = _executor_with_trades([])
        equity_curve = [
            ("2026-06-01 12:00:00", 10000.0),
            ("2026-06-01 13:00:00", 10100.0),
        ]
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-01",
            equity_curve=equity_curve,
        )
        metrics = report.compute()
        assert metrics.sharpe_ratio == 0.0


# ---------------------------------------------------------------------------
# summary_table
# ---------------------------------------------------------------------------


class TestSummaryTable:
    """Tests for summary_table()."""

    def test_returns_string(self) -> None:
        trades = [_make_trade(1, 100.0)]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        table = report.summary_table()
        assert isinstance(table, str)
        assert "BACKTEST REPORT" in table
        assert "EURUSD" in table

    def test_computes_if_not_computed_yet(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        table = report.summary_table()
        assert isinstance(table, str)


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    """Tests for to_dict()."""

    def test_returns_json_serializable(self) -> None:
        trades = [_make_trade(1, 100.0, "TP"), _make_trade(2, -50.0, "SL")]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        d = report.to_dict()
        # Should be JSON serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_contains_all_expected_keys(self) -> None:
        trades = [_make_trade(1, 100.0)]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        d = report.to_dict()

        expected_keys = {
            "symbol", "start_date", "end_date", "initial_balance",
            "final_balance", "final_equity", "total_trades",
            "winning_trades", "losing_trades", "win_rate_pct",
            "net_profit", "gross_profit", "gross_loss", "profit_factor",
            "avg_win", "avg_loss", "avg_trade",
            "largest_win", "largest_loss",
            "max_drawdown_pct", "max_drawdown_duration_bars",
            "sharpe_ratio", "sortino_ratio", "return_pct",
            "exit_reasons", "avg_bars_held", "avg_hours_held",
            "equity_curve", "drawdown_curve",
        }
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"

    def test_profit_factor_inf_becomes_string(self) -> None:
        trades = [_make_trade(1, 100.0), _make_trade(2, 50.0)]  # no losses
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        d = report.to_dict()
        assert d["profit_factor"] == "inf"


# ---------------------------------------------------------------------------
# to_dataframe
# ---------------------------------------------------------------------------


class TestToDataframe:
    """Tests for to_dataframe()."""

    def test_returns_dataframe(self) -> None:
        trades = [_make_trade(1, 100.0), _make_trade(2, -50.0)]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        df = report.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_empty_when_no_trades(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        df = report.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# print_report
# ---------------------------------------------------------------------------


class TestPrintReport:
    """Tests for print_report()."""

    def test_does_not_raise(self, capsys: pytest.CaptureFixture) -> None:
        trades = [_make_trade(1, 100.0)]
        executor = _executor_with_trades(trades)
        report = BacktestReport(
            executor=executor, initial_balance=10000.0,
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
        )
        report.print_report()
        captured = capsys.readouterr()
        assert "BACKTEST REPORT" in captured.out


# ---------------------------------------------------------------------------
# generate_multi_symbol_report
# ---------------------------------------------------------------------------


class TestGenerateMultiSymbolReport:
    """Tests for generate_multi_symbol_report()."""

    def test_works_with_two_symbols(self) -> None:
        eur_trades = [_make_trade(1, 100.0, symbol="EURUSD")]
        gbp_trades = [_make_trade(2, -30.0, symbol="GBPUSD")]

        eur_executor = _executor_with_trades(eur_trades)
        gbp_executor = _executor_with_trades(gbp_trades)

        symbol_results = {
            "EURUSD": {"executor": eur_executor, "start_date": "2026-06-01", "end_date": "2026-06-02"},
            "GBPUSD": {"executor": gbp_executor, "start_date": "2026-06-01", "end_date": "2026-06-02"},
        }

        df = generate_multi_symbol_report(symbol_results, initial_balance=10000.0)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "Symbol" in df.columns
        assert "Win Rate" in df.columns
        assert "Net Profit" in df.columns

    def test_works_with_empty_results(self) -> None:
        executor = SimulatedExecutor(initial_balance=10000.0)
        symbol_results = {
            "EURUSD": {"executor": executor, "start_date": "2026-06-01", "end_date": "2026-06-02"},
        }
        df = generate_multi_symbol_report(symbol_results, initial_balance=10000.0)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# BacktestMetrics dataclass
# ---------------------------------------------------------------------------


class TestBacktestMetricsDataclass:
    """Tests for the BacktestMetrics dataclass."""

    def test_default_values(self) -> None:
        m = BacktestMetrics(
            symbol="TEST", start_date="2026-01-01", end_date="2026-01-02",
            initial_balance=10000.0, final_balance=10000.0, final_equity=10000.0,
        )
        assert m.total_trades == 0
        assert m.win_rate_pct == 0.0
        assert m.sharpe_ratio == 0.0
        assert m.exit_reasons == {}

    def test_fields_populated(self) -> None:
        m = BacktestMetrics(
            symbol="EURUSD", start_date="2026-06-01", end_date="2026-06-02",
            initial_balance=10000.0, final_balance=10125.0, final_equity=10125.0,
            total_trades=3, winning_trades=2, losing_trades=1,
            win_rate_pct=66.7, net_profit=125.0, gross_profit=250.0, gross_loss=-125.0,
            profit_factor=2.0, sharpe_ratio=1.5, sortino_ratio=2.0,
            avg_win=125.0, avg_loss=-125.0, avg_trade=41.67,
            largest_win=200.0, largest_loss=-125.0,
            max_drawdown_pct=1.5, max_drawdown_duration_bars=10,
            return_pct=1.25,
            exit_reasons={"TP": 2, "SL": 1},
            avg_bars_held=4.0, avg_hours_held=1.0,
            equity_curve=[("2026-06-01", 10000.0)],
            drawdown_curve=[("2026-06-01", 0.0)],
        )
        assert m.symbol == "EURUSD"
        assert m.total_trades == 3
        assert m.profit_factor == 2.0
        assert m.sharpe_ratio == 1.5
