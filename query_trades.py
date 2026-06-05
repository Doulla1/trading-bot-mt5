import sqlite3
import glob
import os

print('Symbol | Ticket | Profit | Open | Close | Dir | Reason')
for db in glob.glob('data/*/trading.db'):
    sym = os.path.basename(os.path.dirname(db))
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        # Check if close_reason exists
        columns = [col[1] for col in conn.execute('PRAGMA table_info(trades)').fetchall()]
        has_reason = 'close_reason' in columns
        query = f"SELECT ticket, profit, opened_at, closed_at, direction{', close_reason' if has_reason else ''} FROM trades WHERE profit IS NOT NULL ORDER BY closed_at"
        rows = conn.execute(query).fetchall()
        for r in rows:
            reason = r['close_reason'] if has_reason else 'N/A'
            print(f"{sym} | {r['ticket']} | {r['profit']:.2f} | {r['opened_at']} | {r['closed_at']} | {r['direction']} | {reason}")
    except Exception as e:
        print(f"Error querying {sym}: {e}")
