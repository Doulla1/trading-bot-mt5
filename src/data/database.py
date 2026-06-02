"""Base de donnees SQLite pour le trading bot."""

import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime
from loguru import logger

from src.config import settings

_dbs: dict[str, sqlite3.Connection] = {}
_db_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    """Retourne la connexion SQLite pour le symbole courant (BUG-1: isolation par symbole).
    Utilise un dict keyed par db_path pour que chaque symbole ecrive dans sa propre DB."""
    path = str(settings.db_path)
    if path not in _dbs:
        with _db_lock:
            if path not in _dbs:
                conn = sqlite3.connect(path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                _init_tables(conn)
                _dbs[path] = conn
                logger.info(f"Base de donnees initialisee: {path}")
    return _dbs[path]


def _init_tables(db: sqlite3.Connection) -> None:
    """Cree les tables si elles n'existent pas."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
            volume REAL NOT NULL,
            opened_at TEXT NOT NULL,
            open_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            confidence INTEGER NOT NULL,
            reasoning TEXT,
            closed_at TEXT,
            close_price REAL,
            profit REAL
        );

        CREATE TABLE IF NOT EXISTS analysis_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            decision_action TEXT NOT NULL,
            decision_confidence INTEGER NOT NULL,
            decision_reasoning TEXT,
            screenshot_path TEXT,
            indicators_snapshot TEXT,
            calendar_snapshot TEXT,
            was_executed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS calendar_cache (
            date TEXT PRIMARY KEY,
            events_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_trades_opened ON trades(opened_at);
        CREATE INDEX IF NOT EXISTS idx_trades_profit ON trades(profit);
        CREATE INDEX IF NOT EXISTS idx_analysis_timestamp ON analysis_logs(timestamp);
    """)
    db.commit()


def log_analysis(symbol, timeframe, decision, screenshot_path, indicators, calendar_events, was_executed) -> int:
    """Enregistre une analyse IA. Retourne l'ID."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO analysis_logs (timestamp, symbol, timeframe, decision_action, decision_confidence, decision_reasoning, screenshot_path, indicators_snapshot, calendar_snapshot, was_executed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), symbol, timeframe, decision.get("action", "UNKNOWN"),
         decision.get("confidence", 0), decision.get("reasoning", ""), screenshot_path,
         json.dumps(indicators, default=str), json.dumps(calendar_events, default=str), 1 if was_executed else 0),
    )
    db.commit()
    return cursor.lastrowid


def log_trade_open(ticket, symbol, direction, volume, open_price, stop_loss, take_profit, confidence, reasoning) -> int:
    """Enregistre l'ouverture d'un trade. Retourne l'ID."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO trades (ticket, symbol, direction, volume, opened_at, open_price, stop_loss, take_profit, confidence, reasoning)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticket, symbol, direction, volume, datetime.now().isoformat(), open_price, stop_loss, take_profit, confidence, reasoning),
    )
    db.commit()
    return cursor.lastrowid


def log_trade_close(ticket, close_price, profit) -> None:
    """Met a jour un trade avec les infos de fermeture."""
    db = get_db()
    db.execute("UPDATE trades SET closed_at = ?, close_price = ?, profit = ? WHERE ticket = ? AND closed_at IS NULL",
               (datetime.now().isoformat(), close_price, profit, ticket))
    db.commit()
    logger.info(f"Trade {ticket} ferme dans la DB - Profit: {profit:.2f}")


def get_recent_trades(limit=20, symbol: str | None = None) -> list:
    """Retourne les derniers trades, filtres par symbole si fourni (BUG-get_recent_trades)."""
    db = get_db()
    if symbol:
        rows = db.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY opened_at DESC LIMIT ?",
            [symbol, limit]
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", [limit]).fetchall()
    return [dict(r) for r in rows]


def get_statistics() -> dict:
    """Calcule les statistiques de trading."""
    db = get_db()
    stats = {}
    row = db.execute("SELECT COUNT(*) as total, SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins FROM trades WHERE profit IS NOT NULL").fetchone()
    stats["total_closed"] = row[0]
    stats["wins"] = row[1] or 0
    stats["losses"] = stats["total_closed"] - stats["wins"]
    stats["win_rate"] = round(stats["wins"] / stats["total_closed"] * 100, 1) if stats["total_closed"] > 0 else 0

    row = db.execute("SELECT COALESCE(SUM(profit), 0) FROM trades WHERE profit IS NOT NULL").fetchone()
    stats["total_profit"] = round(row[0], 2)

    row = db.execute("SELECT COALESCE(AVG(decision_confidence), 0) FROM analysis_logs").fetchone()
    stats["avg_confidence"] = round(row[0], 1)

    return stats
