"""Analyseur IA multi-provider - decision de trading.

v4.1: JSON recovery for truncated responses + response_format JSON mode.
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


def _recover_truncated_json(raw: str) -> dict | None:
    """Essaie de recuperer un JSON tronque en fermant les accolades/guillemets manquants.

    DeepSeek coupe parfois la reponse au milieu du champ 'reasoning'.
    Cette fonction tente plusieurs strategies de reparation:
    1. Fermer les accolades non fermees
    2. Regex greedy standard (original)
    3. Couper au dernier champ valide et refermer le JSON
    4. Extraire les champs connus individuellement (fallback ultime)
    """
    if not raw:
        return None

    best_result: dict | None = None

    # Strategie 1: Ajouter les accolades fermantes manquantes
    open_braces = raw.count("{") - raw.count("}")
    if open_braces > 0:
        fixed = raw.rstrip().rstrip(",")
        if fixed and fixed[-1] not in ("}", '"', "]"):
            # Chercher le dernier guillemet ferme (fin de valeur string)
            last_quote = fixed.rfind('",')
            if last_quote > 0:
                fixed = fixed[:last_quote + 1]
            else:
                last_comma = fixed.rfind(",")
                if last_comma > 0:
                    fixed = fixed[:last_comma]
        fixed += "}" * open_braces
        try:
            best_result = json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # Strategie 2: Regex greedy standard (original)
    if best_result is None:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                best_result = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    # Si Strategie 1/2 a donne un resultat partiel, verifier les champs critiques
    if best_result is not None and "action" in best_result and "confidence" in best_result:
        return best_result

    # Strategie 3: Extraire les champs individuellement (fallback ultime)
    try:
        result = {}
        for field in ["action", "confidence", "reasoning", "stop_loss_pips",
                       "take_profit_pips", "risk_level",
                       "reference_swing_high", "reference_swing_low",
                       "is_sl_tp_aligned_with_structure"]:
            if field in ("action", "risk_level", "is_sl_tp_aligned_with_structure"):
                m = re.search(rf'"{field}"\s*:\s*"([^"]*)"', raw)
                if m:
                    result[field] = m.group(1)
            elif field == "reasoning":
                m = re.search(rf'"{field}"\s*:\s*"([^"]*)', raw)
                if m:
                    result[field] = m.group(1).rstrip()
            elif field in ("confidence", "stop_loss_pips", "take_profit_pips"):
                m = re.search(rf'"{field}"\s*:\s*(-?\d+(?:\.\d+)?)', raw)
                if m:
                    val = m.group(1)
                    result[field] = float(val) if "." in val else int(val)
            elif field in ("reference_swing_high", "reference_swing_low"):
                m = re.search(rf'"{field}"\s*:\s*(null|[\d.]+)', raw)
                if m:
                    val = m.group(1)
                    result[field] = None if val == "null" else float(val)

        if "action" in result and "confidence" in result:
            logger.warning(f"JSON partiellement recupere: {len(result)}/9 champs")
            if "reasoning" not in result:
                result["reasoning"] = "(reponse tronquee)"
            if "stop_loss_pips" not in result:
                result["stop_loss_pips"] = 0
            if "take_profit_pips" not in result:
                result["take_profit_pips"] = 0
            if "risk_level" not in result:
                result["risk_level"] = "MEDIUM"
            if "is_sl_tp_aligned_with_structure" not in result:
                result["is_sl_tp_aligned_with_structure"] = "NO"
            if "reference_swing_high" not in result:
                result["reference_swing_high"] = None
            if "reference_swing_low" not in result:
                result["reference_swing_low"] = None

            # Fusionner avec le meilleur resultat partiel des strategies 1/2
            if best_result is not None:
                for k, v in best_result.items():
                    if k not in result:
                        result[k] = v
            return result
    except Exception:
        pass

    # Dernier recours: retourner le resultat partiel meme sans confidence
    # (sera filtre par _validate_decision)
    return best_result


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
    """Envoie toutes les donnees a l'IA. Retourne la decision JSON ou None.

    Utilise response_format={"type": "json_object"} pour forcer un JSON valide.
    En cas de reponse tronquee, applique _recover_truncated_json() en fallback.
    Retry automatique via tenacity (2 tentatives, backoff exponentiel 3-30s).
    Avertit si les tokens de completion approchent la limite de 4096."""
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
        # Utiliser response_format JSON si le provider le supporte (DeepSeek, OpenAI)
        # Cela force le modele a renvoyer un JSON valide et reduit les troncatures
        extra_kwargs = {}
        try:
            extra_kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass  # Certains providers ne supportent pas, on ignore

        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.ai_max_tokens,
            temperature=0.2,
            **extra_kwargs,
        )

        raw = response.choices[0].message.content or ""
        if response.usage:
            logger.info(
                f"Tokens: {response.usage.total_tokens} "
                f"(prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens})"
            )
            # Alerte si on approche la limite de tokens de sortie
            if response.usage.completion_tokens >= (settings.ai_max_tokens - 500):
                logger.warning(
                    f"Reponse proche de la limite tokens ({response.usage.completion_tokens}/{settings.ai_max_tokens}) - "
                    f"risque de troncature. Verifier max_tokens."
                )

        # Log plus de contexte pour debug
        logger.debug(f"{settings.ai_provider} reponse ({len(raw)} chars): {raw[:500]}...")

        # Essayer de parser le JSON, avec fallback sur recuperation
        decision = _recover_truncated_json(raw)
        if decision is None:
            logger.error(
                f"JSON irreparable de {settings.ai_provider}. "
                f"Reponse brute ({len(raw)} chars): {raw[:300]}"
            )
            return None

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
        extra_kwargs = {}
        try:
            extra_kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass

        response = client.chat.completions.create(
            model=settings.ai_fast_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
            **extra_kwargs,
        )
        raw = response.choices[0].message.content or ""
        decision = _recover_truncated_json(raw)
        if decision is None:
            return None
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
