"""Unit tests for the prompts module (prompts.py).

Covers v3.0 changes:
5. _format_indicators_v2() - conversion of raw values to semantic states
   for LLMs (RSI zones, MACD crossover/zone, Bollinger semantic, ATR volatility)
"""

import pytest
from src.ai.prompts import _format_indicators_v2


# ============================================================================
# RSI: semantic zones
# ============================================================================


class TestFormatIndicatorsV2RSI:
    """Tests of semantic formatting of RSI."""

    def test_rsi_surachat_above_75(self):
        """RSI > 75 -> OVERBOUGHT zone."""
        result = _format_indicators_v2({"rsi_14": 78.5})
        assert "OVERBOUGHT" in result
        assert "78.5" in result

    def test_rsi_haussier_above_60(self):
        """RSI between 60 and 75 -> Bullish trend."""
        result = _format_indicators_v2({"rsi_14": 65.0})
        assert "Bullish trend" in result
        assert "OVERBOUGHT" not in result

    def test_rsi_neutre_above_40(self):
        """RSI between 40 and 60 -> Neutral zone."""
        result = _format_indicators_v2({"rsi_14": 50.0})
        assert "Neutral zone" in result

    def test_rsi_baissier_above_25(self):
        """RSI between 25 and 40 -> Bearish trend."""
        result = _format_indicators_v2({"rsi_14": 30.0})
        assert "Bearish trend" in result

    def test_rsi_survente_below_25(self):
        """RSI < 25 -> OVERSOLD zone."""
        result = _format_indicators_v2({"rsi_14": 18.0})
        assert "OVERSOLD" in result
        assert "18.0" in result

    def test_rsi_none_not_included(self):
        """RSI None -> no RSI line in the result."""
        result = _format_indicators_v2({})
        assert "RSI" not in result

    # --- Boundary values ---

    def test_rsi_boundary_75_is_surachat(self):
        """RSI = 75.0: 75 > 75 = False -> Bullish trend."""
        result = _format_indicators_v2({"rsi_14": 75.0})
        assert "Bullish trend" in result
        assert "OVERBOUGHT" not in result

    def test_rsi_boundary_60_is_neutre(self):
        """RSI = 60.0: 60 > 75? No. 60 > 60? No. 60 > 40? Yes -> Neutral zone."""
        result = _format_indicators_v2({"rsi_14": 60.0})
        assert "Neutral zone" in result

    def test_rsi_boundary_40_is_baissier(self):
        """RSI = 40.0: 40 > 75? No. 40 > 60? No. 40 > 40? No. 40 > 25? Yes -> Bearish trend."""
        result = _format_indicators_v2({"rsi_14": 40.0})
        assert "Bearish trend" in result

    def test_rsi_boundary_25_is_survente(self):
        """RSI = 25.0: 25 > 25 = False -> OVERSOLD."""
        result = _format_indicators_v2({"rsi_14": 25.0})
        assert "OVERSOLD" in result


# ============================================================================
# MACD: crossover and zone
# ============================================================================


class TestFormatIndicatorsV2MACD:
    """Tests of semantic formatting of MACD."""

    def test_macd_above_signal_positive_zone(self):
        """MACD > Signal in positive zone -> bullish momentum."""
        result = _format_indicators_v2({
            "macd_line": 0.002,
            "macd_signal": 0.001,
            "macd_histogram": 0.001,
        })
        assert "MACD above Signal" in result
        assert "positive zone" in result
        assert "bullish histogram" in result

    def test_macd_below_signal_negative_zone(self):
        """MACD < Signal in negative zone -> bearish momentum."""
        result = _format_indicators_v2({
            "macd_line": -0.002,
            "macd_signal": -0.001,
            "macd_histogram": -0.001,
        })
        assert "MACD below Signal" in result
        assert "negative zone" in result
        assert "bearish histogram" in result

    def test_macd_above_signal_negative_zone(self):
        """MACD > Signal but in negative zone."""
        result = _format_indicators_v2({
            "macd_line": -0.001,
            "macd_signal": -0.002,
            "macd_histogram": 0.001,
        })
        assert "MACD above Signal" in result
        assert "negative zone" in result
        assert "bullish histogram" in result

    def test_macd_equal_to_signal(self):
        """MACD == Signal -> MACD below Signal (since <=)."""
        result = _format_indicators_v2({
            "macd_line": 0.001,
            "macd_signal": 0.001,
            "macd_histogram": 0.0,
        })
        assert "MACD below Signal" in result

    def test_macd_histogram_none_still_formats(self):
        """MACD without histogram -> formats without histogram part."""
        result = _format_indicators_v2({
            "macd_line": 0.002,
            "macd_signal": 0.001,
        })
        assert "MACD above Signal" in result
        assert "positive zone" in result

    def test_macd_line_none_not_included(self):
        """MACD line None -> no MACD line."""
        result = _format_indicators_v2({"macd_signal": 0.001})
        assert "MACD" not in result

    def test_macd_signal_none_not_included(self):
        """MACD signal None -> no MACD line."""
        result = _format_indicators_v2({"macd_line": 0.001})
        assert "MACD" not in result


