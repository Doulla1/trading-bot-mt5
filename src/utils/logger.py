"""Configuration du logger avec loguru."""

import sys
from loguru import logger
from src.config import settings


def setup_logger() -> None:
    """Initialise loguru avec sortie console + fichier."""
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
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )
    logger.info("Logger initialise")
