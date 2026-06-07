"""Templates of prompts for the AI.

v2.0: separate prompts for OCR (GPT-4o-mini) and Decision (DeepSeek V4 Pro)."""

# Configuration of Stop Loss (SL) limits by symbol (in pips) for display in the prompt.
# Allows the AI to propose realistic SL/TP values adapted to each asset class.
SL_LIMITS_CONFIG = {
    "XAUUSD": {"min": 150, "max": 500, "note": "(1 pip = 0.1 USD price change, e.g., 150 pips = 15.0 USD)"},
    "EURUSD": {"min": 15,  "max": 50,  "note": "(1 pip = 0.0001 price change)"},
    "GBPUSD": {"min": 25,  "max": 70,  "note": "(1 pip = 0.0001 price change)"},
    "AUDUSD": {"min": 15,  "max": 50,  "note": "(1 pip = 0.0001 price change)"},
    "USDJPY": {"min": 30,  "max": 90,  "note": "(1 pip = 0.01 price change)"},
    "USDCHF": {"min": 15,  "max": 50,  "note": "(1 pip = 0.0001 price change)"},
    "EURGBP": {"min": 15,  "max": 50,  "note": "(1 pip = 0.0001 price change)"},
    "EURJPY": {"min": 25,  "max": 80,  "note": "(1 pip = 0.01 price change)"},
    "GBPJPY": {"min": 35,  "max": 100, "note": "(1 pip = 0.01 price change)"},
}


def _translate_trend(val: str) -> str:
    if not val or not isinstance(val, str):
        return val
    mapping = {
        "haussier": "bullish",
        "baissier": "bearish",
        "haussiere": "bullish",
        "baissiere": "bearish",
        "plate": "flat",
        "neutre": "neutral",
        "indetermine": "undetermined",
        "indeterminee": "undetermined",
        "au-dessus": "above",
        "dessous": "below",
        "dedans": "inside",
        "aucun": "none",
        "vert": "green",
        "rouge": "red"
    }
    return mapping.get(val.lower(), val)


def build_analysis_prompt(symbol, timeframe, indicators, calendar_events,
                          open_positions, account_info) -> str:
    """Legacy prompt for GPT-4o-mini (fallback)."""
    ind_text = _format_indicators(indicators)
    cal_text = _format_calendar(calendar_events)
    pos_text = _format_positions(open_positions, account_info)

    sl_cfg = SL_LIMITS_CONFIG.get(symbol, {"min": 15, "max": 50, "note": ""})
    min_sl = sl_cfg["min"]
    max_sl = sl_cfg["max"]
    note_sl = sl_cfg["note"]

    return f"""You are an expert forex trading analyst. Analyze the provided chart screenshot and the data below to make a trading decision.

**TRADING INFORMATION**
- Symbol: {symbol}
- Timeframe: {timeframe}
- Current Price: {indicators.get('current_price', 'N/A')}

**TECHNICAL INDICATORS**
{ind_text}

**ECONOMIC CALENDAR (Next 24h)**
{cal_text}

**OPEN POSITIONS**
{pos_text}

**ANALYSIS INSTRUCTIONS**
Analyze the chart and indicators. Consider economic events.
If a position is already open, evaluate whether to hold or close it.

Respond ONLY with a JSON object:
{{"action": "BUY|SELL|HOLD|CLOSE", "confidence": 0-100, "reasoning": "...", "stop_loss_pips": int, "take_profit_pips": int, "risk_level": "LOW|MEDIUM|HIGH"}}
- stop_loss_pips must be between {min_sl} and {max_sl} pips {note_sl}, take_profit_pips >= stop_loss_pips * 1.5
- Write the 'reasoning' field entirely in French."""