# ============================================================================
# Bollinger Bands: semantic position
# ============================================================================


class TestFormatIndicatorsV2Bollinger:
    """Tests of semantic formatting of Bollinger Bands."""

    def test_bb_sur_bande_superieure(self):
        """BB > 95 -> Price ON UPPER BAND."""
        result = _format_indicators_v2({"bb_position_pct": 97.0})
        assert "Price ON UPPER BAND" in result

    def test_bb_moitie_superieure(self):
        """BB between 70 and 95 -> UPPER HALF."""
        result = _format_indicators_v2({"bb_position_pct": 80.0})
        assert "UPPER HALF" in result

    def test_bb_zone_mediane(self):
        """BB between 30 and 70 -> MIDDLE ZONE."""
        result = _format_indicators_v2({"bb_position_pct": 50.0})
        assert "MIDDLE ZONE" in result

    def test_bb_moitie_inferieure(self):
        """BB between 5 and 30 -> LOWER HALF."""
        result = _format_indicators_v2({"bb_position_pct": 15.0})
        assert "LOWER HALF" in result

    def test_bb_sur_bande_inferieure(self):
        """BB < 5 -> Price ON LOWER BAND."""
        result = _format_indicators_v2({"bb_position_pct": 2.0})
        assert "Price ON LOWER BAND" in result

    def test_bb_none_not_included(self):
        """BB None -> no Bollinger line."""
        result = _format_indicators_v2({})
        assert "Bollinger" not in result

    # --- Boundary values ---

    def test_bb_boundary_95_is_moitie_superieure(self):
        """BB = 95: 95 > 95? No. 95 > 70? Yes -> UPPER HALF."""
        result = _format_indicators_v2({"bb_position_pct": 95.0})
        assert "UPPER HALF" in result

    def test_bb_boundary_70_is_zone_mediane(self):
        """BB = 70: 70 > 95? No. 70 > 70? No. 70 > 30? Yes -> MIDDLE ZONE."""
        result = _format_indicators_v2({"bb_position_pct": 70.0})
        assert "MIDDLE ZONE" in result

    def test_bb_boundary_30_is_moitie_inferieure(self):
        """BB = 30: 30 > 30? No. 30 > 5? Yes -> LOWER HALF."""
        result = _format_indicators_v2({"bb_position_pct": 30.0})
        assert "LOWER HALF" in result

    def test_bb_boundary_5_is_sur_bande_inferieure(self):
        """BB = 5: 5 > 5? No -> Price ON LOWER BAND."""
        result = _format_indicators_v2({"bb_position_pct": 5.0})
        assert "Price ON LOWER BAND" in result


# ============================================================================
# Moving Averages
# ============================================================================


class TestFormatIndicatorsV2MA:
    """Tests of moving averages formatting."""

    def test_ema20_price_above(self):
        """Price above EMA20."""
        result = _format_indicators_v2({
            "ema_20": 1.0830,
            "current_price": 1.0850,
        })
        assert "above" in result
        assert "EMA20" in result

    def test_ema20_price_below(self):
        """Price below EMA20."""
        result = _format_indicators_v2({
            "ema_20": 1.0870,
            "current_price": 1.0850,
        })
        assert "below" in result
        assert "EMA20" in result

    def test_ema20_none_not_included(self):
        """EMA20 None -> no EMA20 line."""
        result = _format_indicators_v2({"current_price": 1.0850})
        assert "EMA20" not in result

    def test_ema200_price_above(self):
        """Price above EMA200."""
        result = _format_indicators_v2({
            "ema_200": 1.0800,
            "current_price": 1.0850,
        })
        assert "above" in result
        assert "EMA200" in result

    def test_ema200_none_not_included(self):
        """EMA200 None -> no EMA200 line."""
        result = _format_indicators_v2({"current_price": 1.0850})
        assert "EMA200" not in result


# ============================================================================
# ATR: volatility
# ============================================================================


