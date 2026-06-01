"""Templates de prompts pour l'IA."""


def build_analysis_prompt(symbol, timeframe, indicators, calendar_events, open_positions, account_info) -> str:
    """Construit le prompt complet d'analyse pour GPT-4o-mini."""

    ind_text = _format_indicators(indicators)
    cal_text = _format_calendar(calendar_events)
    pos_text = _format_positions(open_positions, account_info)

    return f"""Tu es un analyste de trading forex expert. Analyse le graphique fourni en capture d'ecran et les donnees ci-dessous pour prendre une decision de trading.

**INFORMATIONS DE TRADING**
- Paire: {symbol}
- Timeframe: {timeframe}
- Prix actuel: {indicators.get('current_price', 'N/A')}

**INDICATEURS TECHNIQUES**
{ind_text}

**CALENDRIER ECONOMIQUE (prochaines 24h)**
{cal_text}

**POSITIONS OUVERTES**
{pos_text}

**INSTRUCTIONS D'ANALYSE**
Analyse le graphique (support/resistance, patterns, chandeliers, tendance visuelle) ET les indicateurs.
Considere les evenements economiques a venir qui pourraient impacter {symbol}.
Si une position est deja ouverte, evalue s'il faut la conserver ou la fermer.

Reponds UNIQUEMENT avec un objet JSON au format suivant (pas de markdown, pas de texte avant/apres) :

{{
  "action": "BUY" | "SELL" | "HOLD" | "CLOSE",
  "confidence": 0-100,
  "reasoning": "Analyse courte (max 150 mots) expliquant la decision",
  "stop_loss_pips": nombre entier de pips pour le stop loss,
  "take_profit_pips": nombre entier de pips pour le take profit,
  "risk_level": "LOW" | "MEDIUM" | "HIGH"
}}

- "CLOSE" uniquement si une position est ouverte et doit etre fermee
- confidence >= 70 pour executer BUY/SELL
- stop_loss_pips entre 15 et 50 selon la volatilite
- take_profit_pips >= stop_loss_pips * 1.5
"""


def _format_indicators(ind: dict) -> str:
    lines = []
    if ind.get("rsi_14") is not None:
        lines.append(f"- RSI (14): {ind['rsi_14']}")
    if ind.get("macd_line") is not None:
        lines.append(f"- MACD Line: {ind['macd_line']}, Signal: {ind['macd_signal']}, Histo: {ind['macd_histogram']}")
    if ind.get("sma_20") is not None:
        lines.append(f"- SMA 20: {ind['sma_20']}, SMA 50: {ind.get('sma_50', 'N/A')}")
    if ind.get("bb_upper") is not None:
        lines.append(f"- Bollinger: Upper={ind['bb_upper']}, Lower={ind['bb_lower']}, Position={ind.get('bb_position_pct', 'N/A')}%")
    if ind.get("atr_14") is not None:
        lines.append(f"- ATR (14): {ind['atr_14']}")
    lines.append(f"- Tendance court terme: {ind.get('trend_short', 'N/A')}")
    lines.append(f"- Tendance moyen terme: {ind.get('trend_medium', 'N/A')}")
    lines.append(f"- High 24h: {ind.get('high_24h', 'N/A')}, Low 24h: {ind.get('low_24h', 'N/A')}")
    return "\n".join(lines)


def _format_calendar(events: list) -> str:
    if not events:
        return "Aucun evenement majeur prevu."
    lines = []
    for ev in events[:10]:
        impact = "HIGH" if ev.get("impact") == "high" else "MED" if ev.get("impact") == "medium" else "LOW"
        lines.append(f"- [{impact}] {ev.get('time', '')} | {ev.get('currency', '')} | {ev.get('event', '')} | Prev: {ev.get('previous', 'N/A')} | Forecast: {ev.get('forecast', 'N/A')}")
    return "\n".join(lines)


def _format_positions(positions: list, account: dict) -> str:
    if not positions:
        return "Aucune position ouverte."
    lines = []
    for p in positions:
        pnl = p.get("profit", 0)
        pos_type = "BUY" if p.get("type") == 0 else "SELL"
        lines.append(f"- Ticket {p.get('ticket')}: {pos_type} {p.get('volume')} lots @ {p.get('price_open')} | P&L: {pnl:.2f} | SL: {p.get('sl', 'N/A')} | TP: {p.get('tp', 'N/A')}")
    return "\n".join(lines)
