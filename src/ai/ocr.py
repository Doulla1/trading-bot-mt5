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
    """Extrait la structure visuelle du chart via GPT-4o Vision (BUG-3: detail=high + ancrage prix).
    Retourne un dict avec niveaux, patterns, structure - ou None si echec."""
    if not settings.openai_api_key:
        logger.warning("Pas de cle OpenAI - OCR desactive")
        return None

    client = OpenAI(api_key=settings.openai_api_key)

    # Recuperer le prix actuel pour ancrer l'OCR (BUG-3: evite hallucinations de niveaux)
    current_price = _get_current_price(symbol)

    # Compression image - conserver taille native pour detail=high (lisibilite axe Y)
    img = Image.open(screenshot_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    price_anchor = f"\nCURRENT PRICE: {current_price:.5f}. Support/resistance levels MUST be within a range of ±3% around this price ({current_price * 0.97:.5f} - {current_price * 1.03:.5f}). Any level outside this range is invalid." if current_price else ""

    prompt = f"""Analyze this trading chart ({symbol}, timeframe={timeframe}) and extract ONLY the visual elements. Do NOT make any trading decisions.{price_anchor}

Respond in JSON format:
{{
  "support_levels": [list of support prices visible when reading the Y-axis of the chart],
  "resistance_levels": [list of resistance prices visible when reading the Y-axis of the chart],
  "trendlines": "description of the trendlines",
  "chart_patterns": ["list of visible patterns: double top/bottom, head and shoulders, triangle, flag, wedge, channel"],
  "candlestick_visual": "description of the recent visible candlesticks",
  "market_phase": "trending_up|trending_down|ranging|breakout|reversal",
  "price_action_notes": "notes on the price action (rejections, wicks, breakouts)"
}}
Ensure all description fields are written in English."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            max_tokens=500,
            temperature=0.1,
        )

        raw = response.choices[0].message.content or ""
        logger.debug(f"OCR brut: {raw[:200]}...")

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.error(f"Pas de JSON dans la reponse OCR: {raw[:150]}")
            return None

        ocr_data = json.loads(json_match.group(0))
        logger.info(f"OCR OK: phase={ocr_data.get('market_phase', '?')} | supports={ocr_data.get('support_levels', [])} | resistances={ocr_data.get('resistance_levels', [])}")
        return ocr_data

    except Exception as e:
        logger.error(f"Echec OCR: {e}")
        return None


def _get_current_price(symbol: str) -> float | None:
    """Recupere le prix actuel du symbole depuis MT5 pour ancrer l'OCR."""
    try:
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return (tick.bid + tick.ask) / 2
    except Exception:
        pass
    return None
