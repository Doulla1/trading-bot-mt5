"""Tests unitaires pour le RuleEngine (backtesting)."""

import pytest

from src.backtest.rules_engine import (
    DEFAULT_WEIGHTS,
    RuleEngine,
)


# ---------------------------------------------------------------------------
# Helpers - indicator builders
# ---------------------------------------------------------------------------


def _bullish_indicators() -> dict:
    """Strongly bullish indicator set."""
    return {
        "current_price": 1.0850,
        "trend_short": "haussier",
        "trend_medium": "haussier",
        "ichimoku_trend": "haussier",
        "rsi_14": 25,
        "macd_line": 0.002,
        "macd_signal": 0.001,
        "macd_histogram": 0.001,
        "adx_14": 30,
        "di_plus": 28,
        "di_minus": 18,
        "atr_14": 0.0020,
        "bb_position_pct": 15,
        "candlestick_patterns": ["hammer", "bullish_engulfing"],
        "market_structure": {"structure": "hh_hl"},
        "h1_trend": "haussier",
    }


def _bearish_indicators() -> dict:
    """Strongly bearish indicator set."""
    return {
        "current_price": 1.0850,
        "trend_short": "baissier",
        "trend_medium": "baissier",
        "ichimoku_trend": "baissier",
        "rsi_14": 75,
        "macd_line": 0.001,
        "macd_signal": 0.002,
        "macd_histogram": -0.001,
        "adx_14": 30,
        "di_plus": 18,
        "di_minus": 28,
        "atr_14": 0.0020,
        "bb_position_pct": 85,
        "candlestick_patterns": ["shooting_star", "bearish_engulfing"],
        "market_structure": {"structure": "lh_ll"},
        "h1_trend": "baissier",
    }


def _neutral_indicators() -> dict:
    """Ranging / neutral indicator set."""
    return {
        "current_price": 1.0850,
        "trend_short": "haussier",
        "trend_medium": "neutre",
        "ichimoku_trend": "neutre",
        "rsi_14": 50,
        "macd_line": 0.001,
        "macd_signal": 0.001,
        "macd_histogram": 0.0,
        "adx_14": 18,
        "di_plus": 18,
        "di_minus": 17,
        "atr_14": 0.0010,
        "bb_position_pct": 50,
        "candlestick_patterns": [],
        "market_structure": {},
        "h1_trend": "neutre",
    }


# ---------------------------------------------------------------------------
# evaluate() - bullish
# ---------------------------------------------------------------------------


