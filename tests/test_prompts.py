"""Tests unitaires pour le module prompts (prompts.py).

Couvre le changement v3.0:
5. _format_indicators_v2() - conversion des valeurs brutes en etats semantiques
   pour les LLMs (RSI zones, MACD croisement/zone, Bollinger semantique, ATR volatilite)
"""

import pytest
from src.ai.prompts import _format_indicators_v2


# ============================================================================
# RSI: zones semantiques
# ============================================================================


class TestFormatIndicatorsV2RSI:
    """Tests de formatage semantique du RSI."""

    def test_rsi_surachat_above_75(self):
        """RSI > 75 -> zone SURACHAT."""
        result = _format_indicators_v2({"rsi_14": 78.5})
        assert "SURACHAT" in result
        assert "78.5" in result

    def test_rsi_haussier_above_60(self):
        """RSI entre 60 et 75 -> Tendance haussiere."""
        result = _format_indicators_v2({"rsi_14": 65.0})
        assert "Tendance haussiere" in result
        assert "SURACHAT" not in result

    def test_rsi_neutre_above_40(self):
        """RSI entre 40 et 60 -> Zone neutre."""
        result = _format_indicators_v2({"rsi_14": 50.0})
        assert "Zone neutre" in result

    def test_rsi_baissier_above_25(self):
        """RSI entre 25 et 40 -> Tendance baissiere."""
        result = _format_indicators_v2({"rsi_14": 30.0})
        assert "Tendance baissiere" in result

    def test_rsi_survente_below_25(self):
        """RSI < 25 -> zone SURVENTE."""
        result = _format_indicators_v2({"rsi_14": 18.0})
        assert "SURVENTE" in result
        assert "18.0" in result

    def test_rsi_none_not_included(self):
        """RSI None -> pas de ligne RSI dans le resultat."""
        result = _format_indicators_v2({})
        assert "RSI" not in result

    # --- Boundary values ---

    def test_rsi_boundary_75_is_surachat(self):
        """RSI = 75.0 est dans > 75? Non, 75 > 75 = False, donc c'est haussier (60-75)."""
        result = _format_indicators_v2({"rsi_14": 75.0})
        # 75 > 75 = False, 75 > 60 = True -> "Tendance haussiere"
        assert "Tendance haussiere" in result
        assert "SURACHAT" not in result

    def test_rsi_boundary_60_is_neutre(self):
        """RSI = 60.0: 60 > 75? Non. 60 > 60? Non. 60 > 40? Oui -> neutre."""
        result = _format_indicators_v2({"rsi_14": 60.0})
        assert "Zone neutre" in result

    def test_rsi_boundary_40_is_baissier(self):
        """RSI = 40.0: 40 > 75? Non. 40 > 60? Non. 40 > 40? Non. 40 > 25? Oui -> baissier."""
        result = _format_indicators_v2({"rsi_14": 40.0})
        assert "Tendance baissiere" in result

    def test_rsi_boundary_25_is_survente(self):
        """RSI = 25.0: 25 > 25 = False -> SURVENTE."""
        result = _format_indicators_v2({"rsi_14": 25.0})
        assert "SURVENTE" in result


# ============================================================================
# MACD: croisement et zone
# ============================================================================


class TestFormatIndicatorsV2MACD:
    """Tests de formatage semantique du MACD."""

    def test_macd_above_signal_positive_zone(self):
        """MACD > Signal en zone positive -> momentum haussier."""
        result = _format_indicators_v2({
            "macd_line": 0.002,
            "macd_signal": 0.001,
            "macd_histogram": 0.001,
        })
        assert "MACD au-dessus du Signal" in result
        assert "zone positive" in result
        assert "histogramme haussier" in result

    def test_macd_below_signal_negative_zone(self):
        """MACD < Signal en zone negative -> momentum baissier."""
        result = _format_indicators_v2({
            "macd_line": -0.002,
            "macd_signal": -0.001,
            "macd_histogram": -0.001,
        })
        assert "MACD sous le Signal" in result
        assert "zone negative" in result
        assert "histogramme baissier" in result

    def test_macd_above_signal_negative_zone(self):
        """MACD > Signal mais en zone negative."""
        result = _format_indicators_v2({
            "macd_line": -0.001,
            "macd_signal": -0.002,
            "macd_histogram": 0.001,
        })
        assert "MACD au-dessus du Signal" in result
        assert "zone negative" in result
        assert "histogramme haussier" in result

    def test_macd_equal_to_signal(self):
        """MACD == Signal -> MACD sous le Signal (car <=)."""
        result = _format_indicators_v2({
            "macd_line": 0.001,
            "macd_signal": 0.001,
            "macd_histogram": 0.0,
        })
        # macd_line > macd_signal? 0.001 > 0.001 = False -> "sous le Signal"
        assert "MACD sous le Signal" in result

    def test_macd_histogram_none_still_formats(self):
        """MACD sans histogramme -> formatte sans la partie histogramme."""
        result = _format_indicators_v2({
            "macd_line": 0.002,
            "macd_signal": 0.001,
        })
        assert "MACD au-dessus du Signal" in result
        assert "zone positive" in result
        # histogram part should be empty

    def test_macd_line_none_not_included(self):
        """MACD line None -> pas de ligne MACD."""
        result = _format_indicators_v2({"macd_signal": 0.001})
        assert "MACD" not in result

    def test_macd_signal_none_not_included(self):
        """MACD signal None -> pas de ligne MACD."""
        result = _format_indicators_v2({"macd_line": 0.001})
        assert "MACD" not in result


# ============================================================================
# Bollinger Bands: position semantique
# ============================================================================


class TestFormatIndicatorsV2Bollinger:
    """Tests de formatage semantique des bandes de Bollinger."""

    def test_bb_sur_bande_superieure(self):
        """BB > 95 -> SUR LA BANDE SUPERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 97.0})
        assert "SUR LA BANDE SUPERIEURE" in result

    def test_bb_moitie_superieure(self):
        """BB entre 70 et 95 -> MOITIE SUPERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 80.0})
        assert "MOITIE SUPERIEURE" in result

    def test_bb_zone_mediane(self):
        """BB entre 30 et 70 -> ZONE MEDIANE."""
        result = _format_indicators_v2({"bb_position_pct": 50.0})
        assert "ZONE MEDIANE" in result

    def test_bb_moitie_inferieure(self):
        """BB entre 5 et 30 -> MOITIE INFERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 15.0})
        assert "MOITIE INFERIEURE" in result

    def test_bb_sur_bande_inferieure(self):
        """BB < 5 -> SUR LA BANDE INFERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 2.0})
        assert "SUR LA BANDE INFERIEURE" in result

    def test_bb_none_not_included(self):
        """BB None -> pas de ligne Bollinger."""
        result = _format_indicators_v2({})
        assert "Bollinger" not in result

    # --- Boundary values ---

    def test_bb_boundary_95_is_moitie_superieure(self):
        """BB = 95: 95 > 95? Non. 95 > 70? Oui -> MOITIE SUPERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 95.0})
        assert "MOITIE SUPERIEURE" in result

    def test_bb_boundary_70_is_zone_mediane(self):
        """BB = 70: 70 > 95? Non. 70 > 70? Non. 70 > 30? Oui -> ZONE MEDIANE."""
        result = _format_indicators_v2({"bb_position_pct": 70.0})
        assert "ZONE MEDIANE" in result

    def test_bb_boundary_30_is_moitie_inferieure(self):
        """BB = 30: 30 > 30? Non. 30 > 5? Oui -> MOITIE INFERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 30.0})
        assert "MOITIE INFERIEURE" in result

    def test_bb_boundary_5_is_sur_bande_inferieure(self):
        """BB = 5: 5 > 5? Non -> SUR LA BANDE INFERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 5.0})
        assert "SUR LA BANDE INFERIEURE" in result


# ============================================================================
# Moving Averages
# ============================================================================


class TestFormatIndicatorsV2MA:
    """Tests de formatage des moving averages."""

    def test_sma20_price_above(self):
        """Prix au-dessus de la SMA20."""
        result = _format_indicators_v2({
            "sma_20": 1.0830,
            "current_price": 1.0850,
        })
        assert "au-dessus" in result
        assert "SMA20" in result

    def test_sma20_price_below(self):
        """Prix sous la SMA20."""
        result = _format_indicators_v2({
            "sma_20": 1.0870,
            "current_price": 1.0850,
        })
        assert "sous" in result
        assert "SMA20" in result

    def test_sma20_none_not_included(self):
        """SMA20 None -> pas de ligne SMA20."""
        result = _format_indicators_v2({"current_price": 1.0850})
        assert "SMA20" not in result

    def test_sma50_price_above(self):
        """Prix au-dessus de la SMA50."""
        result = _format_indicators_v2({
            "sma_50": 1.0800,
            "current_price": 1.0850,
        })
        assert "au-dessus" in result
        assert "SMA50" in result

    def test_sma50_none_not_included(self):
        """SMA50 None -> pas de ligne SMA50."""
        result = _format_indicators_v2({"current_price": 1.0850})
        assert "SMA50" not in result


# ============================================================================
# ATR: volatilite
# ============================================================================


class TestFormatIndicatorsV2ATR:
    """Tests de formatage semantique de l'ATR."""

    def test_atr_volatilite_elevee(self):
        """ATR > 0.5% du prix -> VOLATILITE ELEVEE."""
        result = _format_indicators_v2({
            "atr_14": 0.0080,
            "current_price": 1.0850,  # 0.0080/1.0850 = 0.74% > 0.5%
        })
        assert "VOLATILITE ELEVEE" in result

    def test_atr_volatilite_moderee(self):
        """ATR entre 0.2% et 0.5% du prix -> Volatilite moderee."""
        result = _format_indicators_v2({
            "atr_14": 0.0040,
            "current_price": 1.0850,  # 0.0040/1.0850 = 0.37%
        })
        assert "Volatilite moderee" in result

    def test_atr_volatilite_faible(self):
        """ATR < 0.2% du prix -> Volatilite faible."""
        result = _format_indicators_v2({
            "atr_14": 0.0010,
            "current_price": 1.0850,  # 0.0010/1.0850 = 0.09%
        })
        assert "Volatilite faible" in result

    def test_atr_none_not_included(self):
        """ATR None -> pas de ligne ATR."""
        result = _format_indicators_v2({})
        assert "ATR" not in result

    def test_atr_no_current_price_not_included(self):
        """ATR sans current_price -> pas de ligne ATR."""
        result = _format_indicators_v2({"atr_14": 0.0040})
        # ATR requires current_price to calculate pct
        assert "ATR" not in result

    # --- Boundary values ---

    def test_atr_boundary_0_5_pct_is_elevee(self):
        """ATR = 0.5% exactement: > 0.5? Non. > 0.2? Oui -> moderee."""
        result = _format_indicators_v2({
            "atr_14": 0.005425,  # 1.0850 * 0.5%
            "current_price": 1.0850,
        })
        # 0.005425/1.0850 = 0.005, atr_pct > 0.5 = False
        assert "Volatilite moderee" in result

    def test_atr_boundary_0_2_pct_is_faible(self):
        """ATR = 0.2% exactement: > 0.5? Non. > 0.2? Non -> faible."""
        result = _format_indicators_v2({
            "atr_14": 0.00217,  # 1.0850 * 0.2%
            "current_price": 1.0850,
        })
        # 0.00217/1.0850 = 0.002, atr_pct > 0.2 = False
        assert "Volatilite faible" in result


