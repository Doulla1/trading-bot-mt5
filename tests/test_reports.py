"""Tests unitaires pour le module reports (mailer, generator, analyzer, daily_report).

Couvre l'envoi d'email, la generation de rapport, l'analyse DeepSeek,
l'orchestration du rapport journalier et le formatage HTML.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from src.config import settings
from src.reports.mailer import send_email
from src.reports.generator import (
    _discover_symbol_dbs,
    _compute_symbol_stats,
    _compute_global_stats,
    _render_html,
    generate_daily_report,
    get_symbols_detail_text,
)
from src.reports.analyzer import analyze_daily_results
from src.reports.daily_report import send_daily_report, _format_analysis_html, _bold_format


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings(monkeypatch):
    """Override les settings pour les tests (API secret, URL, emails)."""
    monkeypatch.setattr("src.reports.mailer.settings.mailer_api_secret", "test-secret-12345")
    monkeypatch.setattr("src.reports.mailer.settings.mailer_api_url", "https://mail.example.com/api/v1/emails")
    monkeypatch.setattr("src.reports.mailer.settings.report_sender_name", "Test Sender")
    return monkeypatch


@pytest.fixture
def sample_trades():
    """Jeu de trades de test pour les calculs de stats."""
    return [
        {
            "ticket": 1, "symbol": "EURUSD", "direction": "BUY", "volume": 0.1,
            "open_price": 1.0850, "opened_at": "2026-06-01T08:00:00",
            "closed_at": "2026-06-01T10:30:00", "profit": 45.50, "confidence": 82,
            "stop_loss": 1.0820, "take_profit": 1.0900,
        },
        {
            "ticket": 2, "symbol": "EURUSD", "direction": "SELL", "volume": 0.1,
            "open_price": 1.0870, "opened_at": "2026-06-01T09:00:00",
            "closed_at": "2026-06-01T11:00:00", "profit": -22.30, "confidence": 75,
            "stop_loss": 1.0900, "take_profit": 1.0820,
        },
        {
            "ticket": 3, "symbol": "EURUSD", "direction": "BUY", "volume": 0.2,
            "open_price": 1.0860, "opened_at": "2026-06-01T13:00:00",
            "closed_at": "2026-06-01T14:15:00", "profit": 78.90, "confidence": 90,
            "stop_loss": 1.0830, "take_profit": 1.0920,
        },
        {
            "ticket": 4, "symbol": "EURUSD", "direction": "BUY", "volume": 0.1,
            "open_price": 1.0890, "opened_at": "2026-06-01T15:00:00",
            "closed_at": None, "profit": None, "confidence": 68,
            "stop_loss": 1.0860, "take_profit": 1.0950,
        },
    ]


@pytest.fixture
def sample_open_trade():
    """Trade encore ouvert (profit=None)."""
    return {
        "ticket": 5, "symbol": "GBPUSD", "direction": "SELL", "volume": 0.1,
        "open_price": 1.2650, "opened_at": "2026-06-01T16:00:00",
        "closed_at": None, "profit": None, "confidence": 72,
        "stop_loss": 1.2680, "take_profit": 1.2600,
    }


@pytest.fixture
def sample_symbols_data(sample_trades, sample_open_trade):
    """Donnees multi-symboles pour les tests d'orchestration."""
    eur_trades = [t for t in sample_trades if t["symbol"] == "EURUSD"]
    return {
        "EURUSD": {
            "stats": _compute_symbol_stats(eur_trades),
            "trades": eur_trades,
        },
        "GBPUSD": {
            "stats": _compute_symbol_stats([sample_open_trade]),
            "trades": [sample_open_trade],
        },
    }


@pytest.fixture
def sample_global_stats(sample_trades, sample_open_trade):
    """Stats globales de test."""
    all_trades = sample_trades + [sample_open_trade]
    symbols_data = {
        "EURUSD": {"stats": _compute_symbol_stats(sample_trades)},
        "GBPUSD": {"stats": _compute_symbol_stats([sample_open_trade])},
    }
    return _compute_global_stats(all_trades, symbols_data)


