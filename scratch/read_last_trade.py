import sys
from pathlib import Path
import MetaTrader5 as mt5

sys.path.append(str(Path(__file__).parent.parent))

from src.ai.strategy import _get_atr_based_sl_tp, _ATR_SL_CONFIG
import src.mt5.bridge as bridge

if not bridge.connect():
    print("Could not connect to MT5")
    sys.exit(1)

indicators = {"atr_14": 0.00081}
deepseek_sl = 20
deepseek_tp = 30

print("--- Testing GBPUSD SL/TP ---")
sl, tp = _get_atr_based_sl_tp("GBPUSD", indicators, deepseek_sl, deepseek_tp)
print(f"GBPUSD: Computed SL={sl}, TP={tp}")
print(f"Config: {_ATR_SL_CONFIG.get('GBPUSD')}")

print("\n--- Testing AUDUSD SL/TP ---")
indicators_aud = {"atr_14": 0.00067}
sl_aud, tp_aud = _get_atr_based_sl_tp("AUDUSD", indicators_aud, 10, 15)
print(f"AUDUSD: Computed SL={sl_aud}, TP={tp_aud}")
print(f"Config: {_ATR_SL_CONFIG.get('AUDUSD')}")

bridge.disconnect()
