"""Tests unitaires pour le module executor."""

import pytest
from src.mt5.executor import calculate_position_size, TradeResult


class TestCalculatePositionSize:
    """Tests de la formule de calcul de taille de position."""

    def test_standard_forex_lot(self):
        """EURUSD standard: 10k account, 20 pips SL, 1% risk -> ~0.5 lots."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots = calculate_position_size(10000, 20, symbol_info, risk_pct=1.0)
        assert 0.01 <= lots <= 1.0
        assert round(lots, 2) == 0.5

    def test_minimum_lot_floor(self):
        """Le volume minimum doit etre 0.01 lots."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots = calculate_position_size(500, 50, symbol_info, risk_pct=1.0)
        assert lots == 0.01

    def test_larger_risk_increases_volume(self):
        """Plus de risque = plus de volume."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots_1pct = calculate_position_size(10000, 20, symbol_info, risk_pct=1.0)
        lots_2pct = calculate_position_size(10000, 20, symbol_info, risk_pct=2.0)
        assert lots_2pct > lots_1pct

    def test_wider_stop_loss_reduces_volume(self):
        """Un SL plus large reduit le volume."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots_tight = calculate_position_size(10000, 15, symbol_info, risk_pct=1.0)
        lots_wide = calculate_position_size(10000, 40, symbol_info, risk_pct=1.0)
        assert lots_tight > lots_wide

    def test_zero_stop_loss_returns_minimum(self):
        """SL a 0 -> lot minimum."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots = calculate_position_size(10000, 0, symbol_info, risk_pct=1.0)
        assert lots == 0.01

    def test_negative_stop_loss_returns_minimum(self):
        """SL negatif -> lot minimum."""
        symbol_info = {
            "trade_tick_value": 1.0,
            "point": 0.00001,
        }
        lots = calculate_position_size(10000, -10, symbol_info, risk_pct=1.0)
        assert lots == 0.01


class TestTradeResult:
    """Tests du dataclass TradeResult."""

    def test_successful_trade(self):
        tr = TradeResult(True, 12345, 0.1, 1.0850, 1.0800, 1.0950, "Test")
        assert tr.success is True
        assert tr.ticket == 12345
        assert tr.error is None

    def test_failed_trade(self):
        tr = TradeResult(False, None, 0.1, 1.0850, 1.0800, 1.0950, "Test", "Market closed")
        assert tr.success is False
        assert tr.ticket is None
        assert tr.error == "Market closed"
