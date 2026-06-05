"""Tests unitaires pour le module database.py.

Couvre les changements v4.1:
1. get_db(symbol=...) - DB par symbole
2. log_trade_close(symbol=...) - fermeture dans la bonne DB
3. log_trade_open(symbol=...) - ouverture dans la bonne DB (deja existant)
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path


# ============================================================================
# Helpers
# ============================================================================


class TestGetDBSymbol:
    """Tests de get_db() avec le parametre symbol (v4.1)."""

    def test_get_db_with_symbol_returns_different_path_than_default(self):
        """get_db(symbol='GBPUSD') utilise data/gbpusd/trading.db, different de EURUSD."""
        import src.data.database as db_mod

        # Nettoyer le cache de connexions
        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch.object(db_mod.settings, "trading_symbol", "EURUSD"), \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db_mod.get_db(symbol="GBPUSD")
            db_mod.get_db(symbol="EURUSD")

        calls = [call[0][0] for call in mock_connect.call_args_list]
        # Les chemins doivent etre differents
        assert len(calls) >= 2
        assert any("gbpusd" in c.lower() for c in calls), f"Expected gbpusd in paths, got {calls}"
        assert any("eurusd" in c.lower() for c in calls), f"Expected eurusd in paths, got {calls}"
        # Verifier qu'ils sont differents
        gbpusd_paths = [c for c in calls if "gbpusd" in c.lower()]
        eurusd_paths = [c for c in calls if "eurusd" in c.lower()]
        assert gbpusd_paths[0] != eurusd_paths[0]

    def test_get_db_without_symbol_uses_default_db_path(self):
        """get_db() sans symbole utilise settings.db_path (retrocompatibilite)."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_db_path = Path("C:/fake/root/data/eurusd/trading.db")

        with patch.object(type(db_mod.settings), "db_path", new_callable=PropertyMock) as mock_db_path, \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_db_path.return_value = fake_db_path
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db_mod.get_db()

        mock_connect.assert_called_once()
        called_path = mock_connect.call_args[0][0]
        assert "eurusd" in called_path.lower()

    def test_get_db_with_symbol_uses_symbol_dir(self):
        """get_db(symbol='GBPUSD') cree un chemin sous data/gbpusd/."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db_mod.get_db(symbol="GBPUSD")

        mock_connect.assert_called_once()
        called_path = mock_connect.call_args[0][0]
        assert "gbpusd" in called_path.lower()
        assert called_path.endswith("trading.db")

    def test_get_db_same_symbol_returns_cached_connection(self):
        """Deux appels avec le meme symbole retournent la meme connexion (cache)."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            conn1 = db_mod.get_db(symbol="EURUSD")
            conn2 = db_mod.get_db(symbol="EURUSD")

        # sqlite3.connect appele une seule fois pour EURUSD
        eurusd_calls = [c for c in mock_connect.call_args_list if "eurusd" in c[0][0].lower()]
        assert len(eurusd_calls) == 1
        assert conn1 is conn2

    def test_get_db_different_symbols_have_different_connections(self):
        """EURUSD et GBPUSD ont des connexions differentes."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn1 = MagicMock()
            mock_conn2 = MagicMock()
            mock_connect.side_effect = [mock_conn1, mock_conn2]

            conn_eur = db_mod.get_db(symbol="EURUSD")
            conn_gbp = db_mod.get_db(symbol="GBPUSD")

        assert conn_eur is not conn_gbp
        assert len(db_mod._dbs) == 2

    def test_get_db_none_symbol_uses_trading_symbol_default(self):
        """get_db(symbol=None) utilise le trading_symbol courant."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch.object(db_mod.settings, "trading_symbol", "AUDUSD"), \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db_mod.get_db(symbol=None)

        mock_connect.assert_called_once()
        called_path = mock_connect.call_args[0][0]
        assert "audusd" in called_path.lower()

    def test_get_db_symbol_case_insensitive(self):
        """get_db(symbol='GBPUSD') normalise en gbpusd pour le chemin."""
        import src.data.database as db_mod

        db_mod._dbs.clear()

        fake_root = Path("C:/fake/root")

        with patch.object(type(db_mod.settings), "project_root", new_callable=PropertyMock) as mock_root, \
             patch("src.data.database.sqlite3.connect") as mock_connect:
            mock_root.return_value = fake_root
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db_mod.get_db(symbol="GBPUSD")

        mock_connect.assert_called_once()
        called_path = mock_connect.call_args[0][0]
        # Le code fait symbol.lower()
        assert "gbpusd" in called_path


class TestLogTradeCloseSymbol:
    """Tests de log_trade_close() avec le parametre symbol (v4.1)."""

    def test_log_trade_close_passes_symbol_to_get_db(self):
        """log_trade_close(ticket, price, profit, symbol='GBPUSD') appelle get_db(symbol='GBPUSD')."""
        from src.data.database import log_trade_close
        import src.data.database as db_mod

        db_mod._dbs.clear()

        with patch.object(db_mod, "get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_get_db.return_value = mock_conn

            log_trade_close(12345, 1.0900, 50.0, symbol="GBPUSD")

        mock_get_db.assert_called_once_with(symbol="GBPUSD")
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_log_trade_close_without_symbol_passes_none(self):
        """log_trade_close sans symbole appelle get_db(symbol=None) -> fallback settings."""
        from src.data.database import log_trade_close
        import src.data.database as db_mod

        db_mod._dbs.clear()

        with patch.object(db_mod, "get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_get_db.return_value = mock_conn

            log_trade_close(12345, 1.0900, 50.0)

        mock_get_db.assert_called_once_with(symbol=None)


class TestLogTradeOpenSymbol:
    """Tests de log_trade_open() avec le parametre symbol (v4.1)."""

    def test_log_trade_open_passes_symbol_to_get_db(self):
        """log_trade_open appelle get_db(symbol=symbol) pour ecrire dans la bonne DB."""
        from src.data.database import log_trade_open
        import src.data.database as db_mod

        db_mod._dbs.clear()

        with patch.object(db_mod, "get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_get_db.return_value = mock_conn

            log_trade_open(12345, "GBPUSD", "BUY", 0.1, 1.2500, 1.2480, 1.2550, 75, "test")

        mock_get_db.assert_called_once_with(symbol="GBPUSD")
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
