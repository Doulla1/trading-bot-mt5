import MetaTrader5 as mt5
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect")
    sys.exit(1)

# Entry: 2026-06-08 10:54:48
# Exit: 2026-06-08 16:43:17
# Let's get M15 bars for USDJPY on 2026-06-08
rates = mt5.copy_rates_from_pos("USDJPY", mt5.TIMEFRAME_M15, 0, 100)
if rates is not None and len(rates) > 0:
    print("=== M15 Rates for USDJPY (during trade window) ===")
    start_time = datetime(2026, 6, 8, 10, 50, tzinfo=timezone.utc).timestamp()
    end_time = datetime(2026, 6, 8, 17, 0, tzinfo=timezone.utc).timestamp()
    
    lowest_low = 999.0
    for r in rates:
        r_time = r[0] # timestamp
        r_open = r[1]
        r_high = r[2]
        r_low = r[3]
        r_close = r[4]
        
        # Log rates within window
        dt = datetime.fromtimestamp(r_time, timezone.utc)
        if start_time <= r_time <= end_time:
            print(f"Time: {dt.strftime('%H:%M')} | O: {r_open:.3f} | H: {r_high:.3f} | L: {r_low:.3f} | C: {r_close:.3f}")
            if r_low < lowest_low:
                lowest_low = r_low
                
    print(f"\nLowest Low Reached in window: {lowest_low:.3f}")
else:
    print("No rates found")

bridge.disconnect()
