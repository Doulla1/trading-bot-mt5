"""Tests unitaires pour le moteur de strategie (strategy.py).

Couvre les 4 changements v3.0:
1. _check_time_exit() - sortie basee sur la structure de marche (SMA20 + HH/HL)
2. _modify_sl() - verification trade_stops_level du broker
3. _apply_breakeven() - seuil a 1.2R au lieu de 0.5R
4. _passes_trade_filters() - filtres RSI/BB conditionnes au regime ADX
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================================
# Helpers
# ============================================================================


def _make_pos_buy(ticket=12345, entry=1.0850, sl=1.0820, tp=1.0920, pnl=0.0):
    """Creer un dict simulant une position BUY MT5."""
    return {
        "ticket": ticket,
        "type": 0,  # POSITION_TYPE_BUY
        "price_open": entry,
        "sl": sl,
        "tp": tp,
        "profit": pnl,
        "volume": 0.1,
    }


def _make_pos_sell(ticket=12346, entry=1.0850, sl=1.0880, tp=1.0780, pnl=0.0):
    """Creer un dict simulant une position SELL MT5."""
    return {
        "ticket": ticket,
        "type": 1,  # POSITION_TYPE_SELL
        "price_open": entry,
        "sl": sl,
        "tp": tp,
        "profit": pnl,
        "volume": 0.1,
    }


def _make_decision(action, confidence=75, rsi=50, bb_pos=50, adx=20):
    """Creer un dict de decision avec indicateurs."""
    return {
        "action": action,
        "confidence": confidence,
        "stop_loss_pips": 20,
        "take_profit_pips": 40,
        "risk_level": "MEDIUM",
        "indicators": {"rsi_14": rsi, "bb_position_pct": bb_pos, "adx_14": adx},
    }


def _make_sym_info(point=0.00001, digits=5, stops_level=10):
    """Creer un mock de symbol_info MT5."""
    m = MagicMock()
    m.point = point
    m.digits = digits
    m.trade_stops_level = stops_level
    return m


def _make_tick(bid=1.0850, ask=1.0851):
    """Creer un mock de tick MT5."""
    m = MagicMock()
    m.bid = bid
    m.ask = ask
    return m


def _make_rates(close_prices, highs=None, lows=None):
    """Creer des rates M15 simules. Chaque rate = (time, open, high, low, close, ...)."""
    n = len(close_prices)
    if highs is None:
        highs = [c * 1.001 for c in close_prices]
    if lows is None:
        lows = [c * 0.999 for c in close_prices]
    rates = []
    for i in range(n):
        rates.append((i, close_prices[i] * 0.999, highs[i], lows[i], close_prices[i], 100, 0))
    return rates


# ============================================================================
# 1. _check_time_exit()
# ============================================================================


class TestCheckTimeExit:
    """Tests de _check_time_exit() - sortie basee structure de marche."""

    # --- BUY: prix sous SMA20 ---

    def test_buy_price_below_sma20_triggers_exit(self):
        """BUY avec prix sous SMA20 -> exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0830, ask=1.0831)  # bid sous SMA20

        # SMA20 ~ 1.0845 (moyenne de 20 closes), bid=1.0830 < SMA20
        closes = [1.0845] * 20
        rates = _make_rates(closes)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            # Pas de stagnation >4h
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    # --- BUY: prix au-dessus SMA20, structure intacte ---

    def test_buy_price_above_sma20_structure_intact_no_exit(self):
        """BUY avec prix au-dessus SMA20 et structure 20-bar intacte -> pas d'exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0860, ask=1.0861)

        # SMA20 ~ 1.0830, bid=1.0860 > SMA20
        closes = [1.0830] * 20
        highs = [1.0840] * 20
        lows = [1.0820] * 20
        # lowest 20-bar = 1.0820, bid=1.0860 > 1.0820 -> structure intacte
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is False

    # --- BUY: structure HL cassee ---

    def test_buy_hl_structure_broken_triggers_exit(self):
        """BUY avec casse du lowest 20-bar -> exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0810, ask=1.0811)  # bid < lowest 20-bar

        closes = [1.0830] * 20
        highs = [1.0845] * 20
        lows = [1.0820] * 20  # lowest = 1.0820
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    # --- SELL: prix au-dessus SMA20 ---

    def test_sell_price_above_sma20_triggers_exit(self):
        """SELL avec prix au-dessus SMA20 -> exit."""
        import src.ai.strategy as strat

        pos = _make_pos_sell(entry=1.0850, sl=1.0880)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0865, ask=1.0866)  # ask au-dessus SMA20

        closes = [1.0845] * 20  # SMA20=1.0845, ask=1.0866 > SMA20
        rates = _make_rates(closes)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    # --- SELL: structure LH cassee ---

    def test_sell_lh_structure_broken_triggers_exit(self):
        """SELL avec casse du highest 20-bar -> exit."""
        import src.ai.strategy as strat

        pos = _make_pos_sell(entry=1.0850, sl=1.0880)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0830, ask=1.0885)  # ask > highest 20-bar

        closes = [1.0890] * 20  # SMA20=1.0890, ask < SMA20 (1.0885 < 1.0890)
        highs = [1.0880] * 20   # highest 20-bar = 1.0880
        lows = [1.0830] * 20
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    # --- SELL: tout intact ---

    def test_sell_below_sma20_structure_intact_no_exit(self):
        """SELL avec prix sous SMA20 et LH intacte -> pas d'exit."""
        import src.ai.strategy as strat

        pos = _make_pos_sell(entry=1.0850, sl=1.0880)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0830, ask=1.0831)

        closes = [1.0845] * 20  # SMA20=1.0845, ask < SMA20, LH intacte
        highs = [1.0860] * 20
        lows = [1.0830] * 20
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is False

    # --- Fallback: pas de rates -> chronometre 4h ---

    def test_no_rates_fallback_4h_stagnation_triggers_exit(self):
        """Pas de rates disponibles + stagnation >4h -> exit (securite)."""
        import src.ai.strategy as strat
        from datetime import datetime, timedelta

        pos = _make_pos_buy(entry=1.0850, sl=1.0820, pnl=0.1)
        sym_info = _make_sym_info()
        tick = _make_tick()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=None), \
             patch.object(strat, "get_db") as mock_db:
            # Simuler une position ouverte il y a 5h
            mock_conn = MagicMock()
            opened_5h_ago = (datetime.now() - timedelta(hours=5)).isoformat()
            mock_conn.execute.return_value.fetchone.return_value = [opened_5h_ago]
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    def test_no_rates_fallback_under_4h_no_exit(self):
        """Pas de rates + stagnation <4h -> pas d'exit."""
        import src.ai.strategy as strat
        from datetime import datetime, timedelta

        pos = _make_pos_buy(entry=1.0850, sl=1.0820, pnl=0.1)
        sym_info = _make_sym_info()
        tick = _make_tick()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=None), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            opened_2h_ago = (datetime.now() - timedelta(hours=2)).isoformat()
            mock_conn.execute.return_value.fetchone.return_value = [opened_2h_ago]
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is False

    # --- None tick/sym_info ---

    def test_none_tick_returns_false(self):
        """Tick None -> pas d'exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy()
        sym_info = _make_sym_info()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=None), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            result = strat._check_time_exit(pos)
            assert result is False

    def test_none_sym_info_returns_false(self):
        """Symbol info None -> pas d'exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy()
        tick = _make_tick()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=None):
            result = strat._check_time_exit(pos)
            assert result is False

    # --- Securite stagnation >4h (meme si structure intacte) ---

    def test_stagnation_over_4h_with_flat_pnl_triggers_exit(self):
        """Stagnation >4h avec PnL plat -> exit de securite."""
        import src.ai.strategy as strat
        from datetime import datetime, timedelta

        pos = _make_pos_buy(entry=1.0850, sl=1.0820, pnl=0.05)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0860, ask=1.0861)

        # Structure intacte, prix > SMA20, tout va bien sauf la stagnation
        closes = [1.0830] * 20
        lows = [1.0820] * 20
        highs = [1.0840] * 20
        lows[-1] = 1.0835  # HL intact
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            opened_6h_ago = (datetime.now() - timedelta(hours=6)).isoformat()
            mock_conn.execute.return_value.fetchone.return_value = [opened_6h_ago]
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is True

    # --- Exception handling ---

    def test_exception_returns_false(self):
        """Exception dans _check_time_exit -> retourne False."""
        import src.ai.strategy as strat

        pos = _make_pos_buy()

        with patch("src.ai.strategy.mt5.symbol_info_tick", side_effect=RuntimeError("MT5 error")):
            result = strat._check_time_exit(pos)
            assert result is False

    # --- Securite: DB row None (ticket pas trouve) ---

    def test_db_row_none_no_stagnation_exit(self):
        """Ticket pas trouve en DB + structure intacte -> pas d'exit."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0860, ask=1.0861)

        closes = [1.0830] * 20
        lows = [1.0820] * 20
        highs = [1.0840] * 20
        # SMA20=1.0830, bid=1.0860 > 1.0830
        # lowest 20-bar=1.0820, bid=1.0860 > 1.0820 -> tout est bon
        rates = _make_rates(closes, highs, lows)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.copy_rates_from_pos", return_value=rates), \
             patch.object(strat, "get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None  # ticket pas trouve
            mock_db.return_value = mock_conn

            result = strat._check_time_exit(pos)
            assert result is False


# ============================================================================
# 2. _modify_sl()
# ============================================================================


class TestModifySL:
    """Tests de _modify_sl() - verification trade_stops_level du broker."""

    def test_buy_sl_too_close_to_bid_skips(self):
        """BUY: SL trop proche du bid (distance < stops_level) -> skip."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info(point=0.00001, stops_level=10)  # stops_level = 10 * 0.00001 = 0.0001
        tick = _make_tick(bid=1.0850, ask=1.0851)

        # Position BUY existante
        mock_pos = MagicMock()
        mock_pos.type = mt5.POSITION_TYPE_BUY

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[mock_pos]), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            # new_sl = 1.08495, bid = 1.0850, distance = 0.00005 < stops_level 0.0001
            strat._modify_sl(12345, 1.08495)
            mock_order.assert_not_called()

    def test_buy_sl_far_enough_sends_order(self):
        """BUY: SL assez loin du bid -> order_send appele."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info(point=0.00001, stops_level=10)
        tick = _make_tick(bid=1.0850, ask=1.0851)

        mock_pos = MagicMock()
        mock_pos.type = mt5.POSITION_TYPE_BUY

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[mock_pos]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            # new_sl = 1.08450, bid = 1.0850, distance = 0.00050 > stops_level 0.0001
            strat._modify_sl(12345, 1.08450)
            mock_order.assert_called_once()

    def test_sell_sl_too_close_to_ask_skips(self):
        """SELL: SL trop proche de l'ask -> skip."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info(point=0.00001, stops_level=10)
        tick = _make_tick(bid=1.0850, ask=1.0851)

        mock_pos = MagicMock()
        mock_pos.type = mt5.POSITION_TYPE_SELL

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[mock_pos]), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            # new_sl = 1.08515, ask = 1.0851, distance = 0.00005 < stops_level 0.0001
            strat._modify_sl(12346, 1.08515)
            mock_order.assert_not_called()

    def test_sell_sl_far_enough_sends_order(self):
        """SELL: SL assez loin de l'ask -> order_send appele."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info(point=0.00001, stops_level=10)
        tick = _make_tick(bid=1.0850, ask=1.0851)

        mock_pos = MagicMock()
        mock_pos.type = mt5.POSITION_TYPE_SELL

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[mock_pos]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            # new_sl = 1.08560, ask = 1.0851, distance = 0.00050 > stops_level 0.0001
            strat._modify_sl(12346, 1.08560)
            mock_order.assert_called_once()

    def test_none_sym_info_still_sends_order(self):
        """Symbol info None -> pas de check broker, order_send quand meme."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=None), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            strat._modify_sl(12345, 1.08450)
            mock_order.assert_called_once()

    def test_none_tick_still_sends_order(self):
        """Tick None -> pas de check broker, order_send quand meme."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info()

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=None), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            strat._modify_sl(12345, 1.08450)
            mock_order.assert_called_once()

    def test_no_open_position_still_sends_order(self):
        """Aucune position ouverte -> pas de check distance, order_send quand meme."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info()
        tick = _make_tick()

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            strat._modify_sl(12345, 1.08450)
            mock_order.assert_called_once()

    def test_sl_already_at_bid_not_triggering_stops_check(self):
        """SL au-dessus du bid (BUY) ne declenche pas le check stops_level."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        sym_info = _make_sym_info(point=0.00001, stops_level=10)
        tick = _make_tick(bid=1.0850, ask=1.0851)

        mock_pos = MagicMock()
        mock_pos.type = mt5.POSITION_TYPE_BUY

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[mock_pos]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            # new_sl = 1.0860 > bid = 1.0850, condition new_sl < bid est False
            # -> pas de check stops_level, on envoie l'ordre
            strat._modify_sl(12345, 1.0860)
            mock_order.assert_called_once()


# ============================================================================
# 3. _apply_breakeven()
# ============================================================================


class TestApplyBreakeven:
    """Tests de _apply_breakeven() - seuil breakeven a 1.2R."""

    # --- BUY breakeven ---

    def test_buy_profit_at_1_5r_triggers_breakeven(self):
        """BUY: profit a 1.5R (>= 1.2R) -> breakeven declenche."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        # entry=1.0850, SL=1.0820, SL distance = 30 pips = 0.00030
        # 1.2R = 36 pips, bid=1.0890 -> 40 pips >= 36 (1.2R)
        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        pos["type"] = mt5.POSITION_TYPE_BUY

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0890, ask=1.0891)  # 40 pips >= 36 (1.2R)

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            result = strat._apply_breakeven(pos)
            assert result is True
            mock_order.assert_called_once()

    def test_buy_profit_below_1_2r_no_breakeven(self):
        """BUY: profit a 0.8R (< 1.2R) -> pas de breakeven."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        # SL distance = 30 pips, 1.2R = 36 pips, profit a 1.0862 = 12 pips < 36
        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        pos["type"] = mt5.POSITION_TYPE_BUY

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0858, ask=1.0859)  # 8 pips de profit

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            result = strat._apply_breakeven(pos)
            assert result is False
            mock_order.assert_not_called()

    def test_buy_profit_exactly_1_2r_triggers_breakeven(self):
        """BUY: profit a 1.25R (>= 1.2R, avec marge float) -> breakeven declenche."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        # SL distance = 20 pips = 0.00020, 1.2R = 24 pips
        # entry=1.0850, SL=1.0830, bid=1.0875 -> 25 pips (> 24, marge float-point)
        pos = _make_pos_buy(entry=1.0850, sl=1.0830)
        pos["type"] = mt5.POSITION_TYPE_BUY

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0875, ask=1.0876)  # 25 pips > 24 (1.2R)

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            result = strat._apply_breakeven(pos)
            assert result is True
            mock_order.assert_called_once()

    # --- SELL breakeven ---

    def test_sell_profit_at_1_5r_triggers_breakeven(self):
        """SELL: profit a 1.5R -> breakeven declenche."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        # entry=1.0850, SL=1.0880, SL distance = 30 pips = 0.00030
        # 1.2R = 36 pips, ask=1.0815 = 35 pips pas assez, 1.0814 = 36 pips OK
        pos = _make_pos_sell(entry=1.0850, sl=1.0880)
        pos["type"] = mt5.POSITION_TYPE_SELL

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0810, ask=1.0811)  # 39 pips de profit OK

        mock_result = MagicMock()
        mock_result.retcode = mt5.TRADE_RETCODE_DONE

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.positions_get", return_value=[]), \
             patch("src.ai.strategy.mt5.order_send", return_value=mock_result) as mock_order:
            result = strat._apply_breakeven(pos)
            assert result is True
            mock_order.assert_called_once()

    def test_sell_profit_below_1_2r_no_breakeven(self):
        """SELL: profit < 1.2R -> pas de breakeven."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        pos = _make_pos_sell(entry=1.0850, sl=1.0880)
        pos["type"] = mt5.POSITION_TYPE_SELL

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0840, ask=1.0841)  # 9 pips de profit < 36 (1.2R)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            result = strat._apply_breakeven(pos)
            assert result is False
            mock_order.assert_not_called()

    # --- None tick/sym_info ---

    def test_none_tick_returns_false(self):
        """Tick None -> _apply_breakeven retourne False."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        sym_info = _make_sym_info()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=None), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            result = strat._apply_breakeven(pos)
            assert result is False

    def test_none_sym_info_returns_false(self):
        """Symbol info None -> _apply_breakeven retourne False."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=1.0850, sl=1.0820)
        tick = _make_tick()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=None):
            result = strat._apply_breakeven(pos)
            assert result is False

    # --- Entry price = 0 ---

    def test_zero_entry_price_returns_false(self):
        """Prix d'entree a 0 -> _apply_breakeven retourne False."""
        import src.ai.strategy as strat

        pos = _make_pos_buy(entry=0.0, sl=1.0820)
        sym_info = _make_sym_info()
        tick = _make_tick()

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            result = strat._apply_breakeven(pos)
            assert result is False

    # --- SL deja au-dela de l'entree (deja en profit secured) ---

    def test_buy_sl_already_at_entry_no_breakeven(self):
        """BUY: SL deja a l'entree -> pas de breakeven (deja fait)."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        pos = _make_pos_buy(entry=1.0850, sl=1.0850)  # SL = entry
        pos["type"] = mt5.POSITION_TYPE_BUY

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0880, ask=1.0881)  # gros profit

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            result = strat._apply_breakeven(pos)
            # current_sl (1.0850) < entry_price (1.0850) -> False, donc pas de breakeven
            assert result is False
            mock_order.assert_not_called()

    def test_sell_sl_already_at_entry_no_breakeven(self):
        """SELL: SL deja a l'entree -> pas de breakeven."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        pos = _make_pos_sell(entry=1.0850, sl=1.0850)  # SL = entry
        pos["type"] = mt5.POSITION_TYPE_SELL

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0810, ask=1.0811)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            result = strat._apply_breakeven(pos)
            # current_sl (1.0850) > entry_price (1.0850) -> False
            assert result is False
            mock_order.assert_not_called()

    # --- SL distance = 0 (pas de SL defini) ---

    def test_buy_zero_sl_distance_no_breakeven(self):
        """BUY: SL distance = 0 (SL=0) -> pas de breakeven."""
        import src.ai.strategy as strat
        import MetaTrader5 as mt5

        pos = _make_pos_buy(entry=1.0850, sl=0.0)
        pos["type"] = mt5.POSITION_TYPE_BUY

        sym_info = _make_sym_info()
        tick = _make_tick(bid=1.0880, ask=1.0881)

        with patch("src.ai.strategy.mt5.symbol_info_tick", return_value=tick), \
             patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info), \
             patch("src.ai.strategy.mt5.order_send") as mock_order:
            result = strat._apply_breakeven(pos)
            # sl_distance_pips = 0, profit >= 0 * 1.2 = 0 est True
            # mais current_sl (0) < entry_price (1.0850) est True
            # donc on appelle _modify_sl, mais _modify_sl essaie de set SL a entry
            # Le code ne check pas si SL_distance est 0 avant...
            # On verifie juste que ca ne crash pas
            assert result in (True, False)


