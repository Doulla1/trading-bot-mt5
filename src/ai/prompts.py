"""Templates de prompts pour l'IA.

v2.0: prompts separes OCR (GPT-4o-mini) et Decision (DeepSeek V4 Pro)."""


def build_analysis_prompt(symbol, timeframe, indicators, calendar_events,
                          open_positions, account_info) -> str:
    """Prompt legacy pour GPT-4o-mini (fallback)."""
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
Analyse le graphique et les indicateurs. Considere les evenements economiques.
Si une position est deja ouverte, evalue s'il faut la conserver ou la fermer.

Reponds UNIQUEMENT avec un objet JSON:
{{"action": "BUY|SELL|HOLD|CLOSE", "confidence": 0-100, "reasoning": "...", "stop_loss_pips": int, "take_profit_pips": int, "risk_level": "LOW|MEDIUM|HIGH"}}
- stop_loss_pips entre 15 et 50, take_profit_pips >= stop_loss_pips * 1.5"""


def build_decision_prompt(symbol, timeframe, indicators, ocr_data,
                          calendar_events, open_positions, account_info,
                          trade_history, session_context,
                          performance_stats=None) -> str:
    """Prompt complet pour DeepSeek V4 Pro avec tout le contexte (v2.0)."""

    parts = [f"""Tu es un trader institutionnel forex expert. Analyse TOUTES les donnees ci-dessous et prends une decision de trading.

**PAIRE**: {symbol} | **TIMEFRAME**: {timeframe}
**PRIX ACTUEL**: {indicators.get('current_price', 'N/A')}
**DATE/HEURE**: {session_context.get('datetime', 'N/A')}
**SESSION**: {session_context.get('session', 'N/A')}"""]

    # 1. INDICATEURS TECHNIQUES
    parts.append("--- INDICATEURS TECHNIQUES ---")
    parts.append(_format_indicators_v2(indicators))

    # 2. ICHIMOKU
    if indicators.get("ichimoku_cloud_top") is not None:
        parts.append("--- ICHIMOKU KINKO HYO ---")
        parts.append(_format_ichimoku(indicators))

    # 3. PIVOT POINTS
    if indicators.get("pivot_pp") is not None:
        parts.append("--- POINTS PIVOTS ---")
        parts.append(_format_pivots(indicators))

    # 4. OCR (analyse visuelle du chart)
    if ocr_data:
        parts.append("--- ANALYSE VISUELLE DU CHART (OCR) ---")
        parts.append(_format_ocr(ocr_data))

    # 5. PATTERNS CHANDELIERS + STRUCTURE
    parts.append("--- PATTERNS ET STRUCTURE ---")
    patterns = indicators.get("candlestick_patterns", [])
    parts.append(f"Patterns chandeliers: {', '.join(patterns)}")
    structure = indicators.get("market_structure", {})
    parts.append(f"Structure marche: {structure.get('structure', 'indetermine')}")
    if structure.get("last_swing_high"):
        parts.append(f"  Dernier swing high: {structure['last_swing_high']}")
    if structure.get("last_swing_low"):
        parts.append(f"  Dernier swing low: {structure['last_swing_low']}")

    # 6. MULTI-TIMEFRAME
    if indicators.get("h1_trend") is not None:
        parts.append("--- CONTEXTE MULTI-TIMEFRAME ---")
        parts.append(f"H1 Tendance: {indicators['h1_trend']}")
        parts.append(f"H1 RSI: {indicators.get('h1_rsi_14', 'N/A')}")
        parts.append(f"H1 Close: {indicators.get('h1_close', 'N/A')}")

    # 7. REGIME DE MARCHE
    parts.append(f"--- REGIME ---")
    parts.append(f"ADX: {indicators.get('adx_14', 'N/A')} "
                 f"(DI+={indicators.get('di_plus', '?')}, DI-={indicators.get('di_minus', '?')})")
    parts.append(f"Regime: {indicators.get('market_regime', 'N/A')}")

    # 8. CALENDRIER
    parts.append("--- CALENDRIER ECONOMIQUE ---")
    parts.append(_format_calendar(calendar_events))

    # 9. POSITIONS + COMPTE
    parts.append("--- POSITIONS OUVERTES ---")
    parts.append(_format_positions(open_positions, account_info))

    # 10. HISTORIQUE TRADES
    if trade_history:
        parts.append("--- HISTORIQUE RECENT (derniers trades) ---")
        parts.append(_format_trade_history(trade_history))
        if performance_stats:
            parts.append("--- STATISTIQUES DE PERFORMANCE ---")
            parts.append(_format_performance(performance_stats))

    # 11. INSTRUCTIONS
    parts.append(f"""--- DECISION ---