def build_decision_prompt(symbol, timeframe, indicators, ocr_data,
                          calendar_events, open_positions, account_info,
                          trade_history, session_context,
                          performance_stats=None) -> str:
    """Full prompt for DeepSeek V4 Pro with all context (v2.0)."""

    parts = [f"""You are an expert institutional forex trader. Analyze ALL the data below and make a trading decision.

**SYMBOL**: {symbol} | **TIMEFRAME**: {timeframe}
**CURRENT PRICE**: {indicators.get('current_price', 'N/A')}
**DATE/TIME**: {session_context.get('datetime', 'N/A')}
**SESSION**: {session_context.get('session', 'N/A')}"""]

    # 1. TECHNICAL INDICATORS
    parts.append("--- TECHNICAL INDICATORS ---")
    parts.append(_format_indicators_v2(indicators))

    # 2. ICHIMOKU
    if indicators.get("ichimoku_cloud_top") is not None:
        parts.append("--- ICHIMOKU KINKO HYO ---")
        parts.append(_format_ichimoku(indicators))

    # 3. PIVOT POINTS
    if indicators.get("pivot_pp") is not None:
        parts.append("--- PIVOT POINTS ---")
        parts.append(_format_pivots(indicators))

    # 4. OCR (visual analysis of the chart)
    if ocr_data:
        parts.append("--- CHART VISUAL ANALYSIS (OCR) ---")
        parts.append(_format_ocr(ocr_data))

    # 5. CANDLESTICK PATTERNS + STRUCTURE
    parts.append("--- PATTERNS AND STRUCTURE ---")
    patterns = indicators.get("candlestick_patterns", [])
    parts.append(f"Candlestick patterns: {', '.join(patterns)}")
    structure = indicators.get("market_structure", {})
    parts.append(f"Market structure: {_translate_trend(structure.get('structure', 'undetermined'))}")
    if structure.get("last_swing_high"):
        dist_sh = indicators.get("dist_swing_high_atr")
        dist_sh_str = f" (Distance: +{dist_sh} ATR)" if dist_sh is not None else ""
        parts.append(f"  Last swing high: {structure['last_swing_high']}{dist_sh_str}")
    if structure.get("last_swing_low"):
        dist_sl = indicators.get("dist_swing_low_atr")
        dist_sl_str = f" (Distance: +{dist_sl} ATR)" if dist_sl is not None else ""
        parts.append(f"  Last swing low: {structure['last_swing_low']}{dist_sl_str}")

    # 6. MULTI-TIMEFRAME
    if indicators.get("h1_trend") is not None or indicators.get("h4_trend") is not None:
        parts.append("--- MULTI-TIMEFRAME CONTEXT ---")
        if indicators.get("h1_trend"):
            parts.append(f"H1 Trend: {_translate_trend(indicators['h1_trend'])}")
        if indicators.get("h4_trend"):
            parts.append(f"H4 Trend: {_translate_trend(indicators['h4_trend'])}")
        parts.append(f"H1 RSI: {indicators.get('h1_rsi_14', 'N/A')} | H1 Close: {indicators.get('h1_close', 'N/A')}")
        if indicators.get("h4_trend"):
            parts.append(f"H4 RSI: {indicators.get('h4_rsi_14', 'N/A')} | H4 Close: {indicators.get('h4_close', 'N/A')}")

    # 7. MARKET REGIME
    parts.append(f"--- REGIME ---")
    parts.append(f"ADX: {indicators.get('adx_14', 'N/A')} "
                 f"(DI+={indicators.get('di_plus', '?')}, DI-={indicators.get('di_minus', '?')})")
    parts.append(f"Regime: {_translate_trend(indicators.get('market_regime', 'N/A'))}")

    # 8. CALENDAR
    parts.append("--- ECONOMIC CALENDAR ---")
    parts.append(_format_calendar(calendar_events))

    # 9. POSITIONS + ACCOUNT
    parts.append("--- OPEN POSITIONS ---")
    parts.append(_format_positions(open_positions, account_info))

    # 10. TRADE HISTORY
    if trade_history:
        parts.append("--- RECENT HISTORY (last trades) ---")
        parts.append(_format_trade_history(trade_history))
        if performance_stats:
            parts.append("--- PERFORMANCE STATISTICS ---")
            parts.append(_format_performance(performance_stats))

    # 11. INSTRUCTIONS
    sl_cfg = SL_LIMITS_CONFIG.get(symbol, {"min": 15, "max": 50, "note": ""})
    min_sl = sl_cfg["min"]
    max_sl = sl_cfg["max"]
    note_sl = sl_cfg["note"]

    parts.append(f"""--- DECISION ---
Analyze ALL data (technical, Ichimoku, pivots, volume, structure, multi-timeframe, market regime, calendar, history).

General rules:
- High CONFIDENCE (>70) only if ALL signals converge.
- If a HIGH impact news event is approaching (<30 min) -> systematic HOLD.
- If Ichimoku, pivots, and structure are in conflict -> HOLD.
- If ADX < 20 (ranging) -> avoid trading, preference HOLD.
- Avoid opening a position just before HIGH impact news (the bot already blocks it, but be careful).

RULES FOR PLACING STOP LOSS (SL) AND TAKE PROFIT (TP):
- The Stop Loss (SL) MUST be placed technically and realistically as a distance in pips:
  * For {symbol}, the SL must be between {min_sl} and {max_sl} pips {note_sl} according to volatility (ATR).
  * BUY: Place the SL just below the last swing low (structural support) or below the bottom of the Ichimoku cloud (dynamic support).
  * SELL: Place the SL just above the last swing high (structural resistance) or above the top of the Ichimoku cloud (dynamic resistance).
- The Take Profit (TP) MUST respect a minimum ratio and be placed realistically (securing gains):
  * The TP must be at least greater than 1.5x the Stop Loss (TP >= 1.5 * SL).
  * SECURING GAINS: Place the TP intelligently relative to chart obstacles. For a BUY, place it 1 to 2 pips BELOW the last swing high (or below the Pivot R1/R2/R3 resistance or below the 24h High) to guarantee execution before a rejection. For a SELL, place it 1 to 2 pips ABOVE the last swing low (or above Pivot S1/S2/S3 support or above the 24h Low).

EXISTING POSITIONS (conservative rule):
- If you already have a position and signals confirm your direction -> HOLD (the position is good, trailing/breakeven will handle it).
- If you already have a position and signals clearly reverse (trend reversal) -> CLOSE (the bot will close and wait for the next cycle to re-evaluate).
- If you already have a position and signals are mixed -> HOLD (wait for confirmation).
- DO NOT suggest BUY/SELL if a position is already open (the bot will not open a second position).

Respond ONLY in JSON format:
{{"action": "BUY|SELL|HOLD|CLOSE", "confidence": 0-100, "reasoning": "analyse concise en français (max 200 mots)", "stop_loss_pips": int, "take_profit_pips": int, "risk_level": "LOW|MEDIUM|HIGH"}}
Ensure the 'reasoning' field is written entirely in French.""")

    return "\n".join(parts)


