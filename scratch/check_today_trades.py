import sqlite3
import glob
import os
import json

today_str = "2026-06-08"

db_paths = glob.glob("data/*/trading.db")
if os.path.exists("data/trading_bot.db"):
    db_paths.append("data/trading_bot.db")

all_trades = []

for path in db_paths:
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if cursor.fetchone():
            rows = conn.execute("SELECT * FROM trades WHERE opened_at LIKE ? OR closed_at LIKE ?", (f"{today_str}%", f"{today_str}%")).fetchall()
            for r in rows:
                t = dict(r)
                t["db_path"] = path
                all_trades.append(t)
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
all_trades.sort(key=lambda x: x.get('opened_at', ''))

print(f"Total trades found for today: {len(all_trades)}")
for t in all_trades:
    print(f"Ticket: {t['ticket']} | Symbol: {t['symbol']} | Dir: {t['direction']} | Vol: {t['volume']} | Open: {t['open_price']} | Close: {t['close_price']} | Profit: {t['profit']} | Reason: {t['close_reason']}")
