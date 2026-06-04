import sys
from unittest.mock import MagicMock
import platform

if platform.system() != 'Windows':
    # Mock MetaTrader5 on non-Windows platforms since it only works on Windows
    mt5 = MagicMock()
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
    sys.modules['MetaTrader5'] = mt5