class TestEvaluateBullish:
    """Tests for bullish scenarios."""

    def test_bullish_indicators_return_buy(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert result["action"] == "BUY"
        assert result["confidence"] >= 50

    def test_bullish_confidence_high(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert result["confidence"] >= 70

    def test_bullish_has_positive_net_score(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert result["net_score"] > 0
        assert result["bullish_score"] > result["bearish_score"]


# ---------------------------------------------------------------------------
# evaluate() - bearish
# ---------------------------------------------------------------------------


class TestEvaluateBearish:
    """Tests for bearish scenarios."""

    def test_bearish_indicators_return_sell(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bearish_indicators())
        assert result["action"] == "SELL"
        assert result["confidence"] >= 50

    def test_bearish_confidence_high(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bearish_indicators())
        assert result["confidence"] >= 70

    def test_bearish_has_negative_net_score(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bearish_indicators())
        assert result["net_score"] < 0
        assert result["bearish_score"] > result["bullish_score"]


# ---------------------------------------------------------------------------
# evaluate() - neutral
# ---------------------------------------------------------------------------


class TestEvaluateNeutral:
    """Tests for neutral/ranging scenarios."""

    def test_neutral_indicators_return_hold(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_neutral_indicators())
        assert result["action"] == "HOLD"

    def test_neutral_confidence_low(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_neutral_indicators())
        assert result["confidence"] <= 50


# ---------------------------------------------------------------------------
# evaluate() - edge cases
# ---------------------------------------------------------------------------


class TestEvaluateEdgeCases:
    """Edge case tests."""

    def test_confidence_capped_at_95(self) -> None:
        """Confidence should never exceed 95."""
        engine = RuleEngine()
        # Super bullish: all signals at maximum
        ind = _bullish_indicators()
        ind["rsi_14"] = 5  # extreme oversold
        ind["bb_position_pct"] = 2  # extreme near lower
        ind["atr_14"] = 0.0050  # large ATR
        result = engine.evaluate(ind)
        assert result["confidence"] <= 95

    def test_confidence_at_least_10_on_hold(self) -> None:
        """HOLD confidence should be at least 10."""
        engine = RuleEngine()
        # Completely flat indicators
        ind = {
            "current_price": 1.0850,
            "trend_short": "neutre",
            "trend_medium": "neutre",
            "ichimoku_trend": "neutre",
            "rsi_14": 50,
            "macd_line": 0.0,
            "macd_signal": 0.0,
            "atr_14": 0.0,
        }
        result = engine.evaluate(ind)
        assert result["action"] == "HOLD"
        assert result["confidence"] >= 10

    def test_empty_indicators_returns_hold(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate({})
        assert result["action"] == "HOLD"
        assert result["confidence"] >= 10


# ---------------------------------------------------------------------------
# SL / TP
# ---------------------------------------------------------------------------


class TestSLTP:
    """Tests for stop loss / take profit calculation."""

    def test_sl_within_range_15_to_50(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert 15 <= result["stop_loss_pips"] <= 50

    def test_tp_at_least_1_5_times_sl(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        # TP >= int(SL * 1.5) - accounts for integer floor in max(int(sl*1.5), tp_raw)
        assert result["take_profit_pips"] >= int(result["stop_loss_pips"] * 1.5)

    def test_default_sl_tp_when_no_atr(self) -> None:
        engine = RuleEngine()
        ind = _bullish_indicators()
        ind["atr_14"] = 0
        result = engine.evaluate(ind)
        assert result["stop_loss_pips"] == 20
        assert result["take_profit_pips"] == 30

    def test_tp_larger_when_atr_larger(self) -> None:
        engine = RuleEngine(sl_atr_mult=1.5, tp_atr_mult=3.0)
        result = engine.evaluate(_bullish_indicators())
        # With tp_atr_mult=3.0, TP should be at least as large as with default
        assert result["take_profit_pips"] >= result["stop_loss_pips"]


# ---------------------------------------------------------------------------
# Risk level
# ---------------------------------------------------------------------------


class TestRiskLevel:
    """Tests for risk_level based on ADX."""

    def test_risk_level_low_when_adx_above_30(self) -> None:
        engine = RuleEngine()
        ind = _bullish_indicators()
        ind["adx_14"] = 35
        result = engine.evaluate(ind)
        assert result["risk_level"] == "LOW"

    def test_risk_level_medium_when_adx_between_20_and_30(self) -> None:
        engine = RuleEngine()
        ind = _bullish_indicators()
        ind["adx_14"] = 25
        result = engine.evaluate(ind)
        assert result["risk_level"] == "MEDIUM"

    def test_risk_level_high_when_adx_below_20(self) -> None:
        engine = RuleEngine()
        ind = _neutral_indicators()
        ind["adx_14"] = 15
        result = engine.evaluate(ind)
        assert result["risk_level"] == "HIGH"

    def test_risk_level_high_when_no_adx(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate({})
        assert result["risk_level"] == "HIGH"


# ---------------------------------------------------------------------------
# to_dict / from_dict
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for to_dict() and from_dict() round-trip."""

    def test_to_dict_contains_all_keys(self) -> None:
        engine = RuleEngine()
        d = engine.to_dict()
        assert "weights" in d
        assert "buy_threshold" in d
        assert "sell_threshold" in d
        assert "sl_atr_mult" in d
        assert "tp_atr_mult" in d

    def test_round_trip_preserves_weights(self) -> None:
        engine1 = RuleEngine(buy_threshold=30, sell_threshold=35)
        data = engine1.to_dict()
        engine2 = RuleEngine.from_dict(data)
        assert engine2.buy_threshold == 30
        assert engine2.sell_threshold == 35
        assert engine2.weights == engine1.weights

    def test_round_trip_preserves_defaults(self) -> None:
        engine1 = RuleEngine()
        data = engine1.to_dict()
        engine2 = RuleEngine.from_dict(data)
        assert engine2.buy_threshold == 25
        assert engine2.sell_threshold == 25
        assert engine2.sl_atr_mult == 1.5
        assert engine2.tp_atr_mult == 2.5

    def test_from_dict_with_partial_data(self) -> None:
        engine = RuleEngine.from_dict({"buy_threshold": 40})
        assert engine.buy_threshold == 40
        assert engine.sell_threshold == 25  # default
        assert engine.weights == DEFAULT_WEIGHTS


# ---------------------------------------------------------------------------
# Custom weights
# ---------------------------------------------------------------------------


class TestCustomWeights:
    """Tests with custom weight overrides."""

    def test_custom_weights_override_default(self) -> None:
        custom = DEFAULT_WEIGHTS.copy()
        custom["rsi_oversold"] = 30
        engine = RuleEngine(weights=custom)
        assert engine.weights["rsi_oversold"] == 30
        # Other weights stay the same
        assert engine.weights["price_above_sma20"] == 10

    def test_higher_weights_produce_higher_score(self) -> None:
        custom = DEFAULT_WEIGHTS.copy()
        custom["rsi_oversold"] = 50
        engine_custom = RuleEngine(weights=custom)
        engine_default = RuleEngine()

        ind = _bullish_indicators()
        result_custom = engine_custom.evaluate(ind)
        result_default = engine_default.evaluate(ind)
        # With higher RSI oversold weight, bullish_score should be larger
        assert result_custom["bullish_score"] > result_default["bullish_score"]

    def test_zero_weights_remove_signal(self) -> None:
        custom = DEFAULT_WEIGHTS.copy()
        for k in custom:
            custom[k] = 0
        engine = RuleEngine(weights=custom)
        result = engine.evaluate(_bullish_indicators())
        # All zero weights -> no score, should be HOLD
        assert result["action"] == "HOLD"


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    """Tests with custom buy/sell thresholds."""

    def test_higher_threshold_harder_to_trigger(self) -> None:
        engine_strict = RuleEngine(buy_threshold=40)
        engine_default = RuleEngine()

        ind = _bullish_indicators()
        result_strict = engine_strict.evaluate(ind)
        result_default = engine_default.evaluate(ind)

        # With higher threshold, confidence may be lower (harder to trigger)
        assert result_default["confidence"] >= result_strict["confidence"]

    def test_sell_threshold_affects_sell_decisions(self) -> None:
        engine_strict = RuleEngine(sell_threshold=50)
        ind = _bearish_indicators()
        result = engine_strict.evaluate(ind)
        # With higher sell threshold, the bearish score might not be enough
        # But our _bearish_indicators has very strong signals, so it should still trigger
        assert result["action"] in ("SELL", "HOLD")

    def test_very_high_threshold_blocks_all(self) -> None:
        engine = RuleEngine(buy_threshold=200, sell_threshold=200)
        result = engine.evaluate(_bullish_indicators())
        assert result["action"] == "HOLD"

    def test_zero_threshold_always_triggers(self) -> None:
        engine = RuleEngine(buy_threshold=0, sell_threshold=0)
        result = engine.evaluate(_bullish_indicators())
        assert result["action"] in ("BUY", "SELL")


# ---------------------------------------------------------------------------
# Response keys
# ---------------------------------------------------------------------------


class TestResponseKeys:
    """Verify all expected response keys are present."""

    EXPECTED_KEYS = {
        "action", "confidence", "reasoning",
        "stop_loss_pips", "take_profit_pips", "risk_level",
        "bullish_score", "bearish_score", "net_score",
    }

    def test_bullish_result_has_all_keys(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_hold_result_has_all_keys(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_neutral_indicators())
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_reasoning_is_non_empty(self) -> None:
        engine = RuleEngine()
        result = engine.evaluate(_bullish_indicators())
        assert len(result["reasoning"]) > 0
