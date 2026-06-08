import sqlite3
import json
import glob
import os

db_paths = glob.glob("data/*/trading.db")
if os.path.exists("data/trading_bot.db"):
    db_paths.append("data/trading_bot.db")

tickets = [413929857, 414387783, 414438643, 414487966, 414514050, 415071089, 415199303]

for ticket in tickets:
    # Find trade symbol and open time
    trade = None
    for path in db_paths:
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM trades WHERE ticket = ?", (ticket,)).fetchone()
            if row:
                trade = dict(row)
                trade["db_path"] = path
                conn.close()
                break
            conn.close()
        except:
            pass
            
    if not trade:
        print(f"Ticket {ticket} not found.")
        continue
        
    symbol = trade["symbol"]
    opened_at = trade["opened_at"]
    direction = trade["direction"]
    db_path = trade["db_path"]
    
    # Query launching log
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    log_row = conn.execute(
        "SELECT * FROM analysis_logs WHERE symbol = ? AND decision_action = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
        (symbol, direction, opened_at)
    ).fetchone()
    if not log_row:
        # Fallback
        log_row = conn.execute(
            "SELECT * FROM analysis_logs WHERE symbol = ? AND was_executed = 1 AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
            (symbol, opened_at)
        ).fetchone()
        
    print(f"\n========================================================")
    print(f"TICKET: {ticket} | SYMBOL: {symbol} | DIR: {direction}")
    print(f"Opened At: {opened_at} | Price: {trade['open_price']} | SL: {trade['stop_loss']} | TP: {trade['take_profit']}")
    if log_row:
        print(f"Log ID: {log_row['id']} | Timestamp: {log_row['timestamp']} | Conf: {log_row['decision_confidence']}")
        print(f"Reasoning: {log_row['decision_reasoning']}")
        ind = json.loads(log_row['indicators_snapshot'])
        print(f"Main Indicators:")
        print(f"  RSI M15: {ind.get('rsi_14')} | H1 RSI: {ind.get('h1_rsi_14')}")
        print(f"  ADX M15: {ind.get('adx_14')} | Regime: {ind.get('market_regime')}")
        print(f"  Ichimoku price vs cloud: {ind.get('ichimoku_price_vs_cloud')}")
        print(f"  Pivots PP: {ind.get('pivot_pp')} | S1: {ind.get('pivot_s1')} | S3: {ind.get('pivot_s3')}")
        print(f"  BB Position %: {ind.get('bb_position_pct')}")
        print(f"  Swing High: {ind.get('market_structure', {}).get('last_swing_high')} | Swing Low: {ind.get('market_structure', {}).get('last_swing_low')}")
    else:
        print("No launching log found.")
    conn.close()
