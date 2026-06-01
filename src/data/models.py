"""Modeles de donnees (dataclasses)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    """Enregistrement d'un trade."""
    ticket: int
    symbol: str
    direction: str
    volume: float
    opened_at: datetime
    open_price: float
    stop_loss: float
    take_profit: float
    confidence: int
    reasoning: str
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    profit: Optional[float] = None
    id: Optional[int] = None


@dataclass
class AnalysisLog:
    """Journal d'une analyse IA."""
    timestamp: datetime
    symbol: str
    timeframe: str
    decision_action: str
    decision_confidence: int
    decision_reasoning: str
    screenshot_path: str
    indicators_snapshot: str
    calendar_snapshot: str
    was_executed: bool
    id: Optional[int] = None
