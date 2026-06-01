"""Rendu de charts professionnels pour l'OCR IA.

Genere des images de charts avec indicateurs dessines directement
(Ichimoku, Bollinger, RSI, MACD, Pivots) a partir des donnees OHLCV.
Ne necessite PAS que MT5 soit au premier plan."""

import io
from pathlib import Path
from loguru import logger
import pandas as pd
import numpy as np

# Utiliser le backend non-interactif pour eviter les warnings
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
from datetime import datetime

from src.config import settings


def render_analysis_chart(df_m15: pd.DataFrame, indicators: dict,
                          symbol: str = None) -> Path | None:
    """Genere un chart professionnel avec tous les indicateurs pour l'OCR.

    Retourne le chemin du fichier PNG genere."""
    if df_m15.empty:
        logger.warning("DataFrame vide, impossible de generer le chart")
        return None

    sym = symbol or settings.trading_symbol
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = settings.screenshots_dir / f"chart_{sym}_{timestamp}.png"

    try:
        df = df_m15.copy()
        # Garder les 100 dernieres bougies pour la lisibilite
        df = df.tail(100)
        df.index = pd.to_datetime(df.index)

        # mplfinance attend 'volume', MT5 donne 'tick_volume'
        if 'tick_volume' in df.columns and 'volume' not in df.columns:
            df['volume'] = df['tick_volume']

        # Configurer les overlays (indicateurs sur le chart principal)
        apds = _build_addplots(df, indicators)

        # Style
        mc = mpf.make_marketcolors(
            up='#26a69a', down='#ef5350',
            edge='inherit', wick='inherit',
            volume='inherit', alpha=0.9,
        )
        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='--', gridcolor='#333333',
            facecolor='#1a1a2e', figcolor='#1a1a2e',
            y_on_right=True,
        )

        # Titre
        title = f"{sym} M15 - {indicators.get('current_price', 'N/A')}"
        if indicators.get('market_regime'):
            title += f" | {indicators['market_regime']}"
        if indicators.get('market_structure', {}).get('structure'):
            title += f" | {indicators['market_structure']['structure']}"

        mpf.plot(
            df, type='candle', style=s,
            addplot=apds if apds else [],
            title=title,
            volume=True,
            figsize=(14, 10),
            savefig=str(filepath),
            tight_layout=True,
        )

        logger.info(f"Chart genere : {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Echec generation chart: {e}")
        return None


def _build_addplots(df: pd.DataFrame, ind: dict) -> list:
    """Construit les overlays matplotlib pour mplfinance."""
    apds = []
    close = df["close"].astype(float)

    # --- Ichimoku Cloud ---
    if ind.get("ichimoku_cloud_top") is not None and ind.get("ichimoku_cloud_bottom") is not None:
        try:
            tenkan = _calc_ichimoku_series(df)
            if tenkan is not None:
                apds.extend(tenkan)
        except Exception:
            pass

    # --- EMA 20 et 200 ---
    apds.append(mpf.make_addplot(
        close.ewm(span=20, adjust=False).mean(),
        color='#ff9800', width=1, label='EMA20'
    ))
    if len(close) >= 200:
        apds.append(mpf.make_addplot(
            close.ewm(span=200, adjust=False).mean(),
            color='#9c27b0', width=1, label='EMA200'
        ))

    # --- Bollinger Bands ---
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    apds.append(mpf.make_addplot(
        bb_mid + 2 * bb_std, color='#64b5f6', width=0.7, alpha=0.4
    ))
    apds.append(mpf.make_addplot(
        bb_mid - 2 * bb_std, color='#64b5f6', width=0.7, alpha=0.4
    ))

    # --- Pivot Points ---
    if ind.get("pivot_r1") is not None:
        pivots = [ind[k] for k in ("pivot_r3", "pivot_r2", "pivot_r1", "pivot_pp", "pivot_s1", "pivot_s2", "pivot_s3") if ind.get(k)]
        for pv in pivots:
            line = pd.Series([pv] * len(df), index=df.index)
            apds.append(mpf.make_addplot(
                line, color='#ffeb3b', width=0.5, alpha=0.5, linestyle=':'
            ))

    return apds


def _calc_ichimoku_series(df: pd.DataFrame) -> list | None:
    """Calcule les series Ichimoku pour overlay."""
    try:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

        return [
            mpf.make_addplot(senkou_a, color='#4caf50', alpha=0.2, width=0.5),
            mpf.make_addplot(senkou_b, color='#f44336', alpha=0.2, width=0.5),
            # Remplir entre senkou_a et senkou_b
            mpf.make_addplot(
                pd.concat([senkou_a, senkou_b], axis=1).max(axis=1),
                color='#4caf50', alpha=0.08,
            ),
            mpf.make_addplot(
                pd.concat([senkou_a, senkou_b], axis=1).min(axis=1),
                color='#f44336', alpha=0.08,
                panel=0
            ),
            mpf.make_addplot(tenkan, color='#2196f3', width=1, label='Tenkan'),
            mpf.make_addplot(kijun, color='#e91e63', width=1, label='Kijun'),
        ]
    except Exception:
        return None
