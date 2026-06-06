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


def get_db(symbol: str | None = None) -> sqlite3.Connection:
    """Retourne la connexion SQLite pour un symbole donne.
    v4.1: Accepte un symbole explicite pour eviter la contamination entre DB.
    Utilise un dict keyed par db_path pour que chaque symbole ecrive dans sa propre DB."""
    # v4.1: Si un symbole est fourni explicitement, on l'utilise
    # sinon on utilise le trading_symbol courant (retrocompatibilite)
    if symbol is not None:
        sym_dir = symbol.lower()
        path = str(settings.project_root / "data" / sym_dir / "trading.db")
    else:
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
            profit REAL,
            close_reason TEXT
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

    # Migration automatique pour les bases de donnees existantes
    try:
        db.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
        db.commit()
        logger.info("Migration: Colonne 'close_reason' ajoutee a la table trades.")
    except sqlite3.OperationalError:
        # La colonne existe deja
        pass


def log_analysis(symbol, timeframe, decision, screenshot_path, indicators, calendar_events, was_executed) -> int:
    """Enregistre une analyse IA. Retourne l'ID."""
    db = get_db(symbol=symbol)
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
    """Enregistre l'ouverture d'un trade. Retourne l'ID.
    v4.1: Utilise le symbole explicite pour ecrire dans la bonne DB."""
    db = get_db(symbol=symbol)
    cursor = db.execute(
        """INSERT INTO trades (ticket, symbol, direction, volume, opened_at, open_price, stop_loss, take_profit, confidence, reasoning)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticket, symbol, direction, volume, datetime.now().isoformat(), open_price, stop_loss, take_profit, confidence, reasoning),
    )
    db.commit()
    return cursor.lastrowid


def log_trade_close(ticket, close_price, profit, reason: str = "EXPERT", symbol: str | None = None) -> None:
    """Met a jour un trade avec les infos de fermeture.
    v4.1: Accepte un symbole explicite pour ecrire dans la bonne DB."""
    db = get_db(symbol=symbol)
    db.execute("UPDATE trades SET closed_at = ?, close_price = ?, profit = ?, close_reason = ? WHERE ticket = ? AND closed_at IS NULL",
               (datetime.now().isoformat(), close_price, profit, reason, ticket))
    db.commit()
    logger.info(f"Trade {ticket} ferme dans la DB - Profit: {profit:.2f} - Raison: {reason}")


def get_recent_trades(limit=20, symbol: str | None = None) -> list:
    """Retourne les derniers trades, filtres par symbole si fourni (BUG-get_recent_trades)."""
    db = get_db(symbol=symbol)
    if symbol:
        rows = db.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY opened_at DESC LIMIT ?",
            [symbol, limit]
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", [limit]).fetchall()
    return [dict(r) for r in rows]


def get_statistics(symbol: str | None = None) -> dict:
    """Calcule les statistiques de trading, filtrees par symbole si fourni (INC-B fix)."""
    db = get_db(symbol=symbol)
    stats = {}
    # Filtrer par symbole pour eviter de melanger les stats multi-paires
    sym_filter = "AND symbol = ?" if symbol else ""
    sym_params = [symbol] if symbol else []

    row = db.execute(
        f"SELECT COUNT(*) as total, SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins "
        f"FROM trades WHERE profit IS NOT NULL {sym_filter}",
        sym_params,
    ).fetchone()
    stats["total_closed"] = row[0]
    stats["wins"] = row[1] or 0
    stats["losses"] = stats["total_closed"] - stats["wins"]
    stats["win_rate"] = round(stats["wins"] / stats["total_closed"] * 100, 1) if stats["total_closed"] > 0 else 0

    row = db.execute(
        f"SELECT COALESCE(SUM(profit), 0) FROM trades WHERE profit IS NOT NULL {sym_filter}",
        sym_params,
    ).fetchone()
    stats["total_profit"] = round(row[0], 2)

    log_filter = "AND symbol = ?" if symbol else ""
    row = db.execute(
        f"SELECT COALESCE(AVG(decision_confidence), 0) FROM analysis_logs WHERE 1=1 {log_filter}",
        sym_params,
    ).fetchone()
    stats["avg_confidence"] = round(row[0], 1)

    return stats
