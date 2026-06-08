import sqlite3
import glob
import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Today's date in YYYY-MM-DD
today_str = "2026-06-08"

db_paths = glob.glob("data/*/trading.db")
if os.path.exists("data/trading_bot.db"):
    db_paths.append("data/trading_bot.db")

all_trades = []
all_logs = []

for path in db_paths:
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Query trades
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if cursor.fetchone():
            query = f"SELECT *, ? as db_source FROM trades WHERE opened_at LIKE '{today_str}%' OR closed_at LIKE '{today_str}%'"
            rows = conn.execute(query, (path,)).fetchall()
            for r in rows:
                all_trades.append(dict(r))
                
        # Query logs
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_logs'")
        if cursor.fetchone():
            query = f"SELECT *, ? as db_source FROM analysis_logs WHERE timestamp LIKE '{today_str}%'"
            rows = conn.execute(query, (path,)).fetchall()
            for r in rows:
                all_logs.append(dict(r))
                
        conn.close()
    except Exception as e:
        print(f"Error querying {path}: {e}")

# Deduplicate trades by ticket
dedup_trades = {}
for t in all_trades:
    ticket = t["ticket"]
    if ticket not in dedup_trades or t["closed_at"] is not None:
        dedup_trades[ticket] = t
all_trades = list(dedup_trades.values())

# Sort trades and logs
all_trades.sort(key=lambda x: x.get('opened_at', ''))
all_logs.sort(key=lambda x: x.get('timestamp', ''))

print(f"--- TODAY'S TRADES ({len(all_trades)}) ---")
for t in all_trades:
    print(f"Ticket: {t['ticket']} | Symbol: {t['symbol']} | Direction: {t['direction']} | Vol: {t['volume']}")
    print(f"  Open: {t['open_price']} at {t['opened_at']} | Close: {t['close_price']} at {t['closed_at']} | Profit: {t['profit']} | Reason: {t['close_reason']}")
    print(f"  SL: {t['stop_loss']} | TP: {t['take_profit']}")
    print(f"  Reasoning: {t['reasoning']}")

print(f"\n--- TODAY'S ANALYSIS LOGS ({len(all_logs)}) ---")
for l in all_logs:
    print(f"Time: {l['timestamp']} | Symbol: {l['symbol']} | Action: {l['decision_action']} | Conf: {l['decision_confidence']} | Executed: {l['was_executed']}")
    print(f"  Reasoning: {l['decision_reasoning']}")
