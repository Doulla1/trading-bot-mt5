"""Tests unitaires pour la validation des reponses IA."""

import json
import pytest
from unittest.mock import patch, MagicMock
from src.ai.vision import analyze


def _mock_openai_response(content: str):
    """Cree un mock de reponse OpenAI."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


class TestAIVisionValidation:
    """Tests de la validation de reponse IA (HIGH-02)."""

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_valid_buy_decision(self, mock_image, mock_openai):
        """Decision BUY valide doit passer."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "BUY",
                "confidence": 85,
                "reasoning": "Tendance haussiere confirmee.",
                "stop_loss_pips": 20,
                "take_profit_pips": 40,
                "risk_level": "MEDIUM",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={"current_price": 1.0850},
            calendar_events=[],
            open_positions=[],
            account_info={"balance": 10000},
        )
        assert result is not None
        assert result["action"] == "BUY"
        assert result["confidence"] == 85

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_confidence_out_of_range_rejected(self, mock_image, mock_openai):
        """Confiance > 100 doit etre rejetee."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "BUY",
                "confidence": 150,
                "reasoning": "Test",
                "stop_loss_pips": 20,
                "take_profit_pips": 40,
                "risk_level": "LOW",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_sl_too_small_rejected(self, mock_image, mock_openai):
        """SL < 5 pips doit etre rejete."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "SELL",
                "confidence": 80,
                "reasoning": "Test",
                "stop_loss_pips": 2,
                "take_profit_pips": 40,
                "risk_level": "LOW",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_tp_less_than_15x_sl_rejected(self, mock_image, mock_openai):
        """TP < 1.5x SL doit etre rejete."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "BUY",
                "confidence": 80,
                "reasoning": "Test",
                "stop_loss_pips": 30,
                "take_profit_pips": 40,
                "risk_level": "LOW",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_invalid_risk_level_rejected(self, mock_image, mock_openai):
        """Risk level invalide doit etre rejete."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "SELL",
                "confidence": 75,
                "reasoning": "Test",
                "stop_loss_pips": 25,
                "take_profit_pips": 50,
                "risk_level": "EXTREME",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_invalid_action_rejected(self, mock_image, mock_openai):
        """Action invalide doit etre rejetee."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "SHORT",
                "confidence": 80,
                "reasoning": "Test",
                "stop_loss_pips": 20,
                "take_profit_pips": 40,
                "risk_level": "LOW",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None

    @patch("src.ai.vision.OpenAI")
    @patch("src.ai.vision.Image")
    def test_missing_required_field_rejected(self, mock_image, mock_openai):
        """Champ obligatoire manquant -> rejete."""
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img
        client = MagicMock()
        mock_openai.return_value = client
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({
                "action": "BUY",
                "confidence": 80,
                "reasoning": "Test",
                # stop_loss_pips manquant
                "take_profit_pips": 40,
                "risk_level": "LOW",
            })
        )
        from pathlib import Path
        result = analyze(
            screenshot_path=Path("fake.png"),
            symbol="EURUSD", timeframe="M15",
            indicators={},
            calendar_events=[],
            open_positions=[],
            account_info={},
        )
        assert result is None