# ---------------------------------------------------------------------------
# TestMailer: send_email
# ---------------------------------------------------------------------------


class TestMailerSendEmail:
    """Tests du client HTTP d'envoi d'email."""

    def test_successful_send_returns_true(self, mock_settings):
        """Envoi reussi (201) doit retourner True."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "abc-123"}

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is True
        mock_client.post.assert_called_once()

    def test_missing_api_secret_returns_false(self, mock_settings):
        """Secret API manquant doit retourner False sans appeler l'API."""
        mock_settings.setattr("src.reports.mailer.settings.mailer_api_secret", "")

        with patch("src.reports.mailer.httpx.Client") as mock_client_cls:
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False
        mock_client_cls.assert_not_called()

    def test_rate_limit_429_returns_false(self, mock_settings):
        """Rate limit (429) doit retourner False."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too many requests"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False

    def test_invalid_secret_401_returns_false(self, mock_settings):
        """Secret invalide (401) doit retourner False."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False

    def test_server_error_500_returns_false(self, mock_settings):
        """Erreur serveur (500) doit retourner False."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False

    def test_timeout_returns_false(self, mock_settings):
        """Timeout HTTP doit retourner False."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False

    def test_connection_error_returns_false(self, mock_settings):
        """Erreur de connexion doit retourner False."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.side_effect = Exception("Connection refused")

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is False

    def test_recipient_name_in_payload(self, mock_settings):
        """Le nom du destinataire doit etre inclus dans le payload."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "abc-456"}

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email(
                "test@example.com", "Sujet", "<p>Body</p>",
                recipient_name="Jean Dupont",
            )

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["recipient_name"] == "Jean Dupont"

    def test_sender_name_from_config_when_not_provided(self, mock_settings):
        """Si sender_name non fourni, utiliser la config."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "abc-789"}

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email("test@example.com", "Sujet", "<p>Body</p>")

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["sender_name"] == "Test Sender"

    def test_explicit_sender_name_overrides_config(self, mock_settings):
        """Sender name explicite doit remplacer la config."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "abc-000"}

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            result = send_email(
                "test@example.com", "Sujet", "<p>Body</p>",
                sender_name="Custom Sender",
            )

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["sender_name"] == "Custom Sender"

    def test_headers_include_api_secret_and_content_type(self, mock_settings):
        """Les headers doivent contenir X-API-Secret et Content-Type."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "abc-headers"}

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.post.return_value = mock_response

        with patch("src.reports.mailer.httpx.Client", return_value=mock_client):
            send_email("test@example.com", "Sujet", "<p>Body</p>")

        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert headers["X-API-Secret"] == "test-secret-12345"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# TestGenerator: _discover_symbol_dbs
# ---------------------------------------------------------------------------


class TestDiscoverSymbolDbs:
    """Tests de la decouverte des bases par symbole."""

    def test_empty_data_dir_returns_empty(self, tmp_path):
        """Dossier data vide -> liste vide."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            result = _discover_symbol_dbs()
        assert result == []

    def test_no_trading_db_files_returns_empty(self, tmp_path):
        """Dossiers de symboles sans trading.db -> liste vide."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "eurusd").mkdir()
        (data_dir / "gbpusd").mkdir()
        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            result = _discover_symbol_dbs()
        assert result == []

    def test_finds_symbol_dbs(self, tmp_path):
        """Doit trouver les trading.db dans chaque dossier symbole."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        for sym in ["eurusd", "gbpusd", "usdjpy"]:
            sym_dir = data_dir / sym
            sym_dir.mkdir()
            (sym_dir / "trading.db").touch()

        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            result = _discover_symbol_dbs()

        assert len(result) == 3
        symbols = {sym for sym, _ in result}
        assert symbols == {"EURUSD", "GBPUSD", "USDJPY"}

    def test_skips_dot_folders(self, tmp_path):
        """Les dossiers commencant par '.' doivent etre ignores."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "eurusd").mkdir()
        (data_dir / "eurusd" / "trading.db").touch()
        (data_dir / ".git").mkdir()
        (data_dir / ".git" / "trading.db").touch()  # Should be ignored

        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            result = _discover_symbol_dbs()

        assert len(result) == 1
        assert result[0][0] == "EURUSD"

    def test_skips_files_in_data_dir(self, tmp_path):
        """Les fichiers (pas des dossiers) dans data/ doivent etre ignores."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "README.md").touch()
        (data_dir / "eurusd").mkdir()
        (data_dir / "eurusd" / "trading.db").touch()

        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            result = _discover_symbol_dbs()

        assert len(result) == 1

