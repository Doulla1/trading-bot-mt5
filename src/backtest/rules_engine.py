"""
Phase 2 - Deterministic multi-signal scoring engine.
Replaces the AI layer (OCR + DeepSeek) with a weighted scoring system.

Takes the same indicator dictionary produced by src/mt5/indicators.compute_all()
and outputs a decision in the same JSON format as DeepSeek.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ============================================================
# Default signal weights
# ============================================================

DEFAULT_WEIGHTS: dict[str, int] = {
    # Trend signals
    "price_above_sma20": 10,
    "price_above_sma50": 5,
    "price_above_cloud": 15,
    "price_below_cloud": -15,
    # Momentum signals
    "rsi_oversold": 15,
    "rsi_overbought": -15,
    "macd_above_signal": 10,
    "macd_histogram_rising": 5,
    # Strength signals
    "adx_di_plus_strong": 10,
    "adx_di_minus_strong": -10,
    # Volatility / Bollinger
    "bb_near_lower": 10,
    "bb_near_upper": -10,
    # Pivot points
    "near_support": 10,
    "near_resistance": -10,
    # Candlestick patterns
    "bullish_pattern": 15,
    "bearish_pattern": -15,
    # Market structure
    "higher_high_higher_low": 10,
    "lower_high_lower_low": -10,
    # Multi-timeframe confluence
    "h1_trend_bullish": 5,
    "h1_trend_bearish": -5,
}


# ============================================================
# Candlestick pattern sets
# ============================================================

BULLISH_PATTERNS: set[str] = {
    "hammer", "bullish_engulfing", "morning_star",
    "piercing_line", "three_white_soldiers",
}

BEARISH_PATTERNS: set[str] = {
    "shooting_star", "bearish_engulfing", "evening_star",
    "dark_cloud_cover", "hanging_man", "three_black_crows",
}


# ============================================================
# RuleEngine
# ============================================================

class RuleEngine:
    """Deterministic trading signal scorer using weighted technical indicators."""

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        buy_threshold: int = 25,
        sell_threshold: int = 25,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
        point: float | None = None,
    ) -> None:
        self.weights = dict(DEFAULT_WEIGHTS) if weights is None else dict(weights)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self._point = point  # None -> auto-detect from current_price

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    @staticmethod
    def _detect_point(price: float) -> float:
        """Auto-detect the point size (pip / 10) from the current price."""
        if price <= 0:
            return 0.00001
        if price >= 100:
            return 0.001   # JPY pairs
        if price >= 1:
            return 0.0001  # most majors
        return 0.00001     # low-price pairs (XAGUSD etc.)

    # --------------------------------------------------------
    # Main evaluation
    # --------------------------------------------------------

    def evaluate(self, indicators: dict[str, Any]) -> dict[str, Any]:
        """Score indicators and produce a trading decision.

        Args:
            indicators: Output dict from indicators.compute_all().

        Returns:
            Decision dict matching the DeepSeek AI output format.
        """
        bullish_score = 0
        bearish_score = 0
        reasons: list[str] = []
        w = self.weights

        # ---- Trend: SMA20 (trend_short) ----
        trend_short = indicators.get("trend_short", "")
        if trend_short == "haussier":
            bullish_score += w["price_above_sma20"]
            reasons.append(f"SMA20 haussier (+{w['price_above_sma20']})")
        else:
            bearish_score += w["price_above_sma20"]
            reasons.append(f"SMA20 baissier (+{w['price_above_sma20']} SELL)")

        # ---- Trend: SMA50 (trend_medium) ----
        trend_medium = indicators.get("trend_medium", "")
        if trend_medium == "haussier":
            bullish_score += w["price_above_sma50"]
            reasons.append(f"SMA50 haussier (+{w['price_above_sma50']})")
        elif trend_medium == "baissier":
            bearish_score += w["price_above_sma50"]
            reasons.append(f"SMA50 baissier (+{w['price_above_sma50']} SELL)")

        # ---- Ichimoku cloud ----
        ichimoku_trend = indicators.get("ichimoku_trend", "neutre")
        if ichimoku_trend == "haussier":
            bullish_score += w["price_above_cloud"]
            reasons.append(f"Ichimoku haussier (+{w['price_above_cloud']})")
        elif ichimoku_trend == "baissier":
            val = abs(w["price_below_cloud"])
            bearish_score += val
            reasons.append(f"Ichimoku baissier (+{val} SELL)")

        # ---- RSI ----
        rsi = indicators.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                bullish_score += w["rsi_oversold"]
                reasons.append(f"RSI survendu ({rsi:.0f}) (+{w['rsi_oversold']})")
            elif rsi > 70:
                val = abs(w["rsi_overbought"])
                bearish_score += val
                reasons.append(f"RSI surachete ({rsi:.0f}) (+{val} SELL)")

        # ---- MACD ----
        macd_line = indicators.get("macd_line")
        macd_signal = indicators.get("macd_signal")
        macd_hist = indicators.get("macd_histogram")
        if macd_line is not None and macd_signal is not None:
            if macd_line > macd_signal:
                bullish_score += w["macd_above_signal"]
                reasons.append(f"MACD > signal (+{w['macd_above_signal']})")
            else:
                bearish_score += w["macd_above_signal"]
                reasons.append(f"MACD < signal (+{w['macd_above_signal']} SELL)")

            if macd_hist is not None and macd_hist > 0:
                bullish_score += w["macd_histogram_rising"]
                reasons.append(f"MACD histogram positif (+{w['macd_histogram_rising']})")
            elif macd_hist is not None and macd_hist < 0:
                bearish_score += w["macd_histogram_rising"]
                reasons.append(f"MACD histogram negatif (+{w['macd_histogram_rising']} SELL)")

        # ---- ADX / DI ----
        adx = indicators.get("adx_14")
        di_plus = indicators.get("di_plus")
        di_minus = indicators.get("di_minus")
        if adx is not None and adx >= 25:
            if di_plus is not None and di_minus is not None:
                if di_plus > di_minus:
                    bullish_score += w["adx_di_plus_strong"]
                    reasons.append(f"ADX trending, DI+ domine (+{w['adx_di_plus_strong']})")
                else:
                    val = abs(w["adx_di_minus_strong"])
                    bearish_score += val
                    reasons.append(f"ADX trending, DI- domine (+{val} SELL)")

        # ---- Bollinger Bands ----
        bb_pos = indicators.get("bb_position_pct")
        if bb_pos is not None:
            if bb_pos < 20:
                bullish_score += w["bb_near_lower"]
                reasons.append(f"BB proche bande inf ({bb_pos:.0f}%) (+{w['bb_near_lower']})")
            elif bb_pos > 80:
                val = abs(w["bb_near_upper"])
                bearish_score += val
                reasons.append(f"BB proche bande sup ({bb_pos:.0f}%) (+{val} SELL)")

        # ---- Pivot points ----
        current_price = indicators.get("current_price")
        if current_price is not None:
            s1 = indicators.get("pivot_s1")
            s2 = indicators.get("pivot_s2")
            r1 = indicators.get("pivot_r1")
            r2 = indicators.get("pivot_r2")
            if s1 is not None and s2 is not None:
                dist_to_s1 = abs(current_price - s1)
                dist_to_s2 = abs(current_price - s2)
                if dist_to_s1 < dist_to_s2 and dist_to_s1 / current_price < 0.003:
                    bullish_score += w["near_support"]
                    reasons.append(f"Proche S1 (+{w['near_support']})")
                elif dist_to_s2 / current_price < 0.003:
                    bullish_score += w["near_support"]
                    reasons.append(f"Proche S2 (+{w['near_support']})")
            if r1 is not None and r2 is not None:
                dist_to_r1 = abs(current_price - r1)
                dist_to_r2 = abs(current_price - r2)
                if dist_to_r1 < dist_to_r2 and dist_to_r1 / current_price < 0.003:
                    val = abs(w["near_resistance"])
                    bearish_score += val
                    reasons.append(f"Proche R1 (+{val} SELL)")
                elif dist_to_r2 / current_price < 0.003:
                    val = abs(w["near_resistance"])
                    bearish_score += val
                    reasons.append(f"Proche R2 (+{val} SELL)")

        # ---- Candlestick patterns ----
        patterns: list[str] = indicators.get("candlestick_patterns", [])
        for p in patterns:
            p_lower = p.lower().replace(" ", "_")
            if p_lower in BULLISH_PATTERNS:
                bullish_score += w["bullish_pattern"]
                reasons.append(f"Pattern {p} (+{w['bullish_pattern']})")
            elif p_lower in BEARISH_PATTERNS:
                val = abs(w["bearish_pattern"])
                bearish_score += val
                reasons.append(f"Pattern {p} (+{val} SELL)")

        # ---- Market structure ----
        structure = indicators.get("market_structure", {})
        struct = structure.get("structure", "") if isinstance(structure, dict) else ""
        if struct == "hh_hl" or struct == "higher_highs":
            bullish_score += w["higher_high_higher_low"]
            reasons.append(f"Structure HH/HL (+{w['higher_high_higher_low']})")
        elif struct == "lh_ll" or struct == "lower_lows":
            val = abs(w["lower_high_lower_low"])
            bearish_score += val
            reasons.append(f"Structure LH/LL (+{val} SELL)")

        # ---- H1 multi-timeframe context ----
        h1_trend = indicators.get("h1_trend", "")
        if h1_trend == "haussier":
            bullish_score += w["h1_trend_bullish"]
            reasons.append(f"H1 haussier (+{w['h1_trend_bullish']})")
        elif h1_trend == "baissier":
            val = abs(w["h1_trend_bearish"])
            bearish_score += val
            reasons.append(f"H1 baissier (+{val} SELL)")

        # ====================================================
        # Decision logic
        # ====================================================
        net_bullish = bullish_score - bearish_score
        net_score = abs(net_bullish)

        if net_bullish >= self.buy_threshold:
            action = "BUY"
            confidence = min(95, 50 + net_score // 2)
        elif net_bullish <= -self.sell_threshold:
            action = "SELL"
            confidence = min(95, 50 + net_score // 2)
        else:
            action = "HOLD"
            confidence = max(10, min(50, net_score))

        # ====================================================
        # SL / TP calculation
        # ====================================================
        atr_val = indicators.get("atr_14", 0) or 0
        price = current_price or 0
        point = self._point if self._point is not None else self._detect_point(price)

        if atr_val > 0 and point > 0:
            sl_pips = max(15, min(50, int((atr_val * self.sl_atr_mult) / (10 * point))))
            tp_pips_raw = int((atr_val * self.tp_atr_mult) / (10 * point))
            tp_pips = max(int(sl_pips * 1.5), tp_pips_raw)
        else:
            sl_pips = 20
            tp_pips = 30

        # ====================================================
        # Risk level
        # ====================================================
        if adx is not None and adx >= 30:
            risk_level = "LOW"
        elif adx is not None and adx >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        # ====================================================
        # Return decision
        # ====================================================
        return {
            "action": action,
            "confidence": int(confidence),
            "reasoning": "; ".join(reasons[:8]),
            "stop_loss_pips": sl_pips,
            "take_profit_pips": tp_pips,
            "risk_level": risk_level,
            "bullish_score": bullish_score,
            "bearish_score": bearish_score,
            "net_score": net_bullish,
        }

    # --------------------------------------------------------
    # Serialization
    # --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Export weights and thresholds as a dict for YAML/JSON serialization."""
        return {
            "weights": dict(self.weights),
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "sl_atr_mult": self.sl_atr_mult,
            "tp_atr_mult": self.tp_atr_mult,
            "point": self._point,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleEngine":
        """Create a RuleEngine from a serialized dict."""
        return cls(
            weights=data.get("weights"),
            buy_threshold=data.get("buy_threshold", 25),
            sell_threshold=data.get("sell_threshold", 25),
            sl_atr_mult=data.get("sl_atr_mult", 1.5),
            tp_atr_mult=data.get("tp_atr_mult", 2.5),
            point=data.get("point"),
        )


# ============================================================
# Module-level helpers
# ============================================================

def load_weights_from_yaml(path: str) -> dict[str, int]:
    """Load weights from a YAML (or JSON) file.

    Falls back to JSON parsing if PyYAML is not installed.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Weights file not found: {path}")

    raw_text = file_path.read_text(encoding="utf-8")

    # Try YAML first, fall back to JSON
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(raw_text)
    except ImportError:
        data = json.loads(raw_text)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at top level, got {type(data).__name__}")

    # Extract weights key if nested under "weights"
    weights_candidate = data.get("weights", data)

    if not isinstance(weights_candidate, dict):
        raise ValueError("Could not find a weights mapping in the file")

    # Ensure all values are int
    validated: dict[str, int] = {}
    for k, v in weights_candidate.items():
        if not isinstance(k, str):
            raise TypeError(f"Weight key must be str, got {type(k).__name__}: {k!r}")
        validated[k] = int(v)

    return validated
