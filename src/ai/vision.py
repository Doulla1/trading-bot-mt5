"""Analyse de screenshots via GPT-4o-mini Vision API."""

import base64
import io
import json
import re
from pathlib import Path
from openai import OpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from PIL import Image

from src.config import settings
from src.ai.prompts import build_analysis_prompt


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def analyze(screenshot_path, symbol, timeframe, indicators, calendar_events, open_positions, account_info) -> dict | None:
    """Envoie le screenshot + donnees structurees a GPT-4o-mini. Retourne la decision JSON ou None."""
    client = OpenAI(api_key=settings.openai_api_key)

    # Redimensionner et compresser l'image avant envoi (MED-04)
    img = Image.open(screenshot_path)
    img = img.resize((512, 384), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = build_analysis_prompt(
        symbol=symbol, timeframe=timeframe, indicators=indicators,
        calendar_events=calendar_events, open_positions=open_positions, account_info=account_info,
    )

    logger.info(f"Envoi analyse a GPT-4o-mini pour {symbol}...")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "low"}},
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=600,
        temperature=0.3,
    )

    raw = response.choices[0].message.content or ""
    logger.debug(f"Reponse brute IA: {raw[:300]}...")

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        logger.error(f"Pas de JSON dans la reponse IA: {raw[:200]}")
        return None

    try:
        decision = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"JSON invalide: {e}")
        return None

    required = ["action", "confidence", "reasoning", "stop_loss_pips", "take_profit_pips", "risk_level"]
    for field in required:
        if field not in decision:
            logger.error(f"Champ manquant: {field}")
            return None

    valid_actions = {"BUY", "SELL", "HOLD", "CLOSE"}
    if decision["action"] not in valid_actions:
        logger.error(f"Action invalide: {decision['action']}")
        return None

    # Validation des plages de valeurs (HIGH-02)
    if not (0 <= decision["confidence"] <= 100):
        logger.error(f"Confiance invalide: {decision['confidence']}")
        return None
    if not (5 <= decision["stop_loss_pips"] <= 100):
        logger.error(f"Stop loss pips invalide: {decision['stop_loss_pips']}")
        return None
    if decision["take_profit_pips"] < decision["stop_loss_pips"] * 1.5:
        logger.error(f"TP {decision['take_profit_pips']} < 1.5x SL {decision['stop_loss_pips']}")
        return None
    if decision["risk_level"] not in ("LOW", "MEDIUM", "HIGH"):
        logger.error(f"Risk level invalide: {decision.get('risk_level')}")
        return None

    logger.info(f"Decision IA: {decision['action']} | Confiance: {decision['confidence']}% | SL: {decision['stop_loss_pips']}pips | TP: {decision['take_profit_pips']}pips")
    return decision
