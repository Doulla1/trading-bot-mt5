"""Analyse DeepSeek V4 Pro des resultats quotidiens de trading.

Envoie les statistiques et trades du jour a DeepSeek V4 Pro pour
une analyse approfondie des performances, patterns et recommandations.
"""

import json
from openai import OpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings


ANALYSIS_PROMPT = """Tu es un analyste quantitatif expert en trading Forex. Tu analyses les resultats
d'une journee de trading d'un bot automatise qui trade sur MT5 (Fusion Markets).

Voici les donnees du jour:

## Statistiques globales
- Trades totaux: {total_trades}
- Trades gagnants: {wins}
- Trades perdants: {losses}
- Win rate: {win_rate}%
- P&L total: {total_profit}
- Meilleur trade: {best_trade}
- Pire trade: {worst_trade}
- Profit moyen par trade: {avg_profit}
- Durée moyenne des trades: {avg_duration}
- Confiance moyenne: {avg_confidence}%

## Detail par symbole
{symbols_detail}

## Trades de la journee
{trades_detail}

Consignes:
1. Redige une analyse en francais, concise mais complete (300-500 mots).
2. Structure ton analyse en 4 sections:
   - **Resume**: synthese des performances du jour en 2-3 phrases.
   - **Forces**: ce qui a bien fonctionne (paires, patterns, moments de la journee).
   - **Faiblesses**: ce qui a mal fonctionne, pertes notables, erreurs potentielles.
   - **Recommandations**: suggestions concretes pour ameliorer les performances (parametres,
     gestion du risque, filtres, horaires a privilegier ou eviter).
3. Sois honnete et direct - si les resultats sont mauvais, dis-le clairement.
4. Mentionne les paires specifiques par leur nom (EURUSD, XAUUSD, etc.).
5. N'invente pas de donnees - base-toi uniquement sur les chiffres fournis.
6. Utilise des emojis avec parcimonie (1-2 max par section).

Reponds avec une analyse en texte brut (pas de JSON)."""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=3, max=20))
def analyze_daily_results(stats: dict, trades: list, symbols_detail: str) -> str:
    """Analyse les resultats quotidiens avec DeepSeek V4 Pro.

    Args:
        stats: Dictionnaire de statistiques globales.
        trades: Liste des trades du jour (dicts).
        symbols_detail: Texte formaté avec les details par symbole.

    Returns:
        Texte d'analyse en francais, ou message d'erreur si l'analyse echoue.
    """
    if not settings.ai_api_key_resolved:
        logger.warning("Pas de cle API - analyse IA indisponible")
        return "_Analyse IA non disponible (cle API manquante)._"

    # Formater les trades pour le prompt
    trades_lines = []
    for t in trades[:50]:  # Limiter a 50 trades max
        direction = t.get("direction", "?")
        symbol = t.get("symbol", "?")
        profit = t.get("profit")
        pnl_str = f"{profit:+.2f}" if profit is not None else "en cours"
        opened = t.get("opened_at", "?")[:16] if t.get("opened_at") else "?"
        trades_lines.append(f"  - {symbol} {direction} | Ouvert: {opened} | P&L: {pnl_str}")
    trades_detail = "\n".join(trades_lines) if trades_lines else "Aucun trade aujourd'hui."

    prompt = ANALYSIS_PROMPT.format(
        total_trades=stats.get("total_trades", 0),
        wins=stats.get("wins", 0),
        losses=stats.get("losses", 0),
        win_rate=stats.get("win_rate", 0),
        total_profit=f"{stats.get('total_profit', 0):+.2f}",
        best_trade=f"{stats.get('best_trade', 0):+.2f}",
        worst_trade=f"{stats.get('worst_trade', 0):+.2f}",
        avg_profit=f"{stats.get('avg_profit', 0):+.2f}",
        avg_duration=stats.get("avg_duration", "N/A"),
        avg_confidence=stats.get("avg_confidence", 0),
        symbols_detail=symbols_detail,
        trades_detail=trades_detail,
    )

    logger.info(f"Envoi analyse quotidienne a {settings.ai_provider}/{settings.ai_model}...")

    try:
        client = OpenAI(
            api_key=settings.ai_api_key_resolved,
            base_url=settings.ai_base_url,
        )

        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=[
                {"role": "system", "content": "Tu es un analyste quantitatif expert. Reponds toujours en francais."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.4,
        )

        analysis = response.choices[0].message.content or ""
        logger.info(f"Analyse {settings.ai_provider} recue ({len(analysis)} caracteres)")

        if not analysis.strip():
            logger.warning(f"{settings.ai_provider} a retourne une reponse vide - second essai avec temperature plus elevee")
            response = client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": "Tu es un analyste quantitatif expert. Reponds toujours en francais."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.7,
            )
            analysis = response.choices[0].message.content or ""
            logger.info(f"Second essai DeepSeek: {len(analysis)} caracteres")

        if not analysis.strip():
            return (
                "**Analyse DeepSeek V4 Pro non disponible**\n\n"
                "L'API DeepSeek a retourne une reponse vide a deux reprises. "
                "Voici les donnees brutes pour votre propre analyse:\n\n"
                f"- {stats.get('total_trades', 0)} trades au total\n"
                f"- {stats.get('wins', 0)} gagnants, {stats.get('losses', 0)} perdants\n"
                f"- P&L: {stats.get('total_profit', 0):+.2f} $\n"
                f"- Win rate: {stats.get('win_rate', 0)}%\n"
            )

        return analysis.strip()

    except Exception as e:
        logger.error(f"Echec analyse DeepSeek: {e}")
        return f"_Analyse DeepSeek indisponible: {str(e)[:100]}_"
