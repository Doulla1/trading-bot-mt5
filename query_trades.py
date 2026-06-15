#!/usr/bin/env python3
import sqlite3
import glob
import os
import sys
import argparse
import json
import csv
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Extract trades from all database files for a specific day.")
    parser.add_argument(
        "--date", 
        type=str, 
        default=None, 
        help="Date to extract trades for (format: YYYY-MM-DD). Defaults to today."
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Extract all trades from all time."
    )
    parser.add_argument(
        "--format", 
        type=str, 
        choices=["text", "json", "csv"], 
        default="text", 
        help="Output format (default: text)."
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default=None, 
        help="Write output to a file."
    )
    return parser.parse_args()

def extract_trades(target_date=None, all_time=False):
    # If no date is given and not all_time, default to today
    if not target_date and not all_time:
        target_date = datetime.now().strftime("%Y-%m-%d")
        
    db_paths = glob.glob("data/*/trading.db")
    if os.path.exists("data/trading_bot.db"):
        db_paths.append("data/trading_bot.db")
        
    all_trades = []
    
    for path in db_paths:
        if not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Check if trades table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
            if not cursor.fetchone():
                conn.close()
                continue
                
            if all_time:
                query = "SELECT * FROM trades"
                rows = cursor.execute(query).fetchall()
            else:
                query = "SELECT * FROM trades WHERE opened_at LIKE ? OR closed_at LIKE ?"
                rows = cursor.execute(query, (f"{target_date}%", f"{target_date}%")).fetchall()
                
            for r in rows:
                trade_dict = dict(r)
                trade_dict["db_source"] = path
                all_trades.append(trade_dict)
                
            conn.close()
        except Exception as e:
            print(f"Error querying {path}: {e}", file=sys.stderr)
            
    # Deduplicate trades by ticket
    dedup_trades = {}
    for t in all_trades:
        ticket = t.get("ticket")
        if not ticket:
            continue
        # If ticket is already present, prefer the one with closed_at or more filled details
        if ticket not in dedup_trades:
            dedup_trades[ticket] = t
        else:
            existing = dedup_trades[ticket]
            # Prefer the closed trade or one with more info (e.g. profit is not None)
            if existing.get("closed_at") is None and t.get("closed_at") is not None:
                dedup_trades[ticket] = t
            elif existing.get("profit") is None and t.get("profit") is not None:
                dedup_trades[ticket] = t
                
    unique_trades = list(dedup_trades.values())
    unique_trades.sort(key=lambda x: x.get('opened_at') or x.get('closed_at') or '')
    return unique_trades, target_date

def print_text(trades, date_str, all_time):
    title = f"--- ALL TRADES ---" if all_time else f"--- TRADES FOR {date_str} ---"
    print(title)
    
    open_trades = [t for t in trades if not t.get("closed_at")]
    closed_trades = [t for t in trades if t.get("closed_at")]
    
    print(f"\nOpen Trades ({len(open_trades)}):")
    if not open_trades:
        print("  None")
    for t in open_trades:
        tp_sl = f"SL: {t.get('stop_loss') or 'N/A'} | TP: {t.get('take_profit') or 'N/A'}"
        print(f"  Ticket: {t.get('ticket')} | {t.get('symbol')} | {t.get('direction')} | Vol: {t.get('volume')} | Opened: {t.get('opened_at')} | Open Price: {t.get('open_price')} | {tp_sl} | DB: {t.get('db_source')}")
        
    print(f"\nClosed Trades ({len(closed_trades)}):")
    if not closed_trades:
        print("  None")
    for t in closed_trades:
        profit_str = f"${t.get('profit'):.2f}" if t.get('profit') is not None else "N/A"
        reason = t.get("close_reason") or "N/A"
        print(f"  Ticket: {t.get('ticket')} | {t.get('symbol')} | {t.get('direction')} | Vol: {t.get('volume')} | Profit: {profit_str} | Opened: {t.get('opened_at')} | Closed: {t.get('closed_at')} | Reason: {reason} | DB: {t.get('db_source')}")
        
    # Metrics
    if closed_trades:
        total_profit = sum(t.get("profit") or 0.0 for t in closed_trades)
        wins = sum(1 for t in closed_trades if (t.get("profit") or 0.0) > 0.0)
        win_rate = (wins / len(closed_trades)) * 100
        print("\nSummary Metrics (Closed Trades):")
        print(f"  Total Net Profit: ${total_profit:.2f}")
        print(f"  Win Rate: {win_rate:.1f}% ({wins}/{len(closed_trades)})")
    else:
        print("\nSummary Metrics: No closed trades to summarize.")

def main():
    args = parse_args()
    
    # Check if target date is set or defaulting
    target_date = args.date
    trades, resolved_date = extract_trades(target_date, args.all)
    
    # Format output
    if args.format == "text":
        # Redirect stdout to file if requested
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                sys.stdout = f
                print_text(trades, resolved_date, args.all)
                sys.stdout = sys.__stdout__
        else:
            print_text(trades, resolved_date, args.all)
            
    elif args.format == "json":
        output_data = {
            "date": resolved_date if not args.all else "all",
            "total_trades": len(trades),
            "trades": trades
        }
        json_str = json.dumps(output_data, indent=2, default=str)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
        else:
            print(json_str)
            
    elif args.format == "csv":
        if not trades:
            if args.output:
                with open(args.output, "w", encoding="utf-8", newline="") as f:
                    pass
            return
            
        # Extract headers from all keys
        headers = set()
        for t in trades:
            headers.update(t.keys())
        headers = sorted(list(headers))
        
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for t in trades:
                    writer.writerow(t)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=headers)
            writer.writeheader()
            for t in trades:
                writer.writerow(t)

if __name__ == "__main__":
    main()

