"""Tests unitaires pour HistoricalDataSource (backtesting)."""

import csv
import os
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.data_source import HistoricalDataSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_csv_path(tmp_path: Path) -> str:
    """Create a temporary CSV with 5 bars of synthetic OHLCV data."""
    csv_file = tmp_path / "test_ohlcv.csv"
    rows = [
        {"datetime": "2026-01-05 08:00:00", "open": 1.08500, "high": 1.08600, "low": 1.08450, "close": 1.08550, "tick_volume": 150, "spread": 1},
        {"datetime": "2026-01-05 08:15:00", "open": 1.08550, "high": 1.08700, "low": 1.08500, "close": 1.08680, "tick_volume": 200, "spread": 1},
        {"datetime": "2026-01-05 08:30:00", "open": 1.08680, "high": 1.08800, "low": 1.08650, "close": 1.08720, "tick_volume": 180, "spread": 1},
        {"datetime": "2026-01-05 08:45:00", "open": 1.08720, "high": 1.08750, "low": 1.08600, "close": 1.08630, "tick_volume": 220, "spread": 2},
        {"datetime": "2026-01-05 09:00:00", "open": 1.08630, "high": 1.08680, "low": 1.08580, "close": 1.08650, "tick_volume": 160, "spread": 1},
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["datetime", "open", "high", "low", "close", "tick_volume", "spread"])
        writer.writeheader()
        writer.writerows(rows)
    return str(csv_file)


@pytest.fixture
def sample_csv_no_spread(tmp_path: Path) -> str:
    """CSV without a 'spread' column to test fallback."""
    csv_file = tmp_path / "test_no_spread.csv"
    rows = [
        {"datetime": "2026-01-05 08:00:00", "open": 1.08500, "high": 1.08600, "low": 1.08450, "close": 1.08550, "tick_volume": 150},
        {"datetime": "2026-01-05 08:15:00", "open": 1.08550, "high": 1.08700, "low": 1.08500, "close": 1.08680, "tick_volume": 200},
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["datetime", "open", "high", "low", "close", "tick_volume"])
        writer.writeheader()
        writer.writerows(rows)
    return str(csv_file)


@pytest.fixture
def loaded_source(sample_csv_path: str) -> HistoricalDataSource:
    """A HistoricalDataSource that already has data loaded."""
    ds = HistoricalDataSource(csv_path=sample_csv_path, symbol="EURUSD")
    ds.load_data()
    return ds


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


class TestLoadData:
    """Tests for load_data()."""

    def test_loads_csv_and_returns_dataframe(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path, symbol="EURUSD")
        df = ds.load_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert "datetime" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns

    def test_datetime_column_is_parsed(self, loaded_source: HistoricalDataSource) -> None:
        df = loaded_source.get_dataframe()
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])

    def test_data_is_sorted_ascending(self, loaded_source: HistoricalDataSource) -> None:
        df = loaded_source.get_dataframe()
        assert df["datetime"].is_monotonic_increasing


# ---------------------------------------------------------------------------
# Rate access
# ---------------------------------------------------------------------------


class TestGetRates:
    """Tests for get_rates()."""

    def test_returns_correct_number_of_bars(self, loaded_source: HistoricalDataSource) -> None:
        rates = loaded_source.get_rates(0, 3)
        assert len(rates) == 3

    def test_returns_correct_slice(self, loaded_source: HistoricalDataSource) -> None:
        rates = loaded_source.get_rates(2, 2)
        assert len(rates) == 2
        # Third bar (index 2) should have close 1.08720
        assert float(rates.iloc[0]["close"]) == 1.08720

    def test_start_idx_out_of_bounds_raises(self, loaded_source: HistoricalDataSource) -> None:
        with pytest.raises(IndexError, match="out of bounds"):
            loaded_source.get_rates(10, 1)

    def test_end_idx_out_of_bounds_raises(self, loaded_source: HistoricalDataSource) -> None:
        with pytest.raises(IndexError, match="out of bounds"):
            loaded_source.get_rates(3, 5)

    def test_negative_start_idx_raises(self, loaded_source: HistoricalDataSource) -> None:
        with pytest.raises(IndexError):
            loaded_source.get_rates(-1, 2)

    def test_not_loaded_raises(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path)
        with pytest.raises(RuntimeError, match="not loaded"):
            ds.get_rates(0, 1)


