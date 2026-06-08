import sqlite3

db_path = "data/eurusd/trading.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT * FROM trades WHERE ticket = 413383491").fetchone()
if row:
    print("=== EURUSD TRADE 413383491 ===")
    for k in row.keys():
        print(f"  {k}: {row[k]}")
else:
    print("Trade not found.")

conn.close()