# ---------------------------------------------------------------------------
# TestGenerator: _compute_symbol_stats
# ---------------------------------------------------------------------------


class TestComputeSymbolStats:
    """Tests du calcul des statistiques par symbole."""

    def test_basic_stats(self, sample_trades):
        """Stats de base sur un jeu de trades mixte."""
        stats = _compute_symbol_stats(sample_trades)

        assert stats["total_trades"] == 4
        assert stats["closed"] == 3
        assert stats["open"] == 1
        assert stats["wins"] == 2
        assert stats["losses"] == 1
        assert stats["win_rate"] == pytest.approx(66.7, abs=0.1)

    def test_total_profit(self, sample_trades):
        """Le profit total est la somme des profits des trades fermes."""
        stats = _compute_symbol_stats(sample_trades)
        assert stats["total_profit"] == pytest.approx(102.10, abs=0.01)

    def test_best_and_worst_trade(self, sample_trades):
        """Meilleur et pire trade identifies correctement."""
        stats = _compute_symbol_stats(sample_trades)
        assert stats["best_trade"] == 78.90
        assert stats["worst_trade"] == -22.30

    def test_avg_profit(self, sample_trades):
        """Profit moyen calcule sur les trades fermes."""
        stats = _compute_symbol_stats(sample_trades)
        expected = (45.50 - 22.30 + 78.90) / 3
        assert stats["avg_profit"] == pytest.approx(expected, abs=0.01)

    def test_avg_confidence(self, sample_trades):
        """Confiance moyenne sur tous les trades avec confidence."""
        stats = _compute_symbol_stats(sample_trades)
        expected = (82 + 75 + 90 + 68) / 4
        assert stats["avg_confidence"] == pytest.approx(expected, abs=0.1)

    def test_avg_duration_minutes(self, sample_trades):
        """Duree moyenne en minutes des trades fermes."""
        stats = _compute_symbol_stats(sample_trades)
        # Trade 1: 150 min, Trade 2: 120 min, Trade 3: 75 min
        expected = (150 + 120 + 75) / 3
        assert stats["avg_duration_min"] == pytest.approx(expected, abs=0.1)

    def test_empty_trades_list(self):
        """Liste de trades vide -> stats a zero."""
        stats = _compute_symbol_stats([])
        assert stats["total_trades"] == 0
        assert stats["closed"] == 0
        assert stats["open"] == 0
        assert stats["wins"] == 0
        assert stats["losses"] == 0
        assert stats["win_rate"] == 0
        assert stats["total_profit"] == 0

    def test_all_wins(self):
        """Tous les trades gagnants -> win_rate 100%."""
        trades = [
            {"ticket": 1, "profit": 10.0, "opened_at": "2026-06-01T08:00", "closed_at": "2026-06-01T09:00", "confidence": 80},
            {"ticket": 2, "profit": 20.0, "opened_at": "2026-06-01T10:00", "closed_at": "2026-06-01T11:00", "confidence": 90},
        ]
        stats = _compute_symbol_stats(trades)
        assert stats["win_rate"] == 100.0
        assert stats["wins"] == 2
        assert stats["losses"] == 0

    def test_all_losses(self):
        """Tous les trades perdants -> win_rate 0%."""
        trades = [
            {"ticket": 1, "profit": -10.0, "opened_at": "2026-06-01T08:00", "closed_at": "2026-06-01T09:00", "confidence": 70},
            {"ticket": 2, "profit": -5.0, "opened_at": "2026-06-01T10:00", "closed_at": "2026-06-01T11:00", "confidence": 65},
        ]
        stats = _compute_symbol_stats(trades)
        assert stats["win_rate"] == 0.0
        assert stats["wins"] == 0
        assert stats["losses"] == 2

    def test_only_open_trades(self, sample_open_trade):
        """Que des trades ouverts -> 0 closed, 0 win_rate."""
        stats = _compute_symbol_stats([sample_open_trade])
        assert stats["total_trades"] == 1
        assert stats["closed"] == 0
        assert stats["open"] == 1
        assert stats["wins"] == 0
        assert stats["win_rate"] == 0

    def test_break_even_trade_counted_as_breakeven(self):
        """Un trade a profit=0 est compte comme breakeven, pas comme perdant."""
        trades = [
            {"ticket": 1, "profit": 10.0, "opened_at": "2026-06-01T08:00", "closed_at": "2026-06-01T09:00", "confidence": 80},
            {"ticket": 2, "profit": 0.0, "opened_at": "2026-06-01T10:00", "closed_at": "2026-06-01T11:00", "confidence": 70},
        ]
        stats = _compute_symbol_stats(trades)
        assert stats["wins"] == 1
        assert stats["losses"] == 0
        assert stats["breakeven"] == 1