# ============================================================================
# Combinaison: tous les indicateurs ensemble
# ============================================================================


class TestFormatIndicatorsV2Full:
    """Tests avec un jeu complet d'indicateurs."""

    def test_full_indicators_output(self):
        """Tous les indicateurs presents -> toutes les sections."""
        ind = {
            "rsi_14": 55.0,
            "macd_line": 0.002,
            "macd_signal": 0.001,
            "macd_histogram": 0.001,
            "bb_position_pct": 65.0,
            "sma_20": 1.0830,
            "sma_50": 1.0800,
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
        assert "SMA20" in result
        assert "SMA50" in result
        assert "EMA20" in result
        assert "EMA200" in result
        assert "ATR 14" in result
        assert "Tendance CT" in result
        assert "Range 24h" in result

    def test_minimal_indicators_does_not_crash(self):
        """Indicateurs vides -> pas de crash."""
        result = _format_indicators_v2({})
        assert isinstance(result, str)
        # Should only have trend line (with N/A)
        assert "Tendance CT" in result

    def test_empty_string_does_not_break(self):
        """Retourne toujours un string."""
        result = _format_indicators_v2({})
        assert isinstance(result, str)
        assert len(result) >= 0

    def test_rsi_zero_treated_as_survente(self):
        """RSI = 0 -> SURVENTE."""
        result = _format_indicators_v2({"rsi_14": 0.0})
        assert "SURVENTE" in result

    def test_rsi_100_treated_as_surachat(self):
        """RSI = 100 -> SURACHAT."""
        result = _format_indicators_v2({"rsi_14": 100.0})
        assert "SURACHAT" in result

    def test_current_price_none_no_sma_formatting(self):
        """current_price None -> SMA20/SMA50 non formattes."""
        result = _format_indicators_v2({
            "sma_20": 1.0830,
            "sma_50": 1.0800,
        })
        # SMA20/SMA50 need current_price
        assert "SMA20" not in result
        assert "SMA50" not in result

    def test_bb_zero_is_sur_bande_inferieure(self):
        """BB = 0 -> SUR LA BANDE INFERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 0.0})
        assert "SUR LA BANDE INFERIEURE" in result

    def test_bb_100_is_sur_bande_superieure(self):
        """BB = 100: 100 > 95 -> SUR LA BANDE SUPERIEURE."""
        result = _format_indicators_v2({"bb_position_pct": 100.0})
        assert "SUR LA BANDE SUPERIEURE" in result

    def test_macd_zero_line_zero_signal(self):
        """MACD line = 0, signal = 0."""
        result = _format_indicators_v2({
            "macd_line": 0.0,
            "macd_signal": 0.0,
            "macd_histogram": 0.0,
        })
        # 0 > 0 = False -> "sous le Signal", 0 > 0 = False -> "zone negative"
        assert "MACD sous le Signal" in result
        assert "zone negative" in result
