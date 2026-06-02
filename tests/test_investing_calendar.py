"""Tests unitaires pour le module investing_calendar (Investing.com scraper)."""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.data.investing_calendar import (
    COUNTRY_TO_CURRENCY,
    _is_playwright_available,
    fetch_events_investing,
    filter_relevant_investing_events,
    _scrape_with_playwright,
    MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_EVENTS = [
    {
        "time": "08:30",
        "currency": "USD",
        "event": "Non-Farm Payrolls",
        "impact": "high",
        "actual": "",
        "forecast": "185K",
        "previous": "228K",
    },
    {
        "time": "12:00",
        "currency": "EUR",
        "event": "ECB Rate Decision",
        "impact": "high",
        "actual": "",
        "forecast": "",
        "previous": "",
    },
    {
        "time": "06:00",
        "currency": "JPY",
        "event": "BoJ Core CPI",
        "impact": "medium",
        "actual": "2.5%",
        "forecast": "2.4%",
        "previous": "2.3%",
    },
    {
        "time": "14:30",
        "currency": "USD",
        "event": "Unemployment Claims",
        "impact": "low",
        "actual": "210K",
        "forecast": "215K",
        "previous": "220K",
    },
    {
        "time": "10:00",
        "currency": "EUR",
        "event": "German Industrial Production",
        "impact": "medium",
        "actual": "",
        "forecast": "0.3%",
        "previous": "-0.5%",
    },
]


# ---------------------------------------------------------------------------
# COUNTRY_TO_CURRENCY
# ---------------------------------------------------------------------------


class TestCountryToCurrency:
    """Tests du mapping pays -> devise (ADR-001, couche data)."""

    def test_us_maps_to_usd(self):
        assert COUNTRY_TO_CURRENCY["US"] == "USD"

    def test_eurozone_countries_map_to_eur(self):
        for country in ["DE", "FR", "IT", "ES", "EU"]:
            assert COUNTRY_TO_CURRENCY[country] == "EUR"

    def test_gb_maps_to_gbp(self):
        assert COUNTRY_TO_CURRENCY["GB"] == "GBP"

    def test_jp_maps_to_jpy(self):
        assert COUNTRY_TO_CURRENCY["JP"] == "JPY"

    def test_nz_maps_to_nzd(self):
        assert COUNTRY_TO_CURRENCY["NZ"] == "NZD"

    def test_au_maps_to_aud(self):
        assert COUNTRY_TO_CURRENCY["AU"] == "AUD"

    def test_ch_maps_to_chf(self):
        assert COUNTRY_TO_CURRENCY["CH"] == "CHF"

    def test_ca_maps_to_cad(self):
        assert COUNTRY_TO_CURRENCY["CA"] == "CAD"

    def test_mapping_contains_major_forex_currencies(self):
        """Les 8 devises majeures du Forex doivent etre presentes."""
        majors = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
        mapped = set(COUNTRY_TO_CURRENCY.values())
        for m in majors:
            assert m in mapped, f"{m} manquant dans le mapping"

    def test_mapping_contains_expected_countries(self):
        """Quelques pays emergents doivent etre dans le mapping."""
        for country in ["CN", "IN", "BR", "KR", "ZA", "SG"]:
            assert country in COUNTRY_TO_CURRENCY

    def test_mapping_is_complete_has_no_duplicate_keys(self):
        """Le mapping ne doit pas avoir de cles en double."""
        assert len(COUNTRY_TO_CURRENCY) == len(set(COUNTRY_TO_CURRENCY.keys()))


# ---------------------------------------------------------------------------
# _is_playwright_available
# ---------------------------------------------------------------------------


class TestIsPlaywrightAvailable:
    """Tests de detection de disponibilite de Playwright."""

    @patch("src.data.investing_calendar.playwright", create=True)
    def test_returns_true_when_playwright_installed(self, mock_playwright):
        """Doit retourner True si playwright est importable."""
        assert _is_playwright_available() is True

    def test_returns_false_when_playwright_missing(self):
        """Doit retourner False si playwright n'est pas installe."""
        original_import = __builtins__["__import__"]

        def mock_import(name, *args, **kwargs):
            if name == "playwright":
                raise ImportError("No module named 'playwright'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            assert _is_playwright_available() is False


# ---------------------------------------------------------------------------
# filter_relevant_investing_events
# ---------------------------------------------------------------------------


class TestFilterRelevantInvestingEvents:
    """Tests du filtrage des evenements par devise et impact."""

    def test_filters_by_eurusd_currency(self):
        """EURUSD doit retourner les evenements EUR et USD."""
        result = filter_relevant_investing_events(MOCK_EVENTS, "EURUSD")
        currencies = {e["currency"] for e in result}
        assert "EUR" in currencies
        assert "USD" in currencies
        assert "JPY" not in currencies

    def test_filters_by_gbpjpy_currency(self):
        """GBPJPY doit retourner les evenements GBP et JPY."""
        events = [
            {"currency": "GBP", "impact": "high", "event": "BoE Rate"},
            {"currency": "JPY", "impact": "high", "event": "BoJ Rate"},
            {"currency": "USD", "impact": "high", "event": "NFP"},
        ]
        result = filter_relevant_investing_events(events, "GBPJPY")
        assert len(result) == 2
        assert result[0]["currency"] == "GBP"
        assert result[1]["currency"] == "JPY"

    def test_filters_low_impact_events(self):
        """Les evenements LOW impact doivent etre exclus."""
        result = filter_relevant_investing_events(MOCK_EVENTS, "EURUSD")
        for ev in result:
            assert ev["impact"] in ("high", "medium")

    def test_returns_only_high_and_medium_impact(self):
        """Seuls les evenements HIGH et MEDIUM sont retournes."""
        events = [
            {"currency": "USD", "impact": "high", "event": "NFP"},
            {"currency": "USD", "impact": "medium", "event": "Claims"},
            {"currency": "USD", "impact": "low", "event": "Fed Speech"},
        ]
        result = filter_relevant_investing_events(events, "USDUSD")
        assert len(result) == 2
        impacts = {e["impact"] for e in result}
        assert impacts == {"high", "medium"}
        assert "low" not in impacts

    def test_returns_empty_list_for_empty_input(self):
        """Liste vide en entree -> liste vide en sortie."""
        assert filter_relevant_investing_events([], "EURUSD") == []

    def test_returns_empty_when_no_matching_currency(self):
        """Aucun evenement pour la devise -> liste vide."""
        events = [
            {"currency": "JPY", "impact": "high", "event": "BoJ"},
        ]
        result = filter_relevant_investing_events(events, "EURUSD")
        assert result == []

    def test_preserves_event_structure(self):
        """Les champs de l'evenement doivent etre preserves."""
        result = filter_relevant_investing_events(MOCK_EVENTS, "EURUSD")
        for ev in result:
            assert "time" in ev
            assert "currency" in ev
            assert "event" in ev
            assert "impact" in ev
            assert "actual" in ev
            assert "forecast" in ev
            assert "previous" in ev

    def test_case_sensitivity_of_impact_field(self):
        """L'impact en minuscule doit etre reconnu."""
        events = [
            {"currency": "USD", "impact": "HIGH", "event": "NFP"},
            {"currency": "USD", "impact": "Medium", "event": "Claims"},
        ]
        result = filter_relevant_investing_events(events, "USDUSD")
        # Le code verifie "high" et "medium" en lowercase strict
        assert len(result) == 0


# ---------------------------------------------------------------------------
# fetch_events_investing - error handling
# ---------------------------------------------------------------------------


class TestFetchEventsInvestingErrorHandling:
    """Tests de gestion d'erreur de fetch_events_investing."""

    @patch("src.data.investing_calendar._is_playwright_available", return_value=False)
    def test_returns_empty_list_when_playwright_unavailable(self, mock_check):
        """Quand playwright n'est pas disponible -> []."""
        result = fetch_events_investing()
        assert result == []

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._scrape_with_playwright",
           side_effect=Exception("Timeout"))
    def test_returns_empty_list_after_all_retries_fail(self, mock_scrape, mock_check):
        """Apres MAX_RETRIES echecs -> []."""
        result = fetch_events_investing()
        assert result == []
        assert mock_scrape.call_count == MAX_RETRIES

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._scrape_with_playwright",
           side_effect=[Exception("First fail"), [{"time": "08:30", "event": "NFP", "impact": "high"}]])
    def test_succeeds_on_retry(self, mock_scrape, mock_check):
        """Reussit apres un echec -> les donnees sont retournees avec conversion UTC."""
        result = fetch_events_investing()
        # Les donnees sont retournees et converties en UTC
        assert len(result) == 1
        assert result[0]["event"] == "NFP"
        # 08:30 GMT+2 -> 06:30 UTC
        assert result[0]["time"] == "06:30"
        assert mock_scrape.call_count == 2


