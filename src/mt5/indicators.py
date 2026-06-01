"""Calcul des indicateurs techniques via les donnees OHLCV.

v2.0: ADX, Ichimoku Kinko Hyo, Pivot Points, patterns chandeliers,
      structure de marche, contexte multi-timeframe."""

import pandas as pd
import numpy as np
from loguru import logger


def compute_all(df: pd.DataFrame, df_h1: pd.DataFrame | None = None) -> dict:
    """Calcule tous les indicateurs a partir d'un DataFrame OHLCV M15 (+ H1 optionnel)."""
    if df.empty or len(df) < 50:
        logger.warning("Pas assez de donnees pour les indicateurs (min 50 bougies)")
        return {}

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    last_close = close.iloc[-1]

    result = {}

    # --- Momentum ---
    rsi_val = _rsi(close, 14)
    result["rsi_14"] = round(rsi_val, 1) if not np.isnan(rsi_val) else None

    macd_line, signal_line, macd_hist = _macd(close)
    result["macd_line"] = round(macd_line, 5) if not np.isnan(macd_line) else None
    result["macd_signal"] = round(signal_line, 5) if not np.isnan(signal_line) else None
    result["macd_histogram"] = round(macd_hist, 5) if not np.isnan(macd_hist) else None

    # --- ADX (trending vs ranging) v2.0 ---
    adx_val, di_plus, di_minus = _adx(high, low, close, 14)
    result["adx_14"] = round(adx_val, 1) if not np.isnan(adx_val) else None
    result["di_plus"] = round(di_plus, 1) if not np.isnan(di_plus) else None
    result["di_minus"] = round(di_minus, 1) if not np.isnan(di_minus) else None

    # --- Moving Averages ---
    result["sma_20"] = round(close.iloc[-20:].mean(), 5)
    result["sma_50"] = round(close.iloc[-50:].mean(), 5) if len(close) >= 50 else None
    ema_20 = close.ewm(span=20, adjust=False).mean()
    result["ema_20"] = round(float(ema_20.iloc[-1]), 5)
    ema_200 = close.ewm(span=200, adjust=False).mean() if len(close) >= 200 else None
    result["ema_200"] = round(float(ema_200.iloc[-1]), 5) if ema_200 is not None and len(ema_200) > 0 else None

    # --- Bollinger Bands ---
    bb_upper, bb_middle, bb_lower = _bollinger_bands(close, 20, 2)
    result["bb_upper"] = round(bb_upper, 5)
    result["bb_middle"] = round(bb_middle, 5)
    result["bb_lower"] = round(bb_lower, 5)
    result["bb_position_pct"] = round(
        ((last_close - bb_lower) / (bb_upper - bb_lower)) * 100, 1
    ) if bb_upper != bb_lower else None

    # --- ATR (volatilite) ---
    atr_val = _atr(high, low, close, 14)
    result["atr_14"] = round(atr_val, 5) if not np.isnan(atr_val) else None

    # --- Ichimoku Kinko Hyo v2.0 ---
    ichimoku = _ichimoku(high, low, close)
    result.update(ichimoku)

    # --- Pivot Points (daily) v2.0 ---
    pivots = _pivot_points(high, low, close)
    result.update(pivots)

    # --- Prix et range ---
    result["current_price"] = round(last_close, 5)
    result["high_24h"] = round(high.iloc[-96:].max(), 5) if len(high) >= 96 else round(high.max(), 5)
    result["low_24h"] = round(low.iloc[-96:].min(), 5) if len(low) >= 96 else round(low.min(), 5)

    # --- Tendance ---
    if result["sma_50"] is not None:
        result["trend_short"] = "haussier" if last_close > result["sma_20"] else "baissier"
        result["trend_medium"] = "haussier" if last_close > result["sma_50"] else "baissier"
    else:
        result["trend_short"] = "haussier" if last_close > result["sma_20"] else "baissier"
        result["trend_medium"] = "indetermine"

    if result.get("ichimoku_cloud_top") is not None:
        result["ichimoku_trend"] = (
            "haussier" if last_close > result["ichimoku_cloud_top"]
            else "baissier" if last_close < result["ichimoku_cloud_bottom"]
            else "neutre"
        )
    if result["adx_14"] is not None:
        result["market_regime"] = "trending" if result["adx_14"] >= 25 else "ranging"

    # --- Patterns chandeliers v2.0 ---
    result["candlestick_patterns"] = _detect_candlestick_patterns(df)

    # --- Structure de marche v2.0 ---
    result["market_structure"] = _market_structure(high, low, close)

    # --- Multi-timeframe H1 v2.0 ---
    if df_h1 is not None and not df_h1.empty:
        h1_close = df_h1["close"].astype(float)
        result["h1_trend"] = _h1_trend(h1_close)
        result["h1_rsi_14"] = round(_rsi(h1_close, 14), 1)
        result["h1_close"] = round(float(h1_close.iloc[-1]), 5)

    return result