# ============================================================
# Enriched Formatters v2.0
# ============================================================

def _format_indicators_v2(ind: dict) -> str:
    """Formatter v3.0: sends semantic states instead of raw values.
    LLMs are semantic logic engines, not mathematical calculators."""
    lines = []

    # --- RSI: semantic state ---
    rsi = ind.get('rsi_14')
    if rsi is not None:
        if rsi > 75:
            rsi_state = f"RSI 14: {rsi:.1f} - OVERBOUGHT zone (extreme buying pressure)"
        elif rsi > 60:
            rsi_state = f"RSI 14: {rsi:.1f} - Bullish trend (positive momentum)"
        elif rsi > 40:
            rsi_state = f"RSI 14: {rsi:.1f} - Neutral zone (no extreme)"
        elif rsi > 25:
            rsi_state = f"RSI 14: {rsi:.1f} - Bearish trend (negative momentum)"
        else:
            rsi_state = f"RSI 14: {rsi:.1f} - OVERSOLD zone (extreme selling pressure)"
        lines.append(rsi_state)

    # --- MACD: crossover and zone ---
    macd_line = ind.get('macd_line')
    macd_signal = ind.get('macd_signal')
    macd_hist = ind.get('macd_histogram')
    if macd_line is not None and macd_signal is not None:
        # Relation MACD vs Signal
        if macd_line > macd_signal:
            cross_state = "MACD above Signal (bullish momentum)"
        else:
            cross_state = "MACD below Signal (bearish momentum)"
        # Zone (positive/negative)
        if macd_line > 0:
            zone = "positive zone"
        else:
            zone = "negative zone"
        # Histogram: acceleration or deceleration
        if macd_hist is not None:
            if macd_hist > 0:
                hist_state = "bullish histogram (buying acceleration)"
            else:
                hist_state = "bearish histogram (selling acceleration)"
        else:
            hist_state = ""
        lines.append(f"MACD: {cross_state} in {zone}, {hist_state}")

    # --- Bollinger Bands: semantic position ---
    bb_pos = ind.get('bb_position_pct')
    if bb_pos is not None:
        if bb_pos > 95:
            bb_state = f"Price ON UPPER BAND (bullish ride, possible breakout)"
        elif bb_pos > 70:
            bb_state = f"Price in UPPER HALF of bands (bullish pressure)"
        elif bb_pos > 30:
            bb_state = f"Price in MIDDLE ZONE of bands (range)"
        elif bb_pos > 5:
            bb_state = f"Price in LOWER HALF of bands (bearish pressure)"
        else:
            bb_state = f"Price ON LOWER BAND (bearish ride, possible breakout)"
        
        # Relative distances in ATR
        dist_upper = ind.get('dist_bb_upper_atr')
        dist_lower = ind.get('dist_bb_lower_atr')
        dist_str = []
        if dist_upper is not None:
            dist_str.append(f"Upper dist: {dist_upper} ATR")
        if dist_lower is not None:
            dist_str.append(f"Lower dist: {dist_lower} ATR")
        bb_dist_info = f" ({', '.join(dist_str)})" if dist_str else ""
        lines.append(f"Bollinger: {bb_state}{bb_dist_info}")

    # --- Moving Averages ---
    current_price = ind.get('current_price')
    ema20 = ind.get('ema_20')
    ema200 = ind.get('ema_200')
    ema20_slope = ind.get('ema_20_slope')
    ema200_slope = ind.get('ema_200_slope')
    dist_ema20 = ind.get('dist_ema20_atr')
    dist_ema200 = ind.get('dist_ema200_atr')
    
    if ema20 is not None and current_price is not None:
        vs_ema20 = "above" if current_price > ema20 else "below"
        ema20_str = f"EMA20: Price {vs_ema20} EMA20 ({ema20:.5f})"
        if dist_ema20 is not None:
            sign = "+" if dist_ema20 >= 0 else ""
            ema20_str += f" | Dist: {sign}{dist_ema20} ATR"
        if ema20_slope:
            ema20_str += f" | Slope: {_translate_trend(ema20_slope)}"
        lines.append(ema20_str)
        
    if ema200 is not None and current_price is not None:
        vs_ema200 = "above" if current_price > ema200 else "below"
        ema200_str = f"EMA200: Price {vs_ema200} EMA200 ({ema200:.5f})"
        if dist_ema200 is not None:
            sign = "+" if dist_ema200 >= 0 else ""
            ema200_str += f" | Dist: {sign}{dist_ema200} ATR"
        if ema200_slope:
            ema200_str += f" | Slope: {_translate_trend(ema200_slope)}"
        lines.append(ema200_str)

    # --- ATR: volatility ---
    atr = ind.get('atr_14')
    if atr is not None and current_price is not None:
        atr_pct = (atr / current_price) * 100 if current_price else 0
        if atr_pct > 0.5:
            atr_state = f"ATR 14: {atr:.5f} - HIGH VOLATILITY ({atr_pct:.2f}% of price)"
        elif atr_pct > 0.2:
            atr_state = f"ATR 14: {atr:.5f} - Moderate volatility ({atr_pct:.2f}% of price)"
        else:
            atr_state = f"ATR 14: {atr:.5f} - Low volatility ({atr_pct:.2f}% of price)"
        lines.append(atr_state)

    # --- Trend ---
    trend_ct = _translate_trend(ind.get('trend_short', 'N/A'))
    trend_mt = _translate_trend(ind.get('trend_medium', 'N/A'))
    lines.append(f"ST Trend: {trend_ct}, MT Trend: {trend_mt}")

    # --- 24h Levels ---
    high24 = ind.get('high_24h')
    low24 = ind.get('low_24h')
    if high24 is not None and low24 is not None and current_price is not None:
        pct_from_high = ((high24 - current_price) / current_price * 100) if current_price else 0
        pct_from_low = ((current_price - low24) / current_price * 100) if current_price else 0
        lines.append(f"24h Range: {low24:.5f} - {high24:.5f} (price is {pct_from_low:.1f}% from low, {pct_from_high:.1f}% from high)")

    # --- Spread ---
    spread = ind.get('spread')
    spread_atr = ind.get('spread_atr_pct')
    if spread is not None:
        spread_str = f"Spread: {spread:.1f} pips"
        if spread_atr is not None:
            spread_str += f" ({spread_atr}% of ATR 14)"
        lines.append(spread_str)

    # --- Volume & VWAP ---
    vol_pct = ind.get('volume_anomaly_pct')
    if vol_pct is not None:
        if vol_pct > 200:
            lines.append(f"Volume: MAJOR ANOMALY ({vol_pct:.0f}% of average) - Strong participation")
        elif vol_pct > 130:
            lines.append(f"Volume: Active ({vol_pct:.0f}% of average)")
        else:
            lines.append(f"Volume: Normal/Low ({vol_pct:.0f}% of average)")

    vwap = ind.get('daily_vwap')
    if vwap is not None and current_price is not None:
        vs_vwap = "above" if current_price > vwap else "below"
        lines.append(f"VWAP: Price {vs_vwap} Daily VWAP ({vwap:.5f})")

    return "\n".join(lines)


