import MetaTrader5 as mt5
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path(__file__).parent.parent))

import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect to MT5")
    sys.exit(1)

acc = bridge.get_account_info()
if acc:
    print(f"Account: {acc.get('login')} | Balance: {acc.get('balance')} | Equity: {acc.get('equity')}")

print("\n--- Open Positions ---")
positions = mt5.positions_get()
if positions is None:
    print("Error calling positions_get:", mt5.last_error())
elif len(positions) == 0:
    print("No open positions.")
else:
    for pos in positions:
        pos_dict = pos._asdict()
        pnl = pos_dict.get('profit')
        # Calculate current price vs open price in pips
        open_p = pos_dict.get('price_open')
        curr_p = pos_dict.get('price_current')
        sym = pos_dict.get('symbol')
        digits = bridge.get_symbol_info(sym).get('digits', 5) if bridge.get_symbol_info(sym) else 5
        
        # Pips calculation: 1 pip = 0.0001 (5 digits) or 0.01 (3 digits)
        multiplier = 10000 if digits in [3, 5] else 100
        pips_diff = (open_p - curr_p) * multiplier if pos_dict.get('type') == mt5.POSITION_TYPE_SELL else (curr_p - open_p) * multiplier
        
        print(f"Ticket: {pos_dict.get('ticket')} | Symbol: {sym} | Type: {'BUY' if pos_dict.get('type') == mt5.POSITION_TYPE_BUY else 'SELL'}")
        print(f"  Volume: {pos_dict.get('volume')} | Open: {open_p} | Current: {curr_p} | Pips: {pips_diff:.1f} pips | P&L: {pnl:.2f} USD")
        print(f"  SL: {pos_dict.get('sl')} | TP: {pos_dict.get('tp')}")

bridge.disconnect()
