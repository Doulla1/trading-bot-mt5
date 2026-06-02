#!/usr/bin/env python3
"""Backtesteur pour le Trading Bot MT5 - CLI principal.

Usage:
    python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31
    python backtest.py --multi --from 2026-05-01 --to 2026-05-31
    python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31 --optimize
    python backtest.py --export --symbol EURUSD --months 3
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def cmd_backtest(args):
    from src.backtest.engine import BacktestEngine
    from src.backtest.rules_engine import RuleEngine, load_weights_from_yaml
    from src.backtest.report import BacktestReport

    weights_path = args.weights
    rule_engine = None
    if Path(weights_path).exists():
        weights_data = load_weights_from_yaml(weights_path)
        rule_engine = RuleEngine.from_dict(weights_data)

    symbols_config = [{
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "magic": 73000,
        "interval_min": 15 if args.timeframe == "M15" else 60,
    }]

    engine = BacktestEngine(
        symbols_config=symbols_config,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_balance=args.balance,
        rule_engine=rule_engine,
        data_dir=args.data_dir,
    )

    results = engine.run()

    for sym, data in results.items():
        executor = data["executor"]
        source = data["source"]
        report = BacktestReport(
            executor=executor,
            initial_balance=args.balance,
            symbol=sym,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        report.print_report()

        if args.output:
            df = report.to_dataframe()
            if args.output.endswith('.csv'):
                df.to_csv(args.output, index=False)
            elif args.output.endswith('.json'):
                df.to_json(args.output, orient='records', indent=2)
            print(f"\nTrades exported to {args.output}")


def cmd_multi(args):
    from src.backtest.engine import BacktestEngine
    from src.backtest.rules_engine import RuleEngine, load_weights_from_yaml
    from src.backtest.report import BacktestReport, generate_multi_symbol_report

    weights_path = args.weights
    rule_engine = None
    if Path(weights_path).exists():
        weights_data = load_weights_from_yaml(weights_path)
        rule_engine = RuleEngine.from_dict(weights_data)

    symbols_config = [
        {"symbol": "EURUSD", "timeframe": "M15", "magic": 73456, "interval_min": 15},
        {"symbol": "GBPUSD", "timeframe": "M15", "magic": 73457, "interval_min": 15},
        {"symbol": "AUDUSD", "timeframe": "M15", "magic": 73458, "interval_min": 15},
        {"symbol": "USDJPY", "timeframe": "M15", "magic": 73459, "interval_min": 15},
        {"symbol": "USDCHF", "timeframe": "M15", "magic": 73460, "interval_min": 15},
        {"symbol": "XAUUSD", "timeframe": "H1",  "magic": 73461, "interval_min": 60},
    ]

    engine = BacktestEngine(
        symbols_config=symbols_config,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_balance=args.balance,
        rule_engine=rule_engine,
        data_dir=args.data_dir,
    )

    results = engine.run()

    reports = {}
    for sym, data in results.items():
        executor = data["executor"]
        source = data["source"]
        report = BacktestReport(
            executor=executor,
            initial_balance=args.balance,
            symbol=sym,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        reports[sym] = report

    generate_multi_symbol_report(reports, args.balance)

    if args.output:
        all_trades = []
        for sym, report in reports.items():
            df = report.to_dataframe()
            all_trades.append(df)
        import pandas as pd
        combined = pd.concat(all_trades, ignore_index=True)
        if args.output.endswith('.csv'):
            combined.to_csv(args.output, index=False)
        elif args.output.endswith('.json'):
            combined.to_json(args.output, orient='records', indent=2)
        print(f"\nTrades exported to {args.output}")


def cmd_optimize(args):
    from src.backtest.optimizer import GridOptimizer

    symbols_config = [{
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "magic": 73000,
        "interval_min": 15 if args.timeframe == "M15" else 60,
    }]

    optimizer = GridOptimizer(
        symbols_config=symbols_config,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_balance=args.balance,
        data_dir=args.data_dir,
        metric=args.metric,
    )

    param_grid = {
        "buy_threshold": [15, 20, 25, 30, 35],
        "sell_threshold": [15, 20, 25, 30, 35],
        "sl_atr_mult": [1.0, 1.5, 2.0],
        "tp_atr_mult": [2.0, 2.5, 3.0, 3.5],
        "max_risk_per_trade_pct": [0.5, 1.0, 1.5],
    }

    if args.optimize_config:
        with open(args.optimize_config) as f:
            config = json.load(f)
        param_grid = config.get("param_grid", param_grid)

    results = optimizer.run(param_grid)
    optimizer.print_top(results, n=15)

    if args.output:
        optimizer.save_results(results, args.output)


def cmd_export(args):
    symbol = args.symbol or "EURUSD"
    timeframe = args.timeframe or "M15"
    tf = "M15" if timeframe == "M15" else "H1"
    symbol_lower = symbol.lower()

    start_date = args.start_date
    end_date = args.end_date
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  EXPORT DE DONNEES MT5 POUR BACKTESTING                     ║
    ╠══════════════════════════════════════════════════════════════╣
    ║                                                              ║
    ║  1. Ouvrir MetaTrader 5 et se connecter au compte            ║
    ║  2. Ouvrir le graphique {symbol} en {timeframe}              ║
    ║  3. Appuyer sur F2 pour ouvrir l'Historique du Centre       ║
    ║  4. Selectionner la periode souhaitee                        ║
    ║  5. Cliquer sur "Exporter" -> CSV                            ║
    ║                                                              ║
    ║  OU utiliser le script Python ci-dessous:                    ║
    ║                                                              ║
    ║  from datetime import datetime                               ║
    ║  import MetaTrader5 as mt5                                   ║
    ║  import pandas as pd                                         ║
    ║                                                              ║
    ║  mt5.initialize()                                            ║
    ║  rates = mt5.copy_rates_range(                               ║
    ║      "{symbol}",                                              ║
    ║      mt5.TIMEFRAME_{tf},                                     ║
    ║      datetime({start_year}, {start_month}, 1),               ║
    ║      datetime({end_year}, {end_month}, 1),                   ║
    ║  )                                                           ║
    ║  df = pd.DataFrame(rates)                                    ║
    ║  df["datetime"] = pd.to_datetime(df["time"], unit="s")      ║
    ║  df.to_csv("data/historical/{symbol_lower}/                  ║
    ║      {symbol_lower}_{timeframe}_{start_year}-{start_month:02d}.csv",║
    ║      columns=["datetime","open","high","low","close",       ║
    ║               "tick_volume","spread"], index=False)          ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """.format(
        symbol=symbol,
        timeframe=timeframe,
        tf=tf,
        symbol_lower=symbol_lower,
        start_year=start_dt.year,
        start_month=start_dt.month,
        end_year=end_dt.year,
        end_month=end_dt.month,
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Backtesteur pour Trading Bot MT5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backtest.py --symbol EURUSD --from 2026-05-01 --to 2026-05-31
  python backtest.py --multi --from 2026-04-01 --to 2026-05-31
  python backtest.py --symbol XAUUSD --timeframe H1 --optimize
  python backtest.py --export --symbol GBPUSD
        """
    )

    parser.add_argument("--symbol", default=None, help="Symbol to backtest")
    parser.add_argument("--timeframe", default="M15", choices=["M15", "H1"])
    parser.add_argument("--from", dest="start_date", default=None,
                       help="Start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--to", dest="end_date", default=None,
                       help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--data-dir", default="data/historical")
    parser.add_argument("--weights", default="src/backtest/weights.yaml")
    parser.add_argument("--multi", action="store_true")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--optimize-config", default=None)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--metric", default="profit_factor",
                       choices=["profit_factor", "sharpe_ratio", "net_profit",
                               "win_rate", "sortino_ratio", "return_pct"])

    args = parser.parse_args()

    # Set default dates
    if args.end_date is None:
        args.end_date = datetime.now().strftime("%Y-%m-%d")
    if args.start_date is None:
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
        args.start_date = (end_dt - timedelta(days=30)).strftime("%Y-%m-%d")

    # Route to command
    if args.export:
        cmd_export(args)
    elif args.optimize:
        cmd_optimize(args)
    elif args.multi:
        cmd_multi(args)
    else:
        if args.symbol is None:
            args.symbol = "EURUSD"
        cmd_backtest(args)


if __name__ == "__main__":
    main()