# ============================================================
# Fonctions internes de calcul
# ============================================================

def _rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _macd(close: pd.Series, fast=12, slow=26, signal=9) -> tuple:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])


def _bollinger_bands(close: pd.Series, period=20, std_dev=2) -> tuple:
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> float:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1])


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> np.ndarray:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).values


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> tuple:
    """Average Directional Index."""
    up_move = high.diff()
    down_move = (-low).diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = _true_range(high, low, close)
    atr = pd.Series(tr).ewm(alpha=1 / period, adjust=False).mean()
    smooth_plus = pd.Series(plus_dm).ewm(alpha=1 / period, adjust=False).mean()
    smooth_minus = pd.Series(minus_dm).ewm(alpha=1 / period, adjust=False).mean()
    di_plus = 100 * (smooth_plus / atr)
    di_minus = 100 * (smooth_minus / atr)
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return float(adx.iloc[-1]), float(di_plus.iloc[-1]), float(di_minus.iloc[-1])


def _ichimoku(high: pd.Series, low: pd.Series, close: pd.Series,
              tenkan_period=9, kijun_period=26, senkou_b_period=52) -> dict:
    """Ichimoku Kinko Hyo."""
    try:
        tenkan = (high.rolling(tenkan_period).max() + low.rolling(tenkan_period).min()) / 2
        kijun = (high.rolling(kijun_period).max() + low.rolling(kijun_period).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(kijun_period)
        senkou_b = ((high.rolling(senkou_b_period).max() + low.rolling(senkou_b_period).min()) / 2).shift(kijun_period)

        cloud_top = max(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
        cloud_bottom = min(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
        cloud_color = "vert" if senkou_a.iloc[-1] > senkou_b.iloc[-1] else "rouge"

        if close.iloc[-1] > cloud_top:
            price_vs_cloud = "au-dessus"
        elif close.iloc[-1] < cloud_bottom:
            price_vs_cloud = "dessous"
        else:
            price_vs_cloud = "dedans"

        tk_cross = "aucun"
        if len(tenkan) >= 2:
            if tenkan.iloc[-1] > kijun.iloc[-1] and tenkan.iloc[-2] <= kijun.iloc[-2]:
                tk_cross = "haussier"
            elif tenkan.iloc[-1] < kijun.iloc[-1] and tenkan.iloc[-2] >= kijun.iloc[-2]:
                tk_cross = "baissier"

        return {
            "ichimoku_tenkan": round(float(tenkan.iloc[-1]), 5),
            "ichimoku_kijun": round(float(kijun.iloc[-1]), 5),
            "ichimoku_cloud_top": round(cloud_top, 5),
            "ichimoku_cloud_bottom": round(cloud_bottom, 5),
            "ichimoku_cloud_color": cloud_color,
            "ichimoku_price_vs_cloud": price_vs_cloud,
            "ichimoku_tenkan_kijun_cross": tk_cross,
        }
    except Exception:
        return dict.fromkeys(
            ["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_cloud_top",
             "ichimoku_cloud_bottom"],
            None
        )


def _pivot_points(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    """Points pivots classiques."""
    try:
        h_prev = float(high.iloc[-2])
        l_prev = float(low.iloc[-2])
        c_prev = float(close.iloc[-2])
        pp = (h_prev + l_prev + c_prev) / 3
        r1 = 2 * pp - l_prev
        s1 = 2 * pp - h_prev
        r2 = pp + (h_prev - l_prev)
        s2 = pp - (h_prev - l_prev)
        r3 = h_prev + 2 * (pp - l_prev)
        s3 = l_prev - 2 * (h_prev - pp)

        last_price = float(close.iloc[-1])
        levels_below = [l for l in [s1, s2, s3] if l < last_price]
        nearest_support = max(levels_below) if levels_below else None
        levels_above = [l for l in [r1, r2, r3] if l > last_price]
        nearest_resistance = min(levels_above) if levels_above else None

        return {
            "pivot_pp": round(pp, 5), "pivot_r1": round(r1, 5),
            "pivot_r2": round(r2, 5), "pivot_r3": round(r3, 5),
            "pivot_s1": round(s1, 5), "pivot_s2": round(s2, 5),
            "pivot_s3": round(s3, 5),
            "pivot_nearest_support": round(nearest_support, 5) if nearest_support else None,
            "pivot_nearest_resistance": round(nearest_resistance, 5) if nearest_resistance else None,
        }
    except Exception:
        return {}


def _detect_candlestick_patterns(df: pd.DataFrame) -> list[str]:
    """Detecte les patterns chandeliers majeurs."""
    patterns = []
    try:
        o = df["open"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        c = df["close"].astype(float)
        idx = -1

        body = abs(c.iloc[idx] - o.iloc[idx])
        upper_wick = h.iloc[idx] - max(c.iloc[idx], o.iloc[idx])
        lower_wick = min(c.iloc[idx], o.iloc[idx]) - l.iloc[idx]
        total_range = h.iloc[idx] - l.iloc[idx]

        body_pct = (body / total_range * 100) if total_range != 0 else 0

        if body_pct < 10:
            patterns.append("doji")
        if lower_wick > 2 * body and upper_wick < body and body_pct > 10:
            patterns.append("hammer" if c.iloc[idx] > o.iloc[idx] else "hanging_man")
        if upper_wick > 2 * body and lower_wick < body and body_pct > 10:
            patterns.append("shooting_star" if c.iloc[idx] < o.iloc[idx] else "inverted_hammer")

        if len(o) >= 2:
            prev_body = abs(c.iloc[-2] - o.iloc[-2])
            if body > prev_body * 1.5:
                if c.iloc[idx] > o.iloc[idx] and c.iloc[-2] < o.iloc[-2]:
                    patterns.append("bullish_engulfing")
                elif c.iloc[idx] < o.iloc[idx] and c.iloc[-2] > o.iloc[-2]:
                    patterns.append("bearish_engulfing")
    except Exception:
        pass
    return patterns if patterns else ["aucun_pattern"]


def _market_structure(high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 20) -> dict:
    """Analyse la structure de marche (HH/HL ou LH/LL)."""
    try:
        recent_high = high.iloc[-lookback:].values
        recent_low = low.iloc[-lookback:].values

        highs_idx, lows_idx = [], []
        for i in range(2, len(recent_high) - 2):
            if recent_high[i] == recent_high[i - 2:i + 3].max():
                highs_idx.append(i)
            if recent_low[i] == recent_low[i - 2:i + 3].min():
                lows_idx.append(i)

        highs_values = [recent_high[i] for i in highs_idx]
        lows_values = [recent_low[i] for i in lows_idx]

        hh = len(highs_values) >= 2 and highs_values[-1] > highs_values[-2]
        hl = len(lows_values) >= 2 and lows_values[-1] > lows_values[-2]
        lh = len(highs_values) >= 2 and highs_values[-1] < highs_values[-2]
        ll = len(lows_values) >= 2 and lows_values[-1] < lows_values[-2]

        if hh and hl:
            structure = "uptrend"
        elif lh and ll:
            structure = "downtrend"
        else:
            structure = "consolidation"

        return {
            "structure": structure,
            "last_swing_high": round(highs_values[-1], 5) if highs_values else None,
            "last_swing_low": round(lows_values[-1], 5) if lows_values else None,
        }
    except Exception:
        return {"structure": "indetermine", "last_swing_high": None, "last_swing_low": None}


def _h1_trend(close: pd.Series) -> str:
    """Tendance simple H1: prix vs EMA 20."""
    ema = close.ewm(span=20, adjust=False).mean()
    if len(ema) < 2:
        return "indetermine"
    return "haussier" if close.iloc[-1] > ema.iloc[-1] else "baissier"