# ---------------------------------------------------------------------------
# Price / tick access
# ---------------------------------------------------------------------------


class TestGetCurrentPrice:
    """Tests for get_current_price()."""

    def test_returns_close_at_index(self, loaded_source: HistoricalDataSource) -> None:
        price = loaded_source.get_current_price(0)
        assert price == 1.08550

    def test_returns_close_at_last_index(self, loaded_source: HistoricalDataSource) -> None:
        price = loaded_source.get_current_price(4)
        assert price == 1.08650

    def test_not_loaded_raises(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path)
        with pytest.raises(RuntimeError, match="not loaded"):
            ds.get_current_price(0)


class TestGetCurrentTick:
    """Tests for get_current_tick()."""

    def test_bid_ask_around_close(self, loaded_source: HistoricalDataSource) -> None:
        tick = loaded_source.get_current_tick(0)
        # close = 1.08550, spread = 1 point -> bid = close - 0.5 * 1 * point
        # point for EURUSD = 0.00001, so half_spread = 0.000005
        assert "bid" in tick
        assert "ask" in tick
        assert "time" in tick
        assert tick["bid"] < tick["ask"]
        # bid + ask should roughly equal close * 2
        assert abs(float(tick["bid"]) + float(tick["ask"]) - 2 * 1.08550) < 0.001

    def test_bid_lower_than_close(self, loaded_source: HistoricalDataSource) -> None:
        tick = loaded_source.get_current_tick(0)
        close = loaded_source.get_current_price(0)
        assert float(tick["bid"]) <= close

    def test_ask_higher_than_close(self, loaded_source: HistoricalDataSource) -> None:
        tick = loaded_source.get_current_tick(0)
        close = loaded_source.get_current_price(0)
        assert float(tick["ask"]) >= close

    def test_fallback_spread_when_no_spread_column(self, sample_csv_no_spread: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_no_spread, symbol="EURUSD", spread_pips=2.0)
        ds.load_data()
        tick = ds.get_current_tick(0)
        # With spread_pips=2.0, spread_points = 2.0 * 0.00001 = 0.00002
        # half = 0.00001
        assert abs(float(tick["ask"]) - float(tick["bid"])) <= 0.001

    def test_time_is_datetime(self, loaded_source: HistoricalDataSource) -> None:
        tick = loaded_source.get_current_tick(0)
        assert tick["time"] is not None


# ---------------------------------------------------------------------------
# Symbol / account info
# ---------------------------------------------------------------------------


