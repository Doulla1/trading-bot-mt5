import sqlite3
import glob
import os
import MetaTrader5 as mt5
from datetime import datetime, timedelta

def run():
    if not mt5.initialize():
        print("MT5 init failed")
        return

    # Load history
    now = datetime.now()
    mt5.history_deals_get(now - timedelta(days=60), now + timedelta(days=1))
    
    total_db_profit = 0.0
    total_real_profit = 0.0

    print(f"{'Symbol':<8} | {'Ticket':<10} | {'DB Profit':<10} | {'Real Profit':<12} | {'Reason'}")
    print("-" * 60)

    for db_path in glob.glob('data/*/trading.db'):
        sym = os.path.basename(os.path.dirname(db_path))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Add close_reason column if not exists
        columns = [c[1] for c in conn.execute("PRAGMA table_info(trades)").fetchall()]
        if 'close_reason' not in columns:
            conn.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
            conn.commit()

        trades = conn.execute("SELECT ticket, profit FROM trades WHERE closed_at IS NOT NULL").fetchall()
        for t in trades:
            ticket = t['ticket']
            db_profit = t['profit']
            
            deals = mt5.history_deals_get(position=ticket)
            if not deals:
                print(f"{sym:<8} | {ticket:<10} | {db_profit:<10.2f} | {'NO DEALS':<12} | N/A")
                continue
                
            out_deal = next((d for d in deals if d.entry == 1), None)
            if out_deal:
                real_profit = out_deal.profit + out_deal.commission + out_deal.swap
                
                reason_str = "UNKNOWN"
                if out_deal.reason == mt5.DEAL_REASON_SL:
                    reason_str = "SL"
                elif out_deal.reason == mt5.DEAL_REASON_TP:
                    reason_str = "TP"
                elif out_deal.reason == mt5.DEAL_REASON_CLIENT:
                    reason_str = "CLIENT"
                elif out_deal.reason == mt5.DEAL_REASON_EXPERT:
                    reason_str = "EXPERT"
                
                print(f"{sym:<8} | {ticket:<10} | {db_profit:<10.2f} | {real_profit:<12.2f} | {reason_str}")
                
                # Update DB
                conn.execute("UPDATE trades SET profit = ?, close_price = ?, close_reason = ? WHERE ticket = ?",
                             (real_profit, out_deal.price, reason_str, ticket))
                conn.commit()
                
                total_db_profit += db_profit
                total_real_profit += real_profit
            else:
                print(f"{sym:<8} | {ticket:<10} | {db_profit:<10.2f} | {'NO OUT DEAL':<12} | N/A")
                
    print("-" * 60)
    print(f"Total DB Profit: {total_db_profit:.2f}")
    print(f"Total Real Profit: {total_real_profit:.2f}")
    
    mt5.shutdown()

if __name__ == '__main__':
    run()