def _format_ichimoku(ind: dict) -> str:
    dist_top = ind.get('dist_ichimoku_cloud_top_atr')
    dist_bottom = ind.get('dist_ichimoku_cloud_bottom_atr')
    cloud_str = f"Cloud Top: {ind.get('ichimoku_cloud_top', '?')}, Bottom: {ind.get('ichimoku_cloud_bottom', '?')}"
    if dist_top is not None and dist_bottom is not None:
        sign_top = "+" if dist_top >= 0 else ""
        sign_bottom = "+" if dist_bottom >= 0 else ""
        cloud_str += f" | Distances: Top={sign_top}{dist_top} ATR, Bottom={sign_bottom}{dist_bottom} ATR"
        
    lines = [
        f"Tenkan: {ind.get('ichimoku_tenkan', '?')}",
        f"Kijun: {ind.get('ichimoku_kijun', '?')}",
        cloud_str,
        f"Cloud Color: {_translate_trend(ind.get('ichimoku_cloud_color', '?'))}",
        f"Price vs Cloud: {_translate_trend(ind.get('ichimoku_price_vs_cloud', '?'))}",
        f"Tenkan/Kijun Cross: {_translate_trend(ind.get('ichimoku_tenkan_kijun_cross', '?'))}",
        f"Ichimoku Trend: {_translate_trend(ind.get('ichimoku_trend', '?'))}",
    ]
    return "\n".join(lines)


