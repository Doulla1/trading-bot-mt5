#!/usr/bin/env python3
"""Point d'entree du Trading Bot IA - support multi-instances."""

import sys
import os
import argparse
from pathlib import Path

# Parser les arguments AVANT l'import des modules, pour surcharger le .env
parser = argparse.ArgumentParser(description="Trading Bot IA")
parser.add_argument("--symbol", type=str, help="Symbole a trader (ex: EURUSD, GBPUSD, AUDUSD)")
parser.add_argument("--once", action="store_true", help="Execution unique puis statistiques")
parser.add_argument("--stats", action="store_true", help="Afficher les statistiques uniquement")
args, _ = parser.parse_known_args()

# Si --symbol est fourni, on override TRADING_SYMBOL dans l'environnement
# avant que pydantic-settings ne charge la configuration
if args.symbol:
    os.environ["TRADING_SYMBOL"] = args.symbol.upper()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.logger import setup_logger
from src.scheduler.scheduler import run_forever, run_once
from src.data.database import get_db, get_statistics
from src.config import settings
from loguru import logger
from rich.console import Console
from rich.table import Table


def show_banner():
    console = Console()
    console.print()
    console.print("  🤖 [bold cyan]TRADING BOT IA[/bold cyan] - Fusion Markets / MT5", style="bold")
    console.print("  " + "-" * 50, style="dim")
    console.print(f"  Symbole: [yellow]{settings.trading_symbol}[/yellow] | Timeframe: [yellow]{settings.trading_timeframe}[/yellow]")
    console.print(f"  DB: [dim]{settings.db_path}[/dim]")
    console.print(f"  Intervale: [yellow]{settings.analysis_interval_minutes} min[/yellow] | Confiance min: [yellow]{settings.min_confidence_threshold}%[/yellow]")
    console.print(f"  Risque/trade: [yellow]{settings.max_risk_per_trade_pct}%[/yellow] | Perte/jour max: [yellow]{settings.max_daily_loss_pct}%[/yellow]")
    console.print("  " + "-" * 50, style="dim")
    console.print()


def show_stats():
    """Affiche les statistiques."""
    stats = get_statistics()
    console = Console()
    table = Table(title=f"Statistiques de trading - {settings.trading_symbol}")
    table.add_column("Metrique", style="cyan")
    table.add_column("Valeur", style="green")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)


if __name__ == "__main__":
    setup_logger()

    if args.symbol:
        logger.info(f"Instance lancee avec --symbol={args.symbol.upper()}")

    if args.once:
        logger.info("Mode: execution unique")
        run_once()
        show_stats()
    elif args.stats:
        show_stats()
    else:
        show_banner()
        try:
            run_forever()
        except KeyboardInterrupt:
            logger.info("Bot arrete proprement.")
            show_stats()
