"""Analyseur DeepSeek V4 Pro - decision de trading avec contexte 1M tokens.

Reçoit TOUTES les donnees structurees et prend la decision finale."""

import json
import re
from openai import OpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.ai.prompts import build_decision_prompt


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=3, max=30))
def make_decision(indicators, ocr_data, calendar_events, open_positions,
                  account_info, trade_history, session_context,
                  performance_stats=None) -> dict | None:
    """Envoie toutes les donnees a DeepSeek V4 Pro. Retourne la decision JSON ou None."""
    if not settings.deepseek_api_key:
        logger.warning("Pas de cle DeepSeek - fallback sur GPT-4o-mini")
        return None

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1",
    )

    prompt = build_decision_prompt(
        symbol=settings.trading_symbol,
        timeframe=settings.trading_timeframe,
        indicators=indicators,
        ocr_data=ocr_data,
        calendar_events=calendar_events,
        open_positions=open_positions,
        account_info=account_info,
        trade_history=trade_history,
        session_context=session_context,
        performance_stats=performance_stats,
    )

    logger.info(f"Envoi decision a DeepSeek V4 Pro pour {settings.trading_symbol}...")

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        logger.debug(f"DeepSeek reponse: {raw[:400]}...")
        logger.info(f"Tokens: {response.usage.total_tokens} (prompt={response.usage.prompt_tokens})")

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.error(f"Pas de JSON dans la reponse DeepSeek: {raw[:200]}")
            return None

        decision = json.loads(json_match.group(0))

        # Validation
        if not _validate_decision(decision):
            return None

        # Normaliser confidence: DeepSeek peut donner 0-1 ou 0-100
        conf = decision.get("confidence", 0)
        if isinstance(conf, (int, float)) and conf <= 1:
            decision["confidence"] = int(conf * 100)

        logger.info(
            f"DeepSeek: {decision['action']} | Confiance: {decision['confidence']}% | "
            f"SL: {decision['stop_loss_pips']}pips | TP: {decision['take_profit_pips']}pips | "
            f"Risque: {decision.get('risk_level', '?')}"
        )
        return decision

    except Exception as e:
        logger.error(f"Echec DeepSeek: {e}")
        return None


def make_decision_fast(indicators, ocr_data, calendar_events, open_positions,
                       account_info, trade_history, session_context) -> dict | None:
    """Version rapide avec deepseek-v4-flash pour les cycles de confirmation."""
    if not settings.deepseek_api_key:
        return None

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1",
    )

    prompt = build_decision_prompt(
        symbol=settings.trading_symbol,
        timeframe=settings.trading_timeframe,
        indicators=indicators,
        ocr_data=ocr_data,
        calendar_events=calendar_events,
        open_positions=open_positions,
        account_info=account_info,
        trade_history=trade_history,
        session_context=session_context,
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return None
        decision = json.loads(json_match.group(0))
        if not _validate_decision(decision):
            return None
        conf = decision.get("confidence", 0)
        if isinstance(conf, (int, float)) and conf <= 1:
            decision["confidence"] = int(conf * 100)
        return decision
    except Exception:
        return None


def _validate_decision(decision: dict) -> bool:
    """Valide les champs et plages de la decision."""
    required = ["action", "confidence", "reasoning", "stop_loss_pips", "take_profit_pips", "risk_level"]
    for field in required:
        if field not in decision:
            logger.error(f"Champ manquant: {field}")
            return False

    if decision["action"] not in ("BUY", "SELL", "HOLD", "CLOSE"):
        logger.error(f"Action invalide: {decision['action']}")
        return False

    conf = decision["confidence"]
    if isinstance(conf, (int, float)) and conf <= 1:
        conf = int(conf * 100)
    if not (0 <= conf <= 100):
        logger.error(f"Confiance invalide: {decision['confidence']}")
        return False

    sl = decision["stop_loss_pips"]
    tp = decision["take_profit_pips"]

    # HOLD/CLOSE peuvent avoir SL=0, TP=0
    if decision["action"] in ("BUY", "SELL"):
        if not (5 <= sl <= 100):
            logger.error(f"SL pips invalide pour BUY/SELL: {sl}")
            return False
        if tp < sl * 1.5:
            logger.error(f"TP {tp} < 1.5x SL {sl}")
            return False

    if decision["risk_level"] not in ("LOW", "MEDIUM", "HIGH"):
        logger.error(f"Risk level invalide: {decision.get('risk_level')}")
        return False

    return True