class TestGetSymbolInfo:
    """Tests for get_symbol_info()."""

    @pytest.mark.parametrize(
        "symbol,expected_point,expected_digits",
        [
            ("EURUSD", 0.00001, 5),
            ("GBPUSD", 0.00001, 5),
            ("USDCHF", 0.00001, 5),
            ("AUDUSD", 0.00001, 5),
        ],
    )
    def test_forex_majors_point_and_digits(
        self, symbol: str, expected_point: float, expected_digits: int
    ) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol=symbol)
        info = ds.get_symbol_info()
        assert info["point"] == expected_point
        assert info["digits"] == expected_digits

    @pytest.mark.parametrize(
        "symbol,expected_point,expected_digits",
        [
            ("USDJPY", 0.001, 3),
            ("EURJPY", 0.001, 3),
            ("GBPJPY", 0.001, 3),
        ],
    )
    def test_jpy_pairs_point_and_digits(
        self, symbol: str, expected_point: float, expected_digits: int
    ) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol=symbol)
        info = ds.get_symbol_info()
        assert info["point"] == expected_point
        assert info["digits"] == expected_digits

    def test_xauusd_point_and_digits(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="XAUUSD")
        info = ds.get_symbol_info()
        assert info["point"] == 0.01
        assert info["digits"] == 2

    def test_spread_conversion(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD", spread_pips=2.0)
        info = ds.get_symbol_info()
        # 2.0 pips * 10 = 20 points
        assert info["spread"] == 20

    def test_custom_point_and_digits_override(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD", point=0.0001, digits=4)
        info = ds.get_symbol_info()
        assert info["point"] == 0.0001
        assert info["digits"] == 4

    def test_trade_tick_value_present(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD")
        info = ds.get_symbol_info()
        assert "trade_tick_value" in info


class TestGetAccountInfo:
    """Tests for get_account_info()."""

    def test_initial_balance(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD", initial_balance=5000.0)
        info = ds.get_account_info()
        assert info["balance"] == 5000.0
        assert info["equity"] == 5000.0

    def test_currency_is_usd(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD")
        info = ds.get_account_info()
        assert info["currency"] == "USD"


# ---------------------------------------------------------------------------
# Market state
# ---------------------------------------------------------------------------


class TestIsMarketOpen:
    """Tests for is_market_open()."""

    def test_always_returns_true(self, loaded_source: HistoricalDataSource) -> None:
        assert loaded_source.is_market_open(0) is True
        assert loaded_source.is_market_open(100) is True


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestGetBarCount:
    """Tests for get_bar_count()."""

    def test_returns_correct_count(self, loaded_source: HistoricalDataSource) -> None:
        assert loaded_source.get_bar_count() == 5

    def test_returns_zero_before_load(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path)
        assert ds.get_bar_count() == 0


class TestGetBarDatetime:
    """Tests for get_bar_datetime()."""

    def test_returns_iso_string(self, loaded_source: HistoricalDataSource) -> None:
        dt = loaded_source.get_bar_datetime(0)
        assert "2026-01-05" in dt

    def test_not_loaded_raises(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path)
        with pytest.raises(RuntimeError, match="not loaded"):
            ds.get_bar_datetime(0)


class TestGetDataframe:
    """Tests for get_dataframe()."""

    def test_returns_full_df(self, loaded_source: HistoricalDataSource) -> None:
        df = loaded_source.get_dataframe()
        assert len(df) == 5

    def test_not_loaded_raises(self, sample_csv_path: str) -> None:
        ds = HistoricalDataSource(csv_path=sample_csv_path)
        with pytest.raises(RuntimeError, match="not loaded"):
            ds.get_dataframe()


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


class TestAutoDetection:
    """Tests for symbol parameter auto-detection."""

    @pytest.mark.parametrize(
        "symbol,expected_point,expected_digits",
        [
            ("EURUSD", 0.00001, 5),
            ("USDJPY", 0.001, 3),
            ("XAUUSD", 0.01, 2),
            ("EURJPY", 0.001, 3),
        ],
    )
    def test_auto_detection_from_symbol_name(
        self, symbol: str, expected_point: float, expected_digits: int
    ) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol=symbol)
        assert ds._point == expected_point
        assert ds._digits == expected_digits

    def test_symbol_case_insensitive(self) -> None:
        ds_lower = HistoricalDataSource(csv_path="fake.csv", symbol="eurusd")
        ds_upper = HistoricalDataSource(csv_path="fake.csv", symbol="EURUSD")
        assert ds_lower._point == ds_upper._point
        assert ds_lower._digits == ds_upper._digits

    def test_unknown_symbol_defaults_to_5_digits(self) -> None:
        ds = HistoricalDataSource(csv_path="fake.csv", symbol="USDMXN")
        assert ds._point == 0.00001
        assert ds._digits == 5
