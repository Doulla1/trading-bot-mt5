"""Configuration du logger avec loguru - rotation journaliere, retention 15 jours."""

import sys
from pathlib import Path
from loguru import logger
from src.config import settings


def setup_logger() -> None:
    """Initialise loguru avec sortie console + fichier journalier."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )
    logger.add(
        str(settings.log_path),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention="15 days",
        encoding="utf-8",
        delay=True,
        catch=True,
    )
    logger.info("Logger initialise")

    # Nettoyage des dossiers de logs orphelins (symboles plus suivis)
    _cleanup_orphan_logs()


def _cleanup_orphan_logs(max_days: int = 30) -> None:
    """Supprime les dossiers de logs des symboles qui n'existent plus depuis +30j."""
    try:
        active_symbols = {"eurusd", "gbpusd", "audusd", "usdjpy", "usdchf", "xauusd"}
        logs_root = settings.project_root / "logs"
        if not logs_root.exists():
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for folder in logs_root.iterdir():
            if folder.is_dir() and folder.name.lower() not in active_symbols:
                # Verifier si le dossier est vieux
                mtime = folder.stat().st_mtime
                age_days = (now.timestamp() - mtime) / 86400
                if age_days > max_days:
                    import shutil
                    shutil.rmtree(folder, ignore_errors=True)
                    logger.info(f"Dossier logs orphelin supprime: {folder.name}")
    except Exception:
        pass
