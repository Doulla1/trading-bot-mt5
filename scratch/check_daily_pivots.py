import MetaTrader5 as mt5
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path(__file__).parent.parent))

from src.config import settings
import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect to MT5")
    sys.exit(1)

symbol = "EURUSD"

# Fetch M15 data to see what is in df_m15.iloc[-2]
df_m15 = bridge.get_rates(symbol, "M15", count=200)
if not df_m15.empty:
    print("\n--- M15 candles ---")
    print(df_m15.tail(5))
    h_m15_prev = float(df_m15["high"].iloc[-2])
    l_m15_prev = float(df_m15["low"].iloc[-2])
    c_m15_prev = float(df_m15["close"].iloc[-2])
    print(f"Previous M15 candle: High={h_m15_prev}, Low={l_m15_prev}, Close={c_m15_prev}")
    
    # Calculate M15 pivots
    pp_m15 = (h_m15_prev + l_m15_prev + c_m15_prev) / 3
    s3_m15 = l_m15_prev - 2 * (h_m15_prev - pp_m15)
    print(f"M15 Pivot PP: {pp_m15:.5f}, S3: {s3_m15:.5f}")

# Fetch D1 data to get actual daily candles
df_d1 = bridge.get_rates(symbol, "D1", count=5)
if not df_d1.empty:
    print("\n--- D1 candles ---")
    print(df_d1)
    
    # Let's inspect the last closed daily candle (which is index -2, since index -1 is the current unclosed day)
    h_d1_prev = float(df_d1["high"].iloc[-2])
    l_d1_prev = float(df_d1["low"].iloc[-2])
    c_d1_prev = float(df_d1["close"].iloc[-2])
    prev_date = df_d1.index[-2]
    
    print(f"\nLast Closed Daily Candle (Date: {prev_date}):")
    print(f"High: {h_d1_prev:.5f}, Low: {l_d1_prev:.5f}, Close: {c_d1_prev:.5f}")
    
    # Calculate Classical daily pivots
    pp = (h_d1_prev + l_d1_prev + c_d1_prev) / 3
    r1 = 2 * pp - l_d1_prev
    s1 = 2 * pp - h_d1_prev
    r2 = pp + (h_d1_prev - l_d1_prev)
    s2 = pp - (h_d1_prev - l_d1_prev)
    r3 = h_d1_prev + 2 * (pp - l_d1_prev)
    s3 = l_d1_prev - 2 * (h_d1_prev - pp)
    
    print(f"\nCalculated Classical Daily Pivots:")
    print(f"PP: {pp:.5f}")
    print(f"R1: {r1:.5f} | S1: {s1:.5f}")
    print(f"R2: {r2:.5f} | S2: {s2:.5f}")
    print(f"R3: {r3:.5f} | S3: {s3:.5f}")

bridge.disconnect()
