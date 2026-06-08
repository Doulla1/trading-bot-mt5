#!/usr/bin/env python3
"""Script to print the complete prompt sent to the AI for a given asset.

Supports connecting to MT5 to fetch real-time data, or falling back to mock data
if MT5 is unavailable or if --mock is specified.

Usage:
    python scripts/print_prompt.py --symbol EURUSD
    python scripts/print_prompt.py --symbol XAUUSD --type analysis
    python scripts/print_prompt.py --symbol GBPUSD --mock
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Add project root to python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Parse arguments first to set environment variables before pydantic settings loads
parser = argparse.ArgumentParser(description="Print the AI prompt for a symbol")
parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g., EURUSD, XAUUSD)")
parser.add_argument("--timeframe", type=str, default="M15", help="Timeframe (default: M15)")
parser.add_argument("--type", type=str, choices=["decision", "analysis"], default="decision",
                    help="Prompt type: 'decision' (DeepSeek Pro template) or 'analysis' (GPT legacy template)")
parser.add_argument("--mock", action="store_true", help="Force mock data instead of connecting to MT5")
args = parser.parse_known_args()[0]

# Set environment overrides
os.environ["TRADING_SYMBOL"] = args.symbol.upper()
os.environ["TRADING_TIMEFRAME"] = args.timeframe.upper()

from loguru import logger
from rich.console import Console

# Configure loguru to print only to stderr so stdout has only the clean prompt
logger.remove()
logger.add(sys.stderr, level="INFO")

from src.config import settings
from src.ai.prompts import build_decision_prompt, build_analysis_prompt


def get_real_data(symbol, timeframe):
    """Attempt to connect to MT5 and retrieve real indicators, calendar, positions, etc."""
    try:
        from src.mt5 import bridge, executor, indicators
        from src.data.calendar import fetch_events, filter_relevant_events
        from src.data.database import get_recent_trades, get_statistics
        from src.scheduler.scheduler import _get_session_context
        import pandas as pd
    except ImportError as e:
        logger.warning(f"Could not import MT5 bridge or database modules: {e}")
        return None

    logger.info("Connecting to MT5...")
    if not bridge.connect():
        logger.warning("Failed to connect to MT5.")
        return None

    try:
        logger.info(f"Retrieving rates and calculating indicators for {symbol}...")
        df_m15 = bridge.get_rates(symbol, "M15", count=200)
        df_h1 = bridge.get_rates(symbol, "H1", count=100)
        df_h4 = bridge.get_rates(symbol, "H4", count=50)

        if df_m15 is None or df_m15.empty:
            logger.warning("No rates found.")
            return None

        # Retrieve spread
        symbol_info = bridge.get_symbol_info(symbol)
        spread = None
        if symbol_info:
            spread_points = symbol_info.get("spread", 0)
            if symbol_info.get("digits", 5) in [3, 5]:
                spread = spread_points / 10.0
            else:
                spread = float(spread_points)

        indicators_data = indicators.compute_all(df_m15, df_h1, df_h4, spread=spread)

        logger.info("Fetching calendar events, positions, and stats...")
        all_events = fetch_events()
        relevant_events = filter_relevant_events(all_events, symbol)
        session_context = _get_session_context()
        open_positions = executor.get_open_positions(symbol)
        account_info = bridge.get_account_info() or {}
        trade_history = get_recent_trades(limit=20)
        performance_stats = get_statistics(symbol=symbol)

        # Mock OCR data as we don't have screenshot visual in this tool
        ocr_data = {
            "market_phase": indicators_data.get("market_regime", "ranging"),
            "chart_patterns": ["undetermined"],
            "support_levels": [indicators_data.get("pivot_nearest_support", "N/A")],
            "resistance_levels": [indicators_data.get("pivot_nearest_resistance", "N/A")],
            "trendlines": "N/A",
            "candlestick_visual": "N/A",
            "price_action_notes": "Real-time query without visual capture"
        }

        return {
            "indicators": indicators_data,
            "ocr_data": ocr_data,
            "calendar_events": relevant_events,
            "open_positions": open_positions,
            "account_info": account_info,
            "trade_history": trade_history,
            "session_context": session_context,
            "performance_stats": performance_stats
        }

    except Exception as e:
        logger.exception(f"Error fetching real data: {e}")
        return None
    finally:
        bridge.disconnect()


def get_mock_data(symbol):
    """Generate realistic dummy data for testing or when MT5 is offline."""
    now = datetime.now(timezone.utc)
    
    # Specific SL values from prompts.py config
    from src.ai.prompts import SL_LIMITS_CONFIG
    sl_limits = SL_LIMITS_CONFIG.get(symbol, {"min": 15, "max": 50, "note": ""})
    
    # Determine base price based on symbol
    if "USD" in symbol:
        base_price = 1.08500 if symbol.startswith("EUR") or symbol.startswith("GBP") or symbol.startswith("AUD") else 100.00
    elif "JPY" in symbol:
        base_price = 155.00
    elif symbol == "XAUUSD":
        base_price = 2350.00
    else:
        base_price = 1.00000

    indicators_data = {
        "current_price": base_price,
        "rsi_14": 52.4,
        "macd_line": 0.00012,
        "macd_signal": 0.00008,
        "macd_histogram": 0.00004,
        "adx_14": 22.5,
        "di_plus": 18.2,
        "di_minus": 16.4,
        "ema_20": base_price - 0.0002,
        "ema_200": base_price - 0.0015,
        "volume_anomaly_pct": 105.0,
        "daily_vwap": base_price - 0.0005,
        "bb_upper": base_price + 0.0022,
        "bb_middle": base_price,
        "bb_lower": base_price - 0.0022,
        "bb_position_pct": 58.2,
        "atr_14": 0.00120 if base_price < 50 else 1.50 if base_price < 500 else 15.00,
        "ichimoku_tenkan": base_price + 0.0005,
        "ichimoku_kijun": base_price,
        "ichimoku_cloud_top": base_price + 0.0002,
        "ichimoku_cloud_bottom": base_price - 0.0008,
        "ichimoku_cloud_color": "vert",
        "ichimoku_price_vs_cloud": "au-dessus",
        "ichimoku_tenkan_kijun_cross": "aucun",
        "ichimoku_trend": "haussier",
        "pivot_pp": base_price - 0.0010,
        "pivot_r1": base_price + 0.0015,
        "pivot_r2": base_price + 0.0030,
        "pivot_r3": base_price + 0.0060,
        "pivot_s1": base_price - 0.0025,
        "pivot_s2": base_price - 0.0050,
        "pivot_s3": base_price - 0.0080,
        "pivot_nearest_support": base_price - 0.0025,
        "pivot_nearest_resistance": base_price + 0.0015,
        "high_24h": base_price + 0.0045,
        "low_24h": base_price - 0.0058,
        "trend_short": "haussier",
        "trend_medium": "haussier",
        "market_regime": "ranging",
        "ema_20_slope": "plate",
        "ema_200_slope": "haussiere",
        "dist_ema20_atr": 0.18,
        "dist_ema200_atr": 1.52,
        "dist_bb_upper_atr": 1.56,
        "dist_bb_lower_atr": 2.10,
        "dist_pivot_support_atr": 2.35,
        "dist_pivot_resistance_atr": 0.98,
        "dist_ichimoku_cloud_top_atr": 0.10,
        "dist_ichimoku_cloud_bottom_atr": 0.94,
        "dist_swing_high_atr": 1.45,
        "dist_swing_low_atr": 1.82,
        "spread": 1.2,
        "spread_atr_pct": 10.0,
        "candlestick_patterns": ["hammer"],
        "market_structure": {
            "structure": "uptrend",
            "last_swing_high": base_price + 0.0018,
            "last_swing_low": base_price - 0.0021
        },
        "h1_trend": "haussier",
        "h1_rsi_14": 56.5,
        "h1_close": base_price + 0.0005,
        "h4_trend": "haussier",
        "h4_rsi_14": 58.2,
        "h4_close": base_price - 0.0008
    }

    ocr_data = {
        "market_phase": "trending_up",
        "chart_patterns": ["double bottom"],
        "support_levels": [base_price - 0.0025, base_price - 0.0050],
        "resistance_levels": [base_price + 0.0015, base_price + 0.0030],
        "trendlines": "Ascending support line",
        "candlestick_visual": "Hammer candle forming on H1",
        "price_action_notes": "Strong rejection tail at key support zone"
    }

    calendar_events = [
        {
            "date": now.strftime("%Y-%m-%d"),
            "time": "14:30",
            "impact": "high",
            "currency": "USD" if "USD" in symbol else "EUR" if "EUR" in symbol else "GBP",
            "event": "Major Economic Indicator Release (CPI/GDP)"
        },
        {
            "date": now.strftime("%Y-%m-%d"),
            "time": "16:00",
            "impact": "medium",
            "currency": "USD" if "USD" in symbol else "EUR" if "EUR" in symbol else "GBP",
            "event": "Business PMI Survey"
        }
    ]

    open_positions = []
    
    account_info = {
        "balance": 10000.00,
        "equity": 10000.00
    }

    trade_history = [
        {
            "direction": "BUY",
            "symbol": symbol,
            "confidence": 75,
            "profit": 45.20,
            "opened_at": now.strftime("%Y-%m-%dT08:00:00")
        },
        {
            "direction": "SELL",
            "symbol": symbol,
            "confidence": 68,
            "profit": -18.50,
            "opened_at": now.strftime("%Y-%m-%dT10:30:00")
        }
    ]

    session_context = {
        "datetime": now.strftime("%Y-%m-%d %H:%M UTC"),
        "session": "London_New_York_overlap",
        "day_of_week": now.strftime("%A"),
        "hour": now.hour
    }

    performance_stats = {
        "total_closed": 12,
        "wins": 8,
        "losses": 4,
        "win_rate": 66.7,
        "total_profit": 125.40,
        "avg_confidence": 72.5
    }

    return {
        "indicators": indicators_data,
        "ocr_data": ocr_data,
        "calendar_events": calendar_events,
        "open_positions": open_positions,
        "account_info": account_info,
        "trade_history": trade_history,
        "session_context": session_context,
        "performance_stats": performance_stats
    }


def main():
    symbol = args.symbol.upper()
    timeframe = args.timeframe.upper()

    console = Console(stderr=True)
    console.print(f"[bold cyan]🔍 AI Prompt Generator[/bold cyan] | Symbol: [yellow]{symbol}[/yellow] | Timeframe: [yellow]{timeframe}[/yellow]")
    console.print("-" * 60, style="dim")

    data = None
    if not args.mock:
        data = get_real_data(symbol, timeframe)

    if data is None:
        console.print("[yellow]Using mock data (MT5 offline or --mock specified)[/yellow]", style="italic")
        data = get_mock_data(symbol)
    else:
        console.print("[green]Successfully retrieved real data from MT5[/green]")

    console.print("-" * 60, style="dim")
    console.print(f"Generating prompt type: [bold]{args.type}[/bold]\n", style="cyan")

    # Build the prompt
    if args.type == "decision":
        prompt = build_decision_prompt(
            symbol=symbol,
            timeframe=timeframe,
            indicators=data["indicators"],
            ocr_data=data["ocr_data"],
            calendar_events=data["calendar_events"],
            open_positions=data["open_positions"],
            account_info=data["account_info"],
            trade_history=data["trade_history"],
            session_context=data["session_context"],
            performance_stats=data.get("performance_stats")
        )
    else:
        prompt = build_analysis_prompt(
            symbol=symbol,
            timeframe=timeframe,
            indicators=data["indicators"],
            calendar_events=data["calendar_events"],
            open_positions=data["open_positions"],
            account_info=data["account_info"]
        )

    # Print the clean prompt to stdout (so it can be redirected using '>')
    print(prompt)


if __name__ == "__main__":
    main()