# ---------------------------------------------------------------------------
# TestGenerator: _compute_global_stats
# ---------------------------------------------------------------------------


class TestComputeGlobalStats:
    """Tests du calcul des statistiques globales."""

    def test_aggregates_multiple_symbols(self, sample_trades, sample_open_trade):
        """Agregation correcte sur plusieurs symboles."""
        all_trades = sample_trades + [sample_open_trade]
        symbols_data = {
            "EURUSD": {"stats": _compute_symbol_stats(sample_trades)},
            "GBPUSD": {"stats": _compute_symbol_stats([sample_open_trade])},
        }
        stats = _compute_global_stats(all_trades, symbols_data)

        assert stats["total_trades"] == 5
        assert stats["closed"] == 3
        assert stats["open"] == 2
        assert stats["symbols_count"] == 2

    def test_symbols_count(self, sample_trades):
        """symbols_count reflete le nombre de paires."""
        symbols_data = {"EURUSD": {"stats": _compute_symbol_stats(sample_trades)}}
        stats = _compute_global_stats(sample_trades, symbols_data)
        assert stats["symbols_count"] == 1

    def test_empty_returns_zeros(self):
        """Aucun trade -> toutes les stats a zero."""
        stats = _compute_global_stats([], {})
        assert stats["total_trades"] == 0
        assert stats["closed"] == 0
        assert stats["open"] == 0
        assert stats["total_profit"] == 0
        assert stats["win_rate"] == 0
        assert stats["avg_duration"] == "N/A"
        assert stats["symbols_count"] == 0

    def test_avg_duration_format(self, sample_trades):
        """La duree moyenne globale est formatee avec 'min'."""
        symbols_data = {"EURUSD": {"stats": _compute_symbol_stats(sample_trades)}}
        stats = _compute_global_stats(sample_trades, symbols_data)
        assert "min" in stats["avg_duration"]

# ---------------------------------------------------------------------------
# TestGenerator: generate_daily_report (integration)
# ---------------------------------------------------------------------------


