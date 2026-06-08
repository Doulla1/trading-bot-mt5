import MetaTrader5 as mt5
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path(__file__).parent.parent))

import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect to MT5")
    sys.exit(1)

# Query deals for today
now = datetime.now()
start = now - timedelta(days=2)
deals = mt5.history_deals_get(start, now + timedelta(days=1))

if deals is None:
    print("Error calling history_deals_get:", mt5.last_error())
elif len(deals) == 0:
    print("No deals found in the last 2 days.")
else:
    print(f"Found {len(deals)} deals in the last 2 days:")
    for deal in deals:
        d = deal._asdict()
        print(f"Ticket: {d.get('ticket')} | Position ID: {d.get('position_id')} | Symbol: {d.get('symbol')} | Type: {'BUY' if d.get('type') == mt5.DEAL_TYPE_BUY else 'SELL' if d.get('type') == mt5.DEAL_TYPE_SELL else d.get('type')} | Entry: {d.get('entry')} | Price: {d.get('price')} | Profit: {d.get('profit')} | Comment: {d.get('comment')} | Time: {datetime.fromtimestamp(d.get('time'))}")

bridge.disconnect()
