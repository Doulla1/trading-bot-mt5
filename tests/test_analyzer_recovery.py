"""Tests for _recover_truncated_json in analyzer.py.

Covers the JSON recovery function that salvages truncated DeepSeek responses.
"""

import json
import pytest
from src.ai.analyzer import _recover_truncated_json


class TestRecoverTruncatedJson:
    """Tests unitaires pour la fonction de recuperation JSON."""

    def test_valid_json_returns_as_is(self):
        """Un JSON valide est retourne tel quel."""
        raw = '{"action": "HOLD", "confidence": 80, "reasoning": "test"}'
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["action"] == "HOLD"
        assert result["confidence"] == 80

    def test_empty_string_returns_none(self):
        """Une chaine vide retourne None."""
        assert _recover_truncated_json("") is None

    def test_no_json_returns_none(self):
        """Du texte sans JSON retourne None."""
        assert _recover_truncated_json("just some text without json") is None

    def test_truncated_json_salvaged_strategy1(self):
        """JSON tronque recupere via fermeture d'accolades."""
        raw = '{"action": "SELL", "confidence": 75, "reasoning": "Tendance'
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["action"] == "SELL"
        assert result["confidence"] == 75

    def test_field_extraction_fallback_strategy3(self):
        """Extraction champ par champ en fallback."""
        raw = 'some garbage {"action": "CLOSE", "confidence": 65} more garbage'
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["action"] == "CLOSE"
        assert result["confidence"] == 65

    def test_deepseek_typical_truncation(self):
        """Simule une reponse DeepSeek tronquee typique (reasoning coupe)."""
        raw = (
            '{"reference_swing_high": 1.15403, '
            '"reference_swing_low": null, '
            '"is_sl_tp_aligned_with_structure": "NO", '
            '"action": "HOLD", '
            '"confidence": 60, '
            '"reasoning": "Tendance baissiere confirmee'
        )
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["action"] == "HOLD"
        assert result["confidence"] == 60

    def test_missing_closing_brace_fixed(self):
        """JSON sans accolade fermante est repare."""
        raw = (
            '{"action": "BUY", "confidence": 85, "reasoning": "OK", '
            '"stop_loss_pips": 20, "take_profit_pips": 40, '
            '"risk_level": "LOW", "is_sl_tp_aligned_with_structure": "YES"'
        )
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["action"] == "BUY"

    def test_null_fields_preserved(self):
        """Les champs null sont correctement interpretes."""
        raw = (
            '{"action": "HOLD", "confidence": 50, "reasoning": "ok", '
            '"stop_loss_pips": 0, "take_profit_pips": 0, '
            '"risk_level": "LOW", "reference_swing_high": null, '
            '"reference_swing_low": null, '
            '"is_sl_tp_aligned_with_structure": "NO"}'
        )
        result = _recover_truncated_json(raw)
        assert result is not None
        assert result["reference_swing_high"] is None
        assert result["reference_swing_low"] is None

    def test_complete_json_still_works(self):
        """Un JSON complet avec tous les champs passe sans erreur."""
        data = {
            "reference_swing_high": 1.15403,
            "reference_swing_low": 1.15353,
            "is_sl_tp_aligned_with_structure": "NO",
            "action": "HOLD",
            "confidence": 50,
            "reasoning": "Tendance baissiere confirmee par EMA, Ichimoku et ADX.",
            "stop_loss_pips": 0,
            "take_profit_pips": 0,
            "risk_level": "LOW",
        }
        raw = json.dumps(data, ensure_ascii=False)
        result = _recover_truncated_json(raw)
        assert result == data