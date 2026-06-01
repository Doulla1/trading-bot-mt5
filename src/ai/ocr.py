"""OCR du chart via GPT-4o-mini Vision - extraction visuelle uniquement.

Ne prend PAS de decision de trading. Se contente d'extraire la structure
visuelle du graphique: niveaux, patterns, structure de marche."""

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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def extract_chart_structure(screenshot_path, symbol, timeframe) -> dict | None:
    """Extrait la structure visuelle du chart via GPT-4o-mini Vision.
    Retourne un dict avec niveaux, patterns, structure - ou None si echec."""
    if not settings.openai_api_key:
        logger.warning("Pas de cle OpenAI - OCR desactive")
        return None

    client = OpenAI(api_key=settings.openai_api_key)

    # Compression image
    img = Image.open(screenshot_path)
    img = img.resize((512, 384), Image.LANCZOS)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = f"""Analyse ce graphique de trading ({symbol}, timeframe={timeframe}) et extrait UNIQUEMENT les elements visuels. Ne donne PAS de decision de trading.

Reponds en JSON:
{{
  "support_levels": [liste des prix de supports visibles],
  "resistance_levels": [liste des prix de resistances visibles],
  "trendlines": "description des lignes de tendance",
  "chart_patterns": ["liste des patterns visibles: double top/bottom, head and shoulders, triangle, flag, wedge, channel"],
  "candlestick_visual": "description des chandeliers recents visibles",
  "market_phase": "trending_up|trending_down|ranging|breakout|reversal",
  "price_action_notes": "notes sur l'action du prix (rejets, mèches, breakouts)"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "low"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            max_tokens=300,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        logger.debug(f"OCR brut: {raw[:200]}...")

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.error(f"Pas de JSON dans la reponse OCR: {raw[:150]}")
            return None

        ocr_data = json.loads(json_match.group(0))
        logger.info(f"OCR OK: phase={ocr_data.get('market_phase', '?')}")
        return ocr_data

    except Exception as e:
        logger.error(f"Echec OCR: {e}")
        return None