def _format_pivots(ind: dict) -> str:
    dist_support = ind.get('dist_pivot_support_atr')
    dist_resistance = ind.get('dist_pivot_resistance_atr')
    
    support_str = f"Nearest Support: {ind.get('pivot_nearest_support', '?')}"
    if dist_support is not None:
        support_str += f" | Dist: +{dist_support} ATR"
        
    resistance_str = f"Nearest Resistance: {ind.get('pivot_nearest_resistance', '?')}"
    if dist_resistance is not None:
        resistance_str += f" | Dist: +{dist_resistance} ATR"
        
    lines = [
        f"PP: {ind.get('pivot_pp', '?')}",
        f"R1: {ind.get('pivot_r1', '?')}, R2: {ind.get('pivot_r2', '?')}, R3: {ind.get('pivot_r3', '?')}",
        f"S1: {ind.get('pivot_s1', '?')}, S2: {ind.get('pivot_s2', '?')}, S3: {ind.get('pivot_s3', '?')}",
        support_str,
        resistance_str,
    ]
    return "\n".join(lines)


def _format_ocr(ocr: dict) -> str:
    lines = [
        f"Market phase: {ocr.get('market_phase', '?')}",
        f"Chart patterns: {ocr.get('chart_patterns', '?')}",
        f"Visual supports: {ocr.get('support_levels', '?')}",
        f"Visual resistances: {ocr.get('resistance_levels', '?')}",
        f"Trendlines: {ocr.get('trendlines', '?')}",
        f"Visual candlesticks: {ocr.get('candlestick_visual', '?')}",
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
            f"Confidence: {t.get('confidence', '?')}% | "
            f"Profit: {profit_str} | "
            f"Date: {t.get('opened_at', '?')[:10]}"
        )
    return "\n".join(lines) if lines else "No history."


def _format_performance(stats: dict) -> str:
    """Formats performance stats (v2.1)."""
    lines = [
        f"Total closed trades: {stats.get('total_closed', 0)}",
        f"Wins: {stats.get('wins', 0)}, Losses: {stats.get('losses', 0)}",
        f"Win rate: {stats.get('win_rate', 0)}%",
        f"Total profit: {stats.get('total_profit', 0)}",
        f"Average confidence: {stats.get('avg_confidence', 0)}%",
    ]
    return "\n".join(lines)


def _format_indicators(ind: dict) -> str:
    """Legacy formatter."""
    lines = []
    for key, label in [
        ("rsi_14", "RSI 14"), ("ema_20", "EMA 20"), ("ema_200", "EMA 200"),
        ("atr_14", "ATR 14"), ("bb_position_pct", "BB Position"),
    ]:
        if ind.get(key) is not None:
            lines.append(f"- {label}: {ind[key]}")
    lines.append(f"- ST Trend: {_translate_trend(ind.get('trend_short', 'N/A'))}")
    lines.append(f"- MT Trend: {_translate_trend(ind.get('trend_medium', 'N/A'))}")
    return "\n".join(lines)


def _format_calendar(events: list) -> str:
    if not events:
        return "No major events scheduled."
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
        return "No open positions."
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