class TestGenerateDailyReport:
    """Tests de la fonction principale generate_daily_report."""

    def test_empty_report_no_symbols(self, tmp_path):
        """Rapport vide quand aucun symbole n'a de trading.db."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            report = generate_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert report["has_trades"] is False
        assert report["trades"] == []
        assert report["symbols"] == {}
        assert report["stats"]["total_trades"] == 0
        assert "Aucun trade aujourd'hui" in report["html"]

    def test_report_with_trades(self, tmp_path, sample_trades):
        """Rapport avec des trades dans la base."""
        data_dir = tmp_path / "data"
        eur_dir = data_dir / "eurusd"
        eur_dir.mkdir(parents=True)

        # Creer la DB avec des trades
        conn = sqlite3.connect(str(eur_dir / "trading.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                ticket INTEGER, symbol TEXT, direction TEXT, volume REAL,
                open_price REAL, opened_at TEXT, closed_at TEXT,
                profit REAL, confidence INTEGER, stop_loss REAL, take_profit REAL
            )
        """)
        for t in sample_trades:
            conn.execute(
                "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [t["ticket"], t["symbol"], t["direction"], t["volume"],
                 t["open_price"], t["opened_at"], t["closed_at"],
                 t["profit"], t["confidence"], t["stop_loss"], t["take_profit"]],
            )
        conn.commit()
        conn.close()

        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            report = generate_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert report["has_trades"] is True
        assert len(report["trades"]) == 4
        assert "EURUSD" in report["symbols"]
        assert report["stats"]["total_trades"] == 4
        assert "EURUSD" in report["html"]

    def test_db_error_handled_gracefully(self, tmp_path):
        """Erreur de lecture d'une DB ne doit pas planter le rapport."""
        data_dir = tmp_path / "data"
        eur_dir = data_dir / "eurusd"
        eur_dir.mkdir(parents=True)
        # Creer un fichier corrompu au lieu d'une vraie DB
        (eur_dir / "trading.db").write_text("not a valid sqlite database")

        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            report = generate_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert report["has_trades"] is False
        assert report["trades"] == []

    def test_date_defaults_to_today(self, tmp_path):
        """Si date=None, utiliser aujourd'hui UTC."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        with patch.object(type(settings), "project_root", new_callable=PropertyMock) as mock_root:
            mock_root.return_value = tmp_path
            report = generate_daily_report()

        assert isinstance(report, dict)
        assert "has_trades" in report

# ---------------------------------------------------------------------------
# TestGenerator: get_symbols_detail_text
# ---------------------------------------------------------------------------


class TestGetSymbolsDetailText:
    """Tests de la generation du texte detaille par symbole."""

    def test_formats_multiple_symbols(self, sample_symbols_data):
        """Formatage correct pour plusieurs symboles."""
        text = get_symbols_detail_text(sample_symbols_data)
        assert "EURUSD" in text
        assert "GBPUSD" in text
        assert "WR:" in text
        assert "P&L:" in text

    def test_empty_symbols_returns_default(self):
        """Aucun symbole -> message par defaut."""
        text = get_symbols_detail_text({})
        assert text == "Aucun trade aujourd'hui."

    def test_includes_win_rate_and_pnl(self, sample_symbols_data):
        """Le texte doit contenir le win rate et le P&L."""
        text = get_symbols_detail_text(sample_symbols_data)
        eur_line = [l for l in text.split("\n") if "EURUSD" in l][0]
        assert "66.7%" in eur_line
        assert "102.10" in eur_line

# ---------------------------------------------------------------------------
# TestAnalyzer: analyze_daily_results
# ---------------------------------------------------------------------------


class TestAnalyzeDailyResults:
    """Tests de l'analyse DeepSeek V4 Pro."""

    @pytest.fixture
    def sample_stats(self):
        return {
            "total_trades": 4, "wins": 2, "losses": 1,
            "win_rate": 66.7, "total_profit": 102.10,
            "best_trade": 78.90, "worst_trade": -22.30,
            "avg_profit": 34.03, "avg_duration": "115 min",
            "avg_confidence": 78,
        }

    def test_successful_analysis(self, monkeypatch, sample_stats, sample_trades):
        """Analyse reussie: doit retourner le texte DeepSeek."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Analyse: bonne journee de trading."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.reports.analyzer.OpenAI", return_value=mock_client):
            result = analyze_daily_results(sample_stats, sample_trades, "EURUSD: 4 trades")

        assert result == "Analyse: bonne journee de trading."
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["model"] == "deepseek-v4-pro"

    def test_missing_api_key_returns_fallback(self, monkeypatch, sample_stats, sample_trades):
        """Cle API manquante -> message de fallback."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "")

        with patch("src.reports.analyzer.OpenAI") as mock_openai:
            result = analyze_daily_results(sample_stats, sample_trades, "")

        assert "Analyse DeepSeek non disponible" in result
        mock_openai.assert_not_called()

    def test_api_error_returns_error_message(self, monkeypatch, sample_stats, sample_trades):
        """Erreur API -> message d'erreur formate."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "sk-test-key")

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API rate limit")

        with patch("src.reports.analyzer.OpenAI", return_value=mock_client):
            result = analyze_daily_results(sample_stats, sample_trades, "")

        assert "Analyse DeepSeek indisponible" in result
        assert "API rate limit" in result

    def test_limits_trades_to_50(self, monkeypatch, sample_stats):
        """Ne doit pas envoyer plus de 50 trades au prompt."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "sk-test-key")

        many_trades = [
            {"ticket": i, "symbol": "EURUSD", "direction": "BUY",
             "opened_at": "2026-06-01T08:00:00", "profit": 10.0}
            for i in range(100)
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Analyse."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.reports.analyzer.OpenAI", return_value=mock_client):
            result = analyze_daily_results(sample_stats, many_trades, "")

        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][1]["content"]
        # Should have at most 50 trade lines (plus headers)
        trade_lines = [l for l in prompt.split("\n") if l.strip().startswith("  -")]
        assert len(trade_lines) <= 50

    def test_empty_content_returns_fallback(self, monkeypatch, sample_stats, sample_trades):
        """Reponse vide -> fallback apres retry."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""  # Empty both times

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.reports.analyzer.OpenAI", return_value=mock_client):
            result = analyze_daily_results(sample_stats, sample_trades, "")

        assert "non disponible" in result
        assert "2 gagnants" in result

    def test_no_trades_prompt_still_works(self, monkeypatch, sample_stats):
        """Prompt avec Aucun trade aujourd'hui fonctionne."""
        monkeypatch.setattr("src.reports.analyzer.settings.deepseek_api_key", "sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Pas de trades, journee calme."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.reports.analyzer.OpenAI", return_value=mock_client):
            result = analyze_daily_results(sample_stats, [], "")

        assert result == "Pas de trades, journee calme."

# ---------------------------------------------------------------------------
# TestDailyReport: send_daily_report (orchestrateur)
# ---------------------------------------------------------------------------


class TestSendDailyReport:
    """Tests de l'orchestrateur du rapport journalier."""

    @pytest.fixture
    def mock_dependencies(self):
        """Fixture pour mocker les 3 sous-fonctions appelees par send_daily_report."""
        with patch("src.reports.daily_report.generate_daily_report") as mock_gen, \
             patch("src.reports.daily_report.get_symbols_detail_text") as mock_detail, \
             patch("src.reports.daily_report.analyze_daily_results") as mock_analyze, \
             patch("src.reports.daily_report.send_email") as mock_send:
            yield mock_gen, mock_detail, mock_analyze, mock_send

    @pytest.fixture
    def sample_report_data(self, sample_global_stats, sample_trades, sample_symbols_data):
        return {
            "stats": sample_global_stats,
            "trades": sample_trades,
            "symbols": sample_symbols_data,
            "html": "<html>##ANALYSIS_PLACEHOLDER##</html>",
            "has_trades": True,
        }

    def test_full_flow_success(self, mock_dependencies, sample_report_data, monkeypatch):
        """Orchestration complete: generation -> analyse -> format -> envoi."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")
        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_name", "User")

        mock_gen.return_value = sample_report_data
        mock_detail.return_value = "EURUSD: 4 trades"
        mock_analyze.return_value = "**Resume**\nBonne journee."
        mock_send.return_value = True

        result = send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert result is True
        mock_gen.assert_called_once()
        mock_analyze.assert_called_once()
        mock_send.assert_called_once()

        # Verifier que l'analyse a ete injectee dans le HTML
        call_args = mock_send.call_args
        assert "##ANALYSIS_PLACEHOLDER##" not in call_args[1]["body_html"]
        assert "<h3" in call_args[1]["body_html"]

    def test_no_recipient_returns_false(self, mock_dependencies, sample_report_data, monkeypatch):
        """Pas de destinataire configure -> retourne False."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "")

        mock_gen.return_value = sample_report_data
        mock_detail.return_value = ""
        mock_analyze.return_value = "Analyse."

        result = send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert result is False
        mock_send.assert_not_called()

    def test_mailer_fails_returns_false(self, mock_dependencies, sample_report_data, monkeypatch):
        """Echec de l'envoi email -> retourne False."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")

        mock_gen.return_value = sample_report_data
        mock_detail.return_value = ""
        mock_analyze.return_value = "Analyse."
        mock_send.return_value = False

        result = send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert result is False
        mock_send.assert_called_once()

    def test_subject_positive_profit(self, mock_dependencies, sample_report_data, monkeypatch):
        """Sujet avec P&L positif (signe +)."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")

        sample_report_data["stats"]["total_profit"] = 150.00
        mock_gen.return_value = sample_report_data
        mock_detail.return_value = "EURUSD: 4 trades"
        mock_analyze.return_value = "Ok"
        mock_send.return_value = True

        send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        subject = mock_send.call_args[1]["subject"]
        assert "+150.00" in subject
        assert "01/06/2026" in subject

    def test_subject_negative_profit(self, mock_dependencies, sample_report_data, monkeypatch):
        """Sujet avec P&L negatif (pas de signe +)."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")

        sample_report_data["stats"]["total_profit"] = -50.00
        mock_gen.return_value = sample_report_data
        mock_detail.return_value = ""
        mock_analyze.return_value = "Ok"
        mock_send.return_value = True

        send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        subject = mock_send.call_args[1]["subject"]
        assert "-50.00" in subject
        assert "+-50.00" not in subject  # Pas de double signe

    def test_recipient_name_in_email(self, mock_dependencies, sample_report_data, monkeypatch):
        """Le nom du destinataire configure est passe a send_email."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")
        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_name", "Alice")

        mock_gen.return_value = sample_report_data
        mock_detail.return_value = ""
        mock_analyze.return_value = "Ok"
        mock_send.return_value = True

        send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        assert mock_send.call_args[1]["recipient_name"] == "Alice"

    def test_placeholder_replaced_in_html(self, mock_dependencies, sample_report_data, monkeypatch):
        """Le placeholder ##ANALYSIS_PLACEHOLDER## est remplace par l'analyse HTML."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies

        monkeypatch.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")

        sample_report_data["html"] = "<div>Before</div>##ANALYSIS_PLACEHOLDER##<div>After</div>"
        mock_gen.return_value = sample_report_data
        mock_detail.return_value = ""
        mock_analyze.return_value = "Analyse."
        mock_send.return_value = True

        send_daily_report(datetime(2026, 6, 1, tzinfo=timezone.utc))

        body = mock_send.call_args[1]["body_html"]
        assert "##ANALYSIS_PLACEHOLDER##" not in body
        assert "<div>Before</div>" in body
        assert "<div>After</div>" in body

    def test_date_defaults_to_today(self, mock_dependencies, mock_settings):
        """Si date=None, utiliser aujourd'hui UTC."""
        mock_gen, mock_detail, mock_analyze, mock_send = mock_dependencies
        mock_settings.setattr("src.reports.daily_report.settings.report_recipient_email", "user@example.com")
        mock_settings.setattr("src.reports.daily_report.settings.report_recipient_name", "")

        mock_gen.return_value = {
            "stats": {"total_trades": 0, "total_profit": 0, "win_rate": 0},
            "trades": [], "symbols": {}, "html": "##ANALYSIS_PLACEHOLDER##", "has_trades": False,
        }
        mock_detail.return_value = "Aucun trade aujourd'hui."
        mock_analyze.return_value = ""
        mock_send.return_value = True

        result = send_daily_report()
        assert result is True
        mock_gen.assert_called_once()