Analyse TOUTES les donnees (technique, Ichimoku, pivots, OCR du chart, patterns, structure, multi-timeframe, regime de marche, calendrier, historique).

Regles:
- CONFIDENCE elevee (>70) uniquement si TOUS les signaux convergent
- Si une news HIGH impact approche (<30 min) -> HOLD systematique
- Si Ichimoku, pivots et structure sont en conflit -> HOLD
- Si ADX < 20 (ranging) -> eviter de trader, preference HOLD
- Eviter d'ouvrir une position juste avant une news HIGH (le bot bloque deja, mais sois prudent)
- SL entre 15 et 50 pips selon ATR et volatilite
- TP >= 1.5x le stop loss

POSITIONS EXISTANTES (regle conservative):
- Si tu as deja une position et que les signaux confirment ta direction -> HOLD (la position est bonne, le trailing/breakeven s'en occupe)
- Si tu as deja une position et que les signaux s'inversent clairement (retournement de tendance) -> CLOSE (le bot fermera et attendra le prochain cycle pour reevaluer)
- Si tu as deja une position et que les signaux sont mixtes -> HOLD (attendre confirmation)
- NE SUGGERE PAS BUY/SELL si une position est deja ouverte (le bot n'ouvrira pas de deuxieme position)

Reponds UNIQUEMENT en JSON:
{{"action": "BUY|SELL|HOLD|CLOSE", "confidence": 0-100, "reasoning": "analyse concise (max 200 mots)", "stop_loss_pips": int, "take_profit_pips": int, "risk_level": "LOW|MEDIUM|HIGH"}}""")

    return "\n".join(parts)


# ============================================================
# Formatteurs enrichis v2.0
# ============================================================

def _format_indicators_v2(ind: dict) -> str:
    """Formateur v3.0: envoie des etats semantiques au lieu de valeurs brutes.
    Les LLMs sont des moteurs de logique semantique, pas des calculateurs mathematiques."""
    lines = []

    # --- RSI: etat semantique ---
    rsi = ind.get('rsi_14')
    if rsi is not None:
        if rsi > 75:
            rsi_state = f"RSI 14: {rsi:.1f} - Zone de SURACHAT (pression acheteuse extreme)"
        elif rsi > 60:
            rsi_state = f"RSI 14: {rsi:.1f} - Tendance haussiere (momentum positif)"
        elif rsi > 40:
            rsi_state = f"RSI 14: {rsi:.1f} - Zone neutre (pas d'extreme)"
        elif rsi > 25:
            rsi_state = f"RSI 14: {rsi:.1f} - Tendance baissiere (momentum negatif)"
        else:
            rsi_state = f"RSI 14: {rsi:.1f} - Zone de SURVENTE (pression vendeuse extreme)"
        lines.append(rsi_state)

    # --- MACD: croisement et zone ---
    macd_line = ind.get('macd_line')
    macd_signal = ind.get('macd_signal')
    macd_hist = ind.get('macd_histogram')
    if macd_line is not None and macd_signal is not None:
        # Relation MACD vs Signal
        if macd_line > macd_signal:
            cross_state = "MACD au-dessus du Signal (momentum haussier)"
        else:
            cross_state = "MACD sous le Signal (momentum baissier)"
        # Zone (positif/negatif)
        if macd_line > 0:
            zone = "zone positive"
        else:
            zone = "zone negative"
        # Histogramme: acceleration ou deceleration
        if macd_hist is not None:
            if macd_hist > 0:
                hist_state = "histogramme haussier (acceleration acheteuse)"
            else:
                hist_state = "histogramme baissier (acceleration vendeuse)"
        else:
            hist_state = ""
        lines.append(f"MACD: {cross_state} en {zone}, {hist_state}")

    # --- Bollinger Bands: position semantique ---
    bb_pos = ind.get('bb_position_pct')
    if bb_pos is not None:
        if bb_pos > 95:
            bb_state = f"Prix SUR LA BANDE SUPERIEURE (surf haussier, possible cassure)"
        elif bb_pos > 70:
            bb_state = f"Prix dans la MOITIE SUPERIEURE des bandes (pression haussiere)"
        elif bb_pos > 30:
            bb_state = f"Prix dans la ZONE MEDIANE des bandes (range)"
        elif bb_pos > 5:
            bb_state = f"Prix dans la MOITIE INFERIEURE des bandes (pression baissiere)"
        else:
            bb_state = f"Prix SUR LA BANDE INFERIEURE (surf baissier, possible cassure)"
        lines.append(f"Bollinger: {bb_state}")

    # --- Moving Averages ---
    sma20 = ind.get('sma_20')
    sma50 = ind.get('sma_50')
    current_price = ind.get('current_price')
    if sma20 is not None and current_price is not None:
        vs_sma20 = "au-dessus" if current_price > sma20 else "sous"
        lines.append(f"SMA20: Prix {vs_sma20} la SMA20 ({sma20:.5f})")
    if sma50 is not None and current_price is not None:
        vs_sma50 = "au-dessus" if current_price > sma50 else "sous"
        lines.append(f"SMA50: Prix {vs_sma50} la SMA50 ({sma50:.5f})")

    ema20 = ind.get('ema_20')
    ema200 = ind.get('ema_200')
    if ema20 is not None:
        lines.append(f"EMA20: {ema20:.5f}")
    if ema200 is not None and current_price is not None:
        vs_ema200 = "au-dessus" if current_price > ema200 else "sous"
        lines.append(f"EMA200: Prix {vs_ema200} l'EMA200 ({ema200:.5f})")

    # --- ATR: volatilite ---
    atr = ind.get('atr_14')
    if atr is not None and current_price is not None:
        atr_pct = (atr / current_price) * 100 if current_price else 0
        if atr_pct > 0.5:
            atr_state = f"ATR 14: {atr:.5f} - VOLATILITE ELEVEE ({atr_pct:.2f}% du prix)"
        elif atr_pct > 0.2:
            atr_state = f"ATR 14: {atr:.5f} - Volatilite moderee ({atr_pct:.2f}% du prix)"
        else:
            atr_state = f"ATR 14: {atr:.5f} - Volatilite faible ({atr_pct:.2f}% du prix)"
        lines.append(atr_state)

    # --- Tendance ---
    trend_ct = ind.get('trend_short', 'N/A')
    trend_mt = ind.get('trend_medium', 'N/A')
    lines.append(f"Tendance CT: {trend_ct}, MT: {trend_mt}")

    # --- Niveaux 24h ---
    high24 = ind.get('high_24h')
    low24 = ind.get('low_24h')
    if high24 is not None and low24 is not None and current_price is not None:
        pct_from_high = ((high24 - current_price) / current_price * 100) if current_price else 0
        pct_from_low = ((current_price - low24) / current_price * 100) if current_price else 0
        lines.append(f"Range 24h: {low24:.5f} - {high24:.5f} (prix a {pct_from_low:.1f}% du bas, {pct_from_high:.1f}% du haut)")

    return "\n".join(lines)


def _format_ichimoku(ind: dict) -> str:
    lines = [
        f"Tenkan: {ind.get('ichimoku_tenkan', '?')}",
        f"Kijun: {ind.get('ichimoku_kijun', '?')}",
        f"Cloud Top: {ind.get('ichimoku_cloud_top', '?')}, Bottom: {ind.get('ichimoku_cloud_bottom', '?')}",
        f"Cloud Couleur: {ind.get('ichimoku_cloud_color', '?')}",
        f"Prix vs Cloud: {ind.get('ichimoku_price_vs_cloud', '?')}",
        f"Tenkan/Kijun Cross: {ind.get('ichimoku_tenkan_kijun_cross', '?')}",
        f"Tendance Ichimoku: {ind.get('ichimoku_trend', '?')}",
    ]
    return "\n".join(lines)


def _format_pivots(ind: dict) -> str:
    lines = [
        f"PP: {ind.get('pivot_pp', '?')}",
        f"R1: {ind.get('pivot_r1', '?')}, R2: {ind.get('pivot_r2', '?')}, R3: {ind.get('pivot_r3', '?')}",
        f"S1: {ind.get('pivot_s1', '?')}, S2: {ind.get('pivot_s2', '?')}, S3: {ind.get('pivot_s3', '?')}",
        f"Support le plus proche: {ind.get('pivot_nearest_support', '?')}",
        f"Resistance la plus proche: {ind.get('pivot_nearest_resistance', '?')}",
    ]
    return "\n".join(lines)


def _format_ocr(ocr: dict) -> str:
    lines = [
        f"Phase de marche: {ocr.get('market_phase', '?')}",
        f"Patterns chart: {ocr.get('chart_patterns', '?')}",
        f"Supports visuels: {ocr.get('support_levels', '?')}",
        f"Resistances visuelles: {ocr.get('resistance_levels', '?')}",
        f"Trendlines: {ocr.get('trendlines', '?')}",
        f"Chandeliers visuels: {ocr.get('candlestick_visual', '?')}",
        f"Price action: {ocr.get('price_action_notes', '?')}",
    ]
    return "\n".join(lines)


def _format_trade_history(history: list) -> str:
    lines = []
    for t in history[:10]:
        profit_val = t.get("profit")
        if profit_val is None:
            profit_str = "N/A"
        elif profit_val > 0:
            profit_str = f"+{profit_val:.1f}"
        else:
            profit_str = str(profit_val)
        lines.append(
            f"- {t.get('direction', '?')} {t.get('symbol', '?')} | "
            f"Confiance: {t.get('confidence', '?')}% | "
            f"Profit: {profit_str} | "
            f"Date: {t.get('opened_at', '?')[:10]}"
        )
    return "\n".join(lines) if lines else "Aucun historique."

def _format_performance(stats: dict) -> str:
    """Formate les statistiques de performance (v2.1)."""
    lines = [
        f"Total trades fermes: {stats.get('total_closed', 0)}",
        f"Gagnes: {stats.get('wins', 0)}, Perdus: {stats.get('losses', 0)}",
        f"Win rate: {stats.get('win_rate', 0)}%",
        f"Profit total: {stats.get('total_profit', 0)}",
        f"Confiance moyenne: {stats.get('avg_confidence', 0)}%",
    ]
    return "\n".join(lines)

def _format_indicators(ind: dict) -> str:
    """Formateur legacy."""
    lines = []
    for key, label in [
        ("rsi_14", "RSI 14"), ("sma_20", "SMA 20"), ("sma_50", "SMA 50"),
        ("atr_14", "ATR 14"), ("bb_position_pct", "BB Position"),
    ]:
        if ind.get(key) is not None:
            lines.append(f"- {label}: {ind[key]}")
    lines.append(f"- Tendance CT: {ind.get('trend_short', 'N/A')}")
    lines.append(f"- Tendance MT: {ind.get('trend_medium', 'N/A')}")
    return "\n".join(lines)


def _format_calendar(events: list) -> str:
    if not events:
        return "Aucun evenement majeur prevu."
    lines = []
    for ev in events[:15]:
        impact = "HIGH" if ev.get("impact") == "high" else "MED" if ev.get("impact") == "medium" else "LOW"
        date_info = ev.get("date", "")
        time_info = ev.get("time", "")
        lines.append(
            f"- [{impact}] {date_info} {time_info} | {ev.get('currency', '')} | "
            f"{ev.get('event', '')}"
        )
    return "\n".join(lines)


def _format_positions(positions: list, account: dict) -> str:
    if not positions:
        return "Aucune position ouverte."
    lines = [f"Balance: {account.get('balance', 'N/A')}, Equity: {account.get('equity', 'N/A')}"]
    for p in positions:
        pnl = p.get("profit", 0)
        pos_type = "BUY" if p.get("type") == 0 else "SELL"
        lines.append(
            f"- Ticket {p.get('ticket')}: {pos_type} {p.get('volume')} lots @ "
            f"{p.get('price_open')} | P&L: {pnl:.2f} | "
            f"SL: {p.get('sl', 'N/A')} | TP: {p.get('tp', 'N/A')}"
        )
    return "\n".join(lines)

