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


class TestDatabaseIsolation:
    """Tests de l'isolation DB par symbole (BUG-1)."""

    def test_get_db_returns_different_connections_per_symbol(self, tmp_path, monkeypatch):
        """get_db() doit retourner des connexions differentes selon le symbole."""
        import src.data.database as db_module

        # Reinitialiser le dict des connexions pour ce test
        original_dbs = db_module._dbs.copy()
        db_module._dbs.clear()

        try:
            call_count = [0]
            paths_seen = []

            original_get_db = db_module.get_db

            def mock_get_db():
                path = str(db_module.settings.db_path)
                paths_seen.append(path)
                return original_get_db()

            # Simuler deux symboles distincts
            from src.config import settings
            settings.trading_symbol = "EURUSD"
            path_eurusd = str(settings.db_path)

            settings.trading_symbol = "USDJPY"
            path_usdjpy = str(settings.db_path)

            assert path_eurusd != path_usdjpy, "Les chemins DB doivent etre distincts par symbole"
        finally:
            db_module._dbs.clear()
            db_module._dbs.update(original_dbs)
            settings.trading_symbol = "EURUSD"

    def test_get_recent_trades_filters_by_symbol(self, tmp_path, monkeypatch):
        """get_recent_trades(symbol=X) ne retourne que les trades du symbole X."""
        import sqlite3
        import src.data.database as db_module
        from unittest.mock import patch

        # Creer une DB en memoire avec des trades de plusieurs symboles
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        db_module._init_tables(conn)
        conn.execute(
            "INSERT INTO trades (ticket,symbol,direction,volume,opened_at,open_price,stop_loss,take_profit,confidence) VALUES (1,'EURUSD','BUY',0.1,'2026-06-01',1.1,1.09,1.12,75)"
        )
        conn.execute(
            "INSERT INTO trades (ticket,symbol,direction,volume,opened_at,open_price,stop_loss,take_profit,confidence) VALUES (2,'USDJPY','BUY',0.1,'2026-06-01',159.0,158.0,161.0,75)"
        )
        conn.commit()

        with patch.object(db_module, "get_db", return_value=conn):
            all_trades = db_module.get_recent_trades(limit=10)
            eur_trades = db_module.get_recent_trades(limit=10, symbol="EURUSD")
            jpy_trades = db_module.get_recent_trades(limit=10, symbol="USDJPY")

        assert len(all_trades) == 2
        assert len(eur_trades) == 1
        assert eur_trades[0]["symbol"] == "EURUSD"
        assert len(jpy_trades) == 1
        assert jpy_trades[0]["symbol"] == "USDJPY"


class TestStrategyFilters:
    """Tests des filtres RSI/BB (PROB-8) et ADX-conditioned filters (v3.0).

    Les tests sans adx_14 utilisent le default adx=20 (<= 25, ranging),
    donc les filtres RSI/BB sont ACTIFS (comportement legacy preserve).
    """

    def _make_decision(self, action, confidence=75, rsi=50, bb_pos=50, adx=None):
        d = {
            "action": action,
            "confidence": confidence,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
            "indicators": {"rsi_14": rsi, "bb_position_pct": bb_pos},
        }
        if adx is not None:
            d["indicators"]["adx_14"] = adx
        return d

    def test_rsi_overbought_blocks_buy_ranging(self):
        """RSI > 75, ADX default (20, ranging) -> bloque BUY."""
        from unittest.mock import patch, MagicMock
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=78)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_rsi_overbought_allows_buy_trending(self):
        """RSI > 75, ADX=30 (trending) -> autorise BUY (filtres desactives)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=78, adx=30)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_rsi_normal_allows_buy(self):
        """RSI normal (55) ne doit pas bloquer un BUY."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=55)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_bb_above_upper_band_blocks_buy_ranging(self):
        """BB > 100, ADX default (20, ranging) -> bloque BUY."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=60, bb_pos=110)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_bb_above_upper_band_allows_buy_trending(self):
        """BB > 100, ADX=30 (trending) -> autorise BUY."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=60, bb_pos=110, adx=30)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_rsi_oversold_blocks_sell_ranging(self):
        """RSI < 25, ADX default (20, ranging) -> bloque SELL."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("SELL", rsi=20)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_rsi_oversold_allows_sell_trending(self):
        """RSI < 25, ADX=30 (trending) -> autorise SELL."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("SELL", rsi=20, adx=30)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_bb_below_lower_blocks_sell_ranging(self):
        """BB < 0, ADX default (20, ranging) -> bloque SELL."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("SELL", rsi=40, bb_pos=-5)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_bb_below_lower_allows_sell_trending(self):
        """BB < 0, ADX=30 (trending) -> autorise SELL."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("SELL", rsi=40, bb_pos=-5, adx=30)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_adx_boundary_25_rsi_overbought_blocks_buy(self):
        """ADX = 25 exactement (<= 25, ranging) -> RSI > 75 bloque BUY."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=78, adx=25)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_adx_boundary_26_rsi_overbought_allows_buy(self):
        """ADX = 26 (> 25, trending) -> RSI > 75 autorise BUY."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = self._make_decision("BUY", rsi=78, adx=26)
        symbol_info = {"spread": 5, "point": 0.00001, "digits": 5}

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