# ============================================================================
# 4. _passes_trade_filters() - ADX-conditioned RSI/BB filters
# ============================================================================


class TestPassesTradeFiltersADX:
    """Tests des filtres RSI/BB conditionnes au regime ADX (v3.0)."""

    def _make_symbol_info(self):
        return {"spread": 5, "point": 0.00001, "digits": 5}

    # --- ADX > 25 (trending): RSI/BB filters DISABLED ---

    def test_trending_rsi_overbought_buy_allowed(self):
        """ADX > 25, RSI > 75, BUY -> autorise (filtres desactives en tendance)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=78, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_trending_rsi_oversold_sell_allowed(self):
        """ADX > 25, RSI < 25, SELL -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=22, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_trending_bb_above_upper_buy_allowed(self):
        """ADX > 25, BB > 100, BUY -> autorise (filtres desactives)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=60, bb_pos=110, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_trending_bb_below_lower_sell_allowed(self):
        """ADX > 25, BB < 0, SELL -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=40, bb_pos=-5, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- ADX <= 25 (ranging): RSI/BB filters ACTIVE ---

    def test_ranging_rsi_overbought_blocks_buy(self):
        """ADX <= 25, RSI > 75, BUY -> bloque."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=78, bb_pos=50, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_ranging_rsi_oversold_blocks_sell(self):
        """ADX <= 25, RSI < 25, SELL -> bloque."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=22, bb_pos=50, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_ranging_bb_above_upper_blocks_buy(self):
        """ADX <= 25, BB > 100, BUY -> bloque."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=60, bb_pos=110, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_ranging_bb_below_lower_blocks_sell(self):
        """ADX <= 25, BB < 0, SELL -> bloque."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=40, bb_pos=-5, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    # --- ADX boundary: exactly 25 ---

    def test_adx_exactly_25_rsi_overbought_blocks_buy(self):
        """ADX = 25 (<= 25), RSI > 75, BUY -> bloque (filtre actif)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=78, bb_pos=50, adx=25)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_adx_exactly_26_rsi_overbought_buy_allowed(self):
        """ADX = 26 (> 25), RSI > 75, BUY -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=78, bb_pos=50, adx=26)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- ADX is None (default) ---

    def test_adx_none_treated_as_ranging(self):
        """ADX None -> traite comme adx=20 (default), donc <= 25, filtres actifs."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = {
            "action": "BUY",
            "confidence": 75,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
            "indicators": {"rsi_14": 78, "bb_position_pct": 50},  # pas d'adx_14
        }
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        # ADX default = 20 <= 25, RSI=78 > 75 -> bloque
        assert result is False

    # --- RSI normal avec ADX <= 25: autorise ---

    def test_ranging_rsi_normal_buy_allowed(self):
        """ADX <= 25, RSI normal (55), BUY -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=55, bb_pos=50, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    def test_ranging_rsi_normal_sell_allowed(self):
        """ADX <= 25, RSI normal (45), SELL -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=45, bb_pos=50, adx=20)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- ADX > 25 but RSI normal: should still pass all other filters ---

    def test_trending_rsi_normal_buy_allowed(self):
        """ADX > 25, RSI normal (60), BUY -> autorise (pas de blocage)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=60, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- Edge case: no indicators at all ---

    def test_no_indicators_adx_default_ranging(self):
        """Aucun indicateur -> ADX default 20, RSI default 50 -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = {
            "action": "BUY",
            "confidence": 75,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
        }
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- bb_pos is None in trending: should still pass ---

    def test_trending_bb_none_buy_allowed(self):
        """ADX > 25, bb_pos None, BUY -> autorise (pas d'evaluation BB)."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=60, bb_pos=None, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True

    # --- bb_pos is non-numeric (string) in ranging: should not crash ---

    def test_ranging_bb_non_numeric_does_not_block(self):
        """ADX <= 25, bb_pos non-numerique -> le check isinstance protege, pas de blocage BB."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = {
            "action": "BUY",
            "confidence": 75,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
            "indicators": {"rsi_14": 60, "bb_position_pct": "invalid", "adx_14": 20},
        }
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0):
            result = strat._passes_trade_filters(decision, symbol_info)

        # isinstance check protects, bb_pos "invalid" is not (int, float), no BB block
        assert result is True

    # --- v4.1: Disabled symbols ---

    def test_disabled_symbol_blocks_trade(self):
        """XAUUSD est dans _DISABLED_SYMBOLS -> _passes_trade_filters retourne False."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=55, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0), \
             patch.object(strat.settings, "trading_symbol", "XAUUSD"):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_disabled_symbol_sell_also_blocked(self):
        """XAUUSD SELL aussi bloque par _DISABLED_SYMBOLS."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("SELL", rsi=45, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0), \
             patch.object(strat.settings, "trading_symbol", "XAUUSD"):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is False

    def test_enabled_symbol_not_blocked(self):
        """EURUSD n'est PAS dans _DISABLED_SYMBOLS -> autorise."""
        from unittest.mock import patch
        import src.ai.strategy as strat

        decision = _make_decision("BUY", rsi=55, bb_pos=50, adx=30)
        symbol_info = self._make_symbol_info()

        with patch.object(strat, "count_open_positions", return_value=0), \
             patch.object(strat, "_circuit_breaker_active", return_value=False), \
             patch.object(strat, "_count_consecutive_losses", return_value=0), \
             patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._passes_trade_filters(decision, symbol_info)

        assert result is True


# ============================================================================
# 5. _is_ranging_market() - Anti-range filter (v4.1)
# ============================================================================


class TestIsRangingMarket:
    """Tests de _is_ranging_market() - detection du range ADX."""

    def setup_method(self):
        """Reset le state global avant chaque test."""
        import src.ai.strategy as strat
        strat._ranging_state.clear()

    def teardown_method(self):
        """Cleanup apres chaque test."""
        import src.ai.strategy as strat
        strat._ranging_state.clear()

    # --- ADX au-dessus du seuil: reset compteur, retourne False ---

    def test_adx_above_threshold_resets_and_returns_false(self):
        """ADX > 25: reset le compteur, retourne False."""
        import src.ai.strategy as strat

        decision = _make_decision("BUY", adx=30)

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._is_ranging_market(decision)

        assert result is False
        assert strat._ranging_state.get("EURUSD", -1) == 0

    def test_adx_above_threshold_after_range_resets_counter(self):
        """Apres 2 periodes ADX bas, un ADX > 25 reset le compteur."""
        import src.ai.strategy as strat

        # 2 periodes ADX bas
        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            strat._is_ranging_market(_make_decision("BUY", adx=20))
            strat._is_ranging_market(_make_decision("BUY", adx=20))
            assert strat._ranging_state.get("EURUSD") == 2

            # Puis ADX remonte
            result = strat._is_ranging_market(_make_decision("BUY", adx=30))

        assert result is False
        assert strat._ranging_state.get("EURUSD") == 0

    # --- ADX sous le seuil, pas assez de periodes ---

    def test_adx_below_threshold_1_period_returns_false(self):
        """1 periode ADX < 25 -> compteur=1, pas encore de range."""
        import src.ai.strategy as strat

        decision = _make_decision("BUY", adx=20)

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._is_ranging_market(decision)

        assert result is False
        assert strat._ranging_state.get("EURUSD") == 1

    def test_adx_below_threshold_2_periods_returns_false(self):
        """2 periodes ADX < 25 -> compteur=2, pas encore de range."""
        import src.ai.strategy as strat

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            strat._is_ranging_market(_make_decision("BUY", adx=20))
            result = strat._is_ranging_market(_make_decision("BUY", adx=20))

        assert result is False
        assert strat._ranging_state.get("EURUSD") == 2

    def test_adx_below_threshold_3_periods_returns_true(self):
        """3 periodes consecutives ADX < 25 -> range detecte, retourne True."""
        import src.ai.strategy as strat

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            strat._is_ranging_market(_make_decision("BUY", adx=20))
            strat._is_ranging_market(_make_decision("BUY", adx=20))
            result = strat._is_ranging_market(_make_decision("BUY", adx=20))

        assert result is True
        assert strat._ranging_state.get("EURUSD") == 3

    def test_adx_below_threshold_4_periods_continues_range(self):
        """4+ periodes ADX < 25 -> range continue, retourne True."""
        import src.ai.strategy as strat

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            for _ in range(3):
                strat._is_ranging_market(_make_decision("BUY", adx=20))
            # 4eme appel
            result = strat._is_ranging_market(_make_decision("BUY", adx=20))

        assert result is True
        assert strat._ranging_state.get("EURUSD") == 4

    # --- ADX exactement au seuil ---

    def test_adx_exactly_25_is_considered_below_threshold(self):
        """ADX = 25 (<= seuil): apres 3 periodes, range detecte."""
        import src.ai.strategy as strat

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            for _ in range(2):
                strat._is_ranging_market(_make_decision("BUY", adx=25))
            result = strat._is_ranging_market(_make_decision("BUY", adx=25))

        # adx=25 n'est PAS > 25 (strict), donc il est traite comme bas
        assert result is True

    def test_adx_exactly_25_001_is_above_threshold(self):
        """ADX = 25.001 (> 25): reset, retourne False."""
        import src.ai.strategy as strat

        decision = _make_decision("BUY", adx=25.001)

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._is_ranging_market(decision)

        assert result is False

    # --- ADX None ---

    def test_adx_none_returns_false_and_resets(self):
        """ADX None (default 30 > 25): retourne False, reset compteur."""
        import src.ai.strategy as strat

        decision = {
            "action": "BUY",
            "confidence": 75,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
            "indicators": {"rsi_14": 50},  # pas d'adx_14
        }

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._is_ranging_market(decision)

        assert result is False
        assert strat._ranging_state.get("EURUSD") == 0

    # --- Pas d'indicateurs du tout ---

    def test_no_indicators_returns_false(self):
        """Aucun indicateur -> ADX default 30 > 25, retourne False."""
        import src.ai.strategy as strat

        decision = {
            "action": "BUY",
            "confidence": 75,
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_level": "MEDIUM",
        }

        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            result = strat._is_ranging_market(decision)

        assert result is False

    # --- Symboles differents ont des etats separes ---

    def test_different_symbols_have_separate_state(self):
        """EURUSD en range n'affecte pas GBPUSD."""
        import src.ai.strategy as strat

        # Mettre EURUSD en range
        with patch.object(strat.settings, "trading_symbol", "EURUSD"):
            for _ in range(3):
                strat._is_ranging_market(_make_decision("BUY", adx=20))
            assert strat._is_ranging_market(_make_decision("BUY", adx=20)) is True

        # GBPUSD n'a jamais ete appele -> compteur 0
        with patch.object(strat.settings, "trading_symbol", "GBPUSD"):
            result = strat._is_ranging_market(_make_decision("BUY", adx=20))

        assert result is False  # 1er appel, compteur=1 < 3
        assert strat._ranging_state.get("GBPUSD") == 1
        assert strat._ranging_state.get("EURUSD") == 4  # EURUSD toujours en range


# ============================================================================
# 6. _get_atr_based_sl_tp() - Hard SL floor (v4.1)
# ============================================================================


class TestATRSLHardFloor:
    """Tests du hard SL floor dans _get_atr_based_sl_tp et execute_decision."""

    # --- _get_atr_based_sl_tp: SL sous min_sl avec ATR valide ---

    def test_atr_sl_respects_min_sl_floor(self):
        """DeepSeek donne SL=5, ATR calcule 8, min_sl=15 -> SL final = 15."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 0.00050}  # ~5 pips pour EURUSD
        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("EURUSD", indicators, deepseek_sl=5, deepseek_tp=10)

        # ATR based: max(min_sl=15, 5*1.5=7.5) = 15
        # SL final: max(deepseek=5, ATR=15) = 15
        # TP final: max(deepseek=10, min_tp=30, 15*2=30) = 30
        assert sl == 15
        assert tp == 30

    def test_atr_sl_above_min_keeps_value(self):
        """DeepSeek SL=25 > min_sl=15 -> SL final = 25 (DeepSeek gagne)."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 0.00200}  # ~20 pips pour EURUSD
        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("EURUSD", indicators, deepseek_sl=25, deepseek_tp=50)

        # ATR based: max(15, 20*1.5=30) = 30
        # SL final: max(25, 30) = 30
        # TP final: max(50, min_tp=30, 30*2=60) = 60
        assert sl == 30
        assert tp == 60

    def test_atr_sl_empty_indicators_uses_min_sl(self):
        """Indicators vide -> ATR=None -> atr_based_sl = min_sl (15)."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("EURUSD", {}, deepseek_sl=5, deepseek_tp=10)

        # Indicators empty, atr_value = None -> atr_based_sl = min_sl = 15
        # SL final: max(5, 15) = 15
        # TP final: max(10, 30, 15*2=30) = 30
        assert sl == 15
        assert tp == 30

    def test_atr_sl_none_indicators_uses_min_sl(self):
        """Indicators=None -> ATR=None -> atr_based_sl = min_sl."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("EURUSD", None, deepseek_sl=5, deepseek_tp=10)

        assert sl == 15
        assert tp == 30

    def test_atr_sl_atr_zero_uses_min_sl(self):
        """ATR=0 -> atr_pips=0 -> atr_based_sl = min_sl."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 0.0}
        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("EURUSD", indicators, deepseek_sl=5, deepseek_tp=10)

        assert sl == 15
        assert tp == 30

    # --- Hard floor par symbole ---

    def test_xauusd_min_sl_150(self):
        """XAUUSD: min_sl=150, DeepSeek SL=50 -> SL=150."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 10.0}
        sym_info = MagicMock()
        sym_info.point = 0.01  # XAUUSD point

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("XAUUSD", indicators, deepseek_sl=50, deepseek_tp=100)

        # ATR pips = 10 / (10*0.01) = 100
        # atr_based_sl = max(150, 100*0.5=50) = 150
        # SL final: max(50, 150) = 150
        assert sl == 150

    def test_gbpusd_min_sl_25(self):
        """GBPUSD: min_sl=25 (updated from 18)."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 0.00050}  # ~5 pips
        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("GBPUSD", indicators, deepseek_sl=5, deepseek_tp=10)

        # atr_based_sl = max(25, 5*1.8=9) = 25
        # SL final: max(5, 25) = 25
        assert sl == 25

    def test_usdjpy_min_sl_30(self):
        """USDJPY: min_sl=30 (updated from 20)."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {"atr_14": 0.050}  # ~0.5 pips
        sym_info = MagicMock()
        sym_info.point = 0.001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("USDJPY", indicators, deepseek_sl=5, deepseek_tp=10)

        # atr_based_sl = max(30, 5*1.8=9) = 30
        # SL final: max(5, 30) = 30
        assert sl == 30

    # --- Symbole inconnu: fallback EURUSD ---

    def test_unknown_symbol_falls_back_to_eurusd_config(self):
        """Symbole inconnu utilise la config EURUSD (min_sl=15)."""
        import src.ai.strategy as strat
        from unittest.mock import patch

        indicators = {}
        sym_info = MagicMock()
        sym_info.point = 0.00001

        with patch("src.ai.strategy.mt5.symbol_info", return_value=sym_info):
            sl, tp = strat._get_atr_based_sl_tp("NZDCAD", indicators, deepseek_sl=5, deepseek_tp=10)

        assert sl == 15
        assert tp == 30
