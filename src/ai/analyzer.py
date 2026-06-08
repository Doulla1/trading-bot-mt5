"""Analyseur IA multi-provider - decision de trading.

v4.0: Configuration via .env (AI_PROVIDER, AI_MODEL, AI_BASE_URL, AI_API_KEY).
Compatible OpenAI, DeepSeek, OpenRouter, Azure et toute API OpenAI-compatible.
Pour changer de fournisseur, modifier les variables dans .env - pas le code."""

import json
import re
from openai import OpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.ai.prompts import build_decision_prompt


def _make_client() -> OpenAI | None:
    """Cree un client OpenAI configure selon les parametres .env.

    Utilise ai_api_key_resolved (ai_api_key puis fallback deepseek_api_key).
    Retourne None si aucune cle n'est configuree."""
    api_key = settings.ai_api_key_resolved
    if not api_key:
        logger.warning(f"Aucune cle API - Verifier AI_API_KEY ou DEEPSEEK_API_KEY dans .env")
        return None
    return OpenAI(api_key=api_key, base_url=settings.ai_base_url)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=3, max=30))
def make_decision(indicators, ocr_data, calendar_events, open_positions,
                  account_info, trade_history, session_context,
                  performance_stats=None) -> dict | None:
    """Envoie toutes les donnees a l'IA. Retourne la decision JSON ou None."""
    client = _make_client()
    if client is None:
        return None

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

    logger.info(
        f"Envoi decision a {settings.ai_provider}/{settings.ai_model} pour {settings.trading_symbol}..."
    )

    try:
        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        logger.debug(f"{settings.ai_provider} reponse: {raw[:400]}...")
        if response.usage:
            logger.info(f"Tokens: {response.usage.total_tokens} (prompt={response.usage.prompt_tokens})")

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.error(f"Pas de JSON dans la reponse {settings.ai_provider}: {raw[:200]}")
            return None

        decision = json.loads(json_match.group(0))

        if not _validate_decision(decision):
            return None

        # Normaliser confidence: certains modeles donnent 0-1, d'autres 0-100
        conf = decision.get("confidence", 0)
        if isinstance(conf, (int, float)) and conf <= 1:
            decision["confidence"] = int(conf * 100)

        logger.info(
            f"{settings.ai_provider}: {decision['action']} | Confiance: {decision['confidence']}% | "
            f"SL: {decision['stop_loss_pips']}pips | TP: {decision['take_profit_pips']}pips | "
            f"Risque: {decision.get('risk_level', '?')}"
        )
        return decision

    except Exception as e:
        logger.error(f"Echec {settings.ai_provider}: {e}")
        return None


def make_decision_fast(indicators, ocr_data, calendar_events, open_positions,
                       account_info, trade_history, session_context) -> dict | None:
    """Version rapide avec le modele secondaire (ai_fast_model) pour les cycles de confirmation."""
    client = _make_client()
    if client is None:
        return None

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
            model=settings.ai_fast_model,
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
    required = [
        "action", "confidence", "reasoning", "stop_loss_pips",
        "take_profit_pips", "risk_level", "is_sl_tp_aligned_with_structure"
    ]
    for field in required:
        if field not in decision:
            logger.error(f"Champ manquant dans la decision IA: {field}")
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

    # v4.0: SL max elargi a 300 pour XAUUSD (ATR SL peut atteindre 200+ pips)
    if decision["action"] in ("BUY", "SELL"):
        if not (5 <= sl <= 300):
            logger.error(f"SL pips invalide pour BUY/SELL: {sl}")
            return False
        if tp < sl * 1.5:
            logger.error(f"TP {tp} < 1.5x SL {sl}")
            return False

    if decision["risk_level"] not in ("LOW", "MEDIUM", "HIGH"):
        logger.error(f"Risk level invalide: {decision.get('risk_level')}")
        return False

    return True
