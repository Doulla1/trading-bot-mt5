"""Capture d'ecran des charts MT5 via mss."""

from pathlib import Path
from datetime import datetime
from loguru import logger

from src.config import settings


def capture_chart(symbol=None) -> Path | None:
    """Prend un screenshot de l'ecran principal via mss. Retourne le chemin ou None (CRITICAL-07)."""
    sym = symbol or settings.trading_symbol
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{sym}_{timestamp}.png"
    filepath = settings.screenshots_dir / filename

    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            # Capturer le moniteur principal
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))

        logger.info(f"Screenshot sauvegarde : {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Echec screenshot pour {sym}: {e}")
        return None


def cleanup_old_screenshots(max_age_hours=24) -> int:
    """Supprime les screenshots de plus de N heures."""
    import time
    cutoff = time.time() - max_age_hours * 3600
    deleted = 0
    for f in settings.screenshots_dir.glob("*.png"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    if deleted:
        logger.debug(f"{deleted} vieux screenshots supprimes")
    return deleted