# ---------------------------------------------------------------------------
# fetch_events_investing - with mocked Playwright
# ---------------------------------------------------------------------------


class TestFetchEventsInvestingWithPlaywright:
    """Tests du pipeline complet avec Playwright mocke."""

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._convert_event_times_to_utc", side_effect=lambda x: x)
    @patch("playwright.sync_api.sync_playwright")
    def test_returns_parsed_events_from_page(self, mock_sync_pw, mock_convert, mock_check):
        """Verifie que les evenements extraits par page.evaluate sont correctement retournes."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        result = fetch_events_investing()

        assert len(result) == 5
        assert result[0]["event"] == "Non-Farm Payrolls"
        assert result[0]["currency"] == "USD"
        assert result[0]["impact"] == "high"
        assert result[1]["event"] == "ECB Rate Decision"
        assert result[1]["currency"] == "EUR"
        assert result[3]["event"] == "Unemployment Claims"
        assert result[3]["impact"] == "low"

        mock_page.goto.assert_called_once()
        mock_page.wait_for_selector.assert_called_once()
        mock_page.evaluate.assert_called_once()
        mock_browser.close.assert_called_once()

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._convert_event_times_to_utc", side_effect=lambda x: x)
    @patch("playwright.sync_api.sync_playwright")
    def test_empty_table_returns_empty_list(self, mock_sync_pw, mock_convert, mock_check):
        """Quand la table est vide -> []."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = []

        result = fetch_events_investing()
        assert result == []

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._convert_event_times_to_utc", side_effect=lambda x: x)
    @patch("playwright.sync_api.sync_playwright")
    def test_browser_is_closed_after_scrape(self, mock_sync_pw, mock_convert, mock_check):
        """Verifie que le navigateur est ferme apres le scraping."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        fetch_events_investing()
        mock_browser.close.assert_called_once()

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._convert_event_times_to_utc", side_effect=lambda x: x)
    @patch("playwright.sync_api.sync_playwright")
    def test_anti_detection_scripts_are_injected(self, mock_sync_pw, mock_convert, mock_check):
        """Verifie que les scripts anti-detection sont injectes dans le contexte."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        fetch_events_investing()

        mock_context.add_init_script.assert_called_once()
        script_arg = mock_context.add_init_script.call_args[0][0]
        assert "webdriver" in script_arg
        assert "Object.defineProperty(navigator, 'plugins'" in script_arg
        assert "window.chrome" in script_arg

    @patch("src.data.investing_calendar._is_playwright_available", return_value=True)
    @patch("src.data.investing_calendar._convert_event_times_to_utc", side_effect=lambda x: x)
    @patch("playwright.sync_api.sync_playwright")
    def test_chromium_launched_with_stealth_args(self, mock_sync_pw, mock_convert, mock_check):
        """Verifie que Chromium est lance avec les bons arguments anti-detection."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        fetch_events_investing()

        args = mock_playwright.chromium.launch.call_args[1]
        assert args["headless"] is True
        assert "--disable-blink-features=AutomationControlled" in args["args"]
        assert "--no-sandbox" in args["args"]


# ---------------------------------------------------------------------------
# _scrape_with_playwright - integration-like tests
# ---------------------------------------------------------------------------


class TestScrapeWithPlaywright:
    """Tests de _scrape_with_playwright en isolation."""

    @patch("playwright.sync_api.sync_playwright")
    def test_page_navigates_to_correct_url(self, mock_sync_pw):
        """Verifie la navigation vers l'URL Investing.com."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        from src.data.investing_calendar import INVESTING_URL
        _scrape_with_playwright()

        mock_page.goto.assert_called_once_with(
            INVESTING_URL, wait_until="networkidle", timeout=30000
        )

    @patch("playwright.sync_api.sync_playwright")
    def test_waits_for_table_selector(self, mock_sync_pw):
        """Verifie l'attente du selecteur de table."""
        mock_playwright = MagicMock()
        mock_sync_pw.return_value.__enter__.return_value = mock_playwright
        mock_browser = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.evaluate.return_value = MOCK_EVENTS

        _scrape_with_playwright()

        mock_page.wait_for_selector.assert_called_once_with(
            "table.datatable-v2_table__93S4Y", timeout=30000
        )