class TestFormatIndicatorsV2ATR:
    """Tests of ATR semantic formatting."""

    def test_atr_volatilite_elevee(self):
        """ATR > 0.5% of price -> HIGH VOLATILITY."""
        result = _format_indicators_v2({
            "atr_14": 0.0080,
            "current_price": 1.0850,
        })
        assert "HIGH VOLATILITY" in result

    def test_atr_volatilite_moderee(self):
        """ATR between 0.2% and 0.5% of price -> Moderate volatility."""
        result = _format_indicators_v2({
            "atr_14": 0.0040,
            "current_price": 1.0850,
        })
        assert "Moderate volatility" in result

    def test_atr_volatilite_faible(self):
        """ATR < 0.2% of price -> Low volatility."""
        result = _format_indicators_v2({
            "atr_14": 0.0010,
            "current_price": 1.0850,
        })
        assert "Low volatility" in result

    def test_atr_none_not_included(self):
        """ATR None -> no ATR line."""
        result = _format_indicators_v2({})
        assert "ATR" not in result

    def test_atr_no_current_price_not_included(self):
        """ATR without current_price -> no ATR line."""
        result = _format_indicators_v2({"atr_14": 0.0040})
        assert "ATR" not in result

    # --- Boundary values ---

    def test_atr_boundary_0_5_pct_is_elevee(self):
        """ATR = 0.5% exactly -> Moderate volatility."""
        result = _format_indicators_v2({
            "atr_14": 0.005425,
            "current_price": 1.0850,
        })
        assert "Moderate volatility" in result

    def test_atr_boundary_0_2_pct_is_faible(self):
        """ATR = 0.2% exactly -> Low volatility."""
        result = _format_indicators_v2({
            "atr_14": 0.00217,
            "current_price": 1.0850,
        })
        assert "Low volatility" in result


# ============================================================================
# Combination: all indicators together
# ============================================================================


class TestFormatIndicatorsV2Full:
    """Tests with a complete set of indicators."""

    def test_full_indicators_output(self):
        """All indicators present -> all sections."""
        ind = {
            "rsi_14": 55.0,
            "macd_line": 0.002,
            "macd_signal": 0.001,
            "macd_histogram": 0.001,
            "bb_position_pct": 65.0,
            "current_price": 1.0850,
            "ema_20": 1.0840,
            "ema_200": 1.0750,
            "atr_14": 0.0030,
            "trend_short": "haussier",
            "trend_medium": "haussier",
            "high_24h": 1.0900,
            "low_24h": 1.0780,
        }
        result = _format_indicators_v2(ind)

        assert "RSI 14" in result
        assert "MACD" in result
        assert "Bollinger" in result
        assert "EMA20" in result
        assert "EMA200" in result
        assert "ATR 14" in result
        assert "ST Trend" in result
        assert "24h Range" in result

    def test_minimal_indicators_does_not_crash(self):
        """Empty indicators -> no crash."""
        result = _format_indicators_v2({})
        assert isinstance(result, str)
        assert "ST Trend" in result

    def test_empty_string_does_not_break(self):
        """Always returns a string."""
        result = _format_indicators_v2({})
        assert isinstance(result, str)
        assert len(result) >= 0

    def test_rsi_zero_treated_as_survente(self):
        """RSI = 0 -> OVERSOLD."""
        result = _format_indicators_v2({"rsi_14": 0.0})
        assert "OVERSOLD" in result

    def test_rsi_100_treated_as_surachat(self):
        """RSI = 100 -> OVERBOUGHT."""
        result = _format_indicators_v2({"rsi_14": 100.0})
        assert "OVERBOUGHT" in result

    def test_current_price_none_no_ema_formatting(self):
        """current_price None -> EMA20/EMA200 not formatted."""
        result = _format_indicators_v2({
            "ema_20": 1.0830,
            "ema_200": 1.0800,
        })
        assert "EMA20" not in result
        assert "EMA200" not in result

    def test_bb_zero_is_sur_bande_inferieure(self):
        """BB = 0 -> Price ON LOWER BAND."""
        result = _format_indicators_v2({"bb_position_pct": 0.0})
        assert "Price ON LOWER BAND" in result

    def test_bb_100_is_sur_bande_superieure(self):
        """BB = 100 -> Price ON UPPER BAND."""
        result = _format_indicators_v2({"bb_position_pct": 100.0})
        assert "Price ON UPPER BAND" in result

    def test_macd_zero_line_zero_signal(self):
        """MACD line = 0, signal = 0."""
        result = _format_indicators_v2({
            "macd_line": 0.0,
            "macd_signal": 0.0,
            "macd_histogram": 0.0,
        })
        assert "MACD below Signal" in result
        assert "negative zone" in result
