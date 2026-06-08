import sqlite3

db_path = "data/eurusd/trading.db"
conn = sqlite3.connect(db_path)

print("Updating EURUSD trade 413383491...")
conn.execute(
    "UPDATE trades SET close_price = 1.15135, profit = -0.42, close_reason = 'EXPERT' WHERE ticket = 413383491"
)
conn.commit()
print("Updated successfully.")

conn.close()
