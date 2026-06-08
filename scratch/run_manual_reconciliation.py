import MetaTrader5 as mt5
import sys
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path(__file__).parent.parent))

import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect to MT5")
    sys.exit(1)

# Connect to eurusd/trading.db (where all three trades are stored as open)
db_path = "data/eurusd/trading.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query open trades in this specific DB
open_trades = conn.execute("SELECT * FROM trades WHERE closed_at IS NULL").fetchall()
print(f"Open trades in {db_path}: {[r['ticket'] for r in open_trades]}")

# Fetch history to fill cache
now = datetime.now()
mt5.history_deals_get(now - timedelta(days=30), now + timedelta(days=1))

for row in open_trades:
    ticket = row["ticket"]
    symbol = row["symbol"]
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        print(f"Position {ticket} ({symbol}) is closed in MT5. Querying deals...")
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            close_deal = next((d for d in deals if d.entry == 1), None)
            if close_deal:
                total_profit = close_deal.profit + close_deal.commission + close_deal.swap
                reason = "EXPERT"
                comment = close_deal.comment.lower() if close_deal.comment else ""
                if "sl" in comment:
                    reason = "SL"
                elif "tp" in comment:
                    reason = "TP"
                
                print(f"Found close deal: Price={close_deal.price}, Profit={total_profit:.2f}, Reason={reason}")
                
                conn.execute(
                    "UPDATE trades SET closed_at = ?, close_price = ?, profit = ?, close_reason = ? WHERE ticket = ? AND closed_at IS NULL",
                    (datetime.now().isoformat(), close_deal.price, total_profit, reason, ticket)
                )
                conn.commit()
                print(f"Updated ticket {ticket} in {db_path}.")
            else:
                print(f"No close deal (entry=1) found for ticket {ticket}.")
        else:
            print(f"No deals found for ticket {ticket}.")
    else:
        print(f"Position {ticket} ({symbol}) is still open in MT5.")

conn.close()
bridge.disconnect()