# ---------------------------------------------------------------------------
# TestFormatAnalysisHtml: _format_analysis_html + _bold_format
# ---------------------------------------------------------------------------


class TestBoldFormat:
    """Tests de la conversion markdown bold -> HTML strong."""

    def test_single_bold(self):
        """Un seul **texte** -> <strong>texte</strong>."""
        result = _bold_format("Ceci est **important** dans le texte.")
        assert "<strong style='color: #f1f5f9;'>important</strong>" in result

    def test_multiple_bold(self):
        """Plusieurs **texte** dans la meme ligne."""
        result = _bold_format("**Premier** et **Deuxieme**.")
        assert result.count("<strong") == 2

    def test_no_bold_unchanged(self):
        """Texte sans bold -> inchange."""
        result = _bold_format("Texte normal sans formatage.")
        assert result == "Texte normal sans formatage."
        assert "<strong" not in result

    def test_empty_string(self):
        """Chaine vide -> chaine vide."""
        assert _bold_format("") == ""


class TestFormatAnalysisHtml:
    """Tests de la conversion markdown -> HTML pour l'analyse."""

    def test_section_titles_become_h3(self):
        """Les titres **Titre** deviennent des <h3>."""
        text = "**Resume**\nContenu du resume."
        result = _format_analysis_html(text)
        assert "<h3" in result
        assert "Resume" in result

    def test_list_items_become_li(self):
        """Les elements de liste (- item) deviennent des <li>."""
        text = "**Recommandations**\n- Augmenter le stop loss\n- Reduire le volume"
        result = _format_analysis_html(text)
        assert "<ul" in result
        assert "<li>" in result
        assert "Augmenter le stop loss" in result
        assert "</ul>" in result

    def test_asterisk_list_items(self):
        """Les elements de liste avec * sont aussi supportes."""
        text = "**Forces**\n* Bon win rate\n* Execution rapide"
        result = _format_analysis_html(text)
        assert "<li>" in result
        assert "Bon win rate" in result

    def test_paragraphs_wrapped_in_p(self):
        """Le texte normal est wrappe dans des <p>."""
        text = "Ceci est un paragraphe.\n\nEt un autre."
        result = _format_analysis_html(text)
        assert "<p" in result
        assert "Ceci est un paragraphe." in result

    def test_html_special_chars_escaped(self):
        """Les caracteres HTML sont echappes."""
        text = "Test <script>alert('xss')</script> & symboles > <"
        result = _format_analysis_html(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&amp;" in result

    def test_empty_input(self):
        """Texte vide -> HTML minimal (un <br>)."""
        result = _format_analysis_html("")
        assert result == "<br>"

    def test_whitespace_only_lines(self):
        """Lignes avec seulement des espaces -> <br>."""
        result = _format_analysis_html("Ligne 1\n   \nLigne 2")
        assert "<br>" in result

    def test_full_analysis_format(self):
        """Formatage d'une analyse complete type DeepSeek."""
        text = (
            "**Resume**\n"
            "Bonne journee avec 3 trades gagnants.\n\n"
            "**Forces**\n"
            "- EURUSD a bien performe\n"
            "- Bonne gestion du risque\n\n"
            "**Faiblesses**\n"
            "- GBPUSD en perte legerement\n\n"
            "**Recommandations**\n"
            "- Augmenter le **stop loss** sur GBPUSD\n"
            "- Continuer sur EURUSD"
        )
        result = _format_analysis_html(text)

        assert "<h3" in result
        assert "<p" in result
        assert "<ul" in result
        assert "<li>" in result
        assert "<strong" in result
        assert "EURUSD" in result
        assert "GBPUSD" in result

    def test_bold_in_list_item(self):
        """Le bold dans un element de liste est converti."""
        text = "- Test avec **mot important** ici"
        result = _format_analysis_html(text)
        assert "<li>" in result
        assert "<strong" in result
        assert "mot important" in result

    def test_bold_in_paragraph(self):
        """Le bold dans un paragraphe est converti."""
        text = "Texte avec **mot cle** important."
        result = _format_analysis_html(text)
        assert "<p" in result
        assert "<strong" in result
        assert "mot cle" in result

    def test_closes_list_before_section_title(self):
        """Une liste est fermee avant un titre de section."""
        text = "- Item 1\n- Item 2\n**Nouvelle Section**\nContenu."
        result = _format_analysis_html(text)
        # List should be closed before the h3
        ul_close_idx = result.index("</ul>")
        h3_idx = result.index("<h3")
        assert ul_close_idx < h3_idx

    def test_no_double_list_tags(self):
        """Pas de <ul> imbriques ou de </ul> sans <ul>."""
        text = "- Item 1\n- Item 2\n\nTexte\n- Item 3"
        result = _format_analysis_html(text)
        assert result.count("<ul") == result.count("</ul>")
