"""Scraper du calendrier economique Investing.com avec Playwright.

Utilise un navigateur Chromium headless avec des techniques anti-detection
pour contourner le rendu JavaScript (Next.js) du site Investing.com.

v1.1: Conversion des heures GMT+2 en UTC + gestion des heures relatives ("57m").

Fuseau horaire:
  - Investing.com affiche les heures en GMT+2 (fixe, pas de DST)
  - Ce module convertit TOUTES les heures en UTC avant de les retourner
  - Les heures relatives comme "57m" (temps restant) sont resolues en UTC
  - Le bot peut ainsi comparer proprement avec datetime.utcnow()"""

import json
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from loguru import logger

# Investing.com affiche les heures en GMT+2 (fixe toute l'annee)
# Les heures relatives "XXm" sont resolues par rapport a cet offset
INVESTING_TZ_OFFSET = timedelta(hours=2)  # GMT+2 fixe

# ---------------------------------------------------------------------------
# Mapping pays -> devise (codes ISO 3166-1 alpha-2 -> ISO 4217)
# ---------------------------------------------------------------------------
COUNTRY_TO_CURRENCY = {
    "US": "USD", "JP": "JPY", "AU": "AUD", "NZ": "NZD",
    "GB": "GBP", "CH": "CHF", "CA": "CAD",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
    "PT": "EUR", "IE": "EUR", "NL": "EUR", "BE": "EUR",
    "AT": "EUR", "FI": "EUR", "GR": "EUR", "EU": "EUR",
    "CN": "CNY", "IN": "INR", "KR": "KRW", "SG": "SGD",
    "HK": "HKD", "TW": "TWD", "BR": "BRL", "MX": "MXN",
    "RU": "RUB", "ZA": "ZAR", "TR": "TRY", "SE": "SEK",
    "NO": "NOK", "DK": "DKK", "PL": "PLN", "TH": "THB",
    "MY": "MYR", "ID": "IDR", "PH": "PHP", "IL": "ILS",
    "SA": "SAR", "AE": "AED", "EG": "EGP", "CL": "CLP",
    "CO": "COP", "AR": "ARS", "VN": "VND", "NG": "NGN",
    "KE": "KES", "QA": "QAR", "KW": "KWD", "HU": "HUF",
    "CZ": "CZK", "RO": "RON", "IS": "ISK", "PK": "PKR",
    "BD": "BDT", "LK": "LKR", "NP": "NPR", "MO": "MOP",
}

# Regex pour detecter les heures relatives: "57m", "2h", "1d"
_RELATIVE_TIME_RE = re.compile(r"^(\d+)(m|h|d)$")

INVESTING_URL = "https://fr.investing.com/economic-calendar"
MAX_RETRIES = 3
RETRY_DELAY_SEC = 3
PAGE_LOAD_TIMEOUT_MS = 30000


def _is_playwright_available() -> bool:
    """Verifie si Playwright est installe et les browsers disponibles."""
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False


def _convert_event_times_to_utc(events: list[dict]) -> list[dict]:
    """Convertit les heures GMT+2 (Investing.com) en UTC.

    Gere deux formats:
      - "08:30"  -> heure absolue GMT+2, convertie en UTC
      - "57m"    -> temps restant, resolu en heure UTC absolue
      - "All day" ou vide -> laisse tel quel

    Investing.com affiche les heures en GMT+2 fixe (pas de DST).
    On soustrait 2h pour obtenir l'UTC.
    """
    now_utc = datetime.now(timezone.utc)
    # Heure GMT+2 actuelle (pour resoudre les "57m")
    now_gmt2 = now_utc + INVESTING_TZ_OFFSET

    converted = []
    for ev in events:
        ev = dict(ev)  # copie pour ne pas muter l'original
        raw_time = ev.get("time", "")

        if not raw_time or raw_time == "All day":
            converted.append(ev)
            continue

        # 1) Temps relatif: "57m", "2h", "1d"
        rel_match = _RELATIVE_TIME_RE.match(raw_time)
        if rel_match:
            value = int(rel_match.group(1))
            unit = rel_match.group(2)
            if unit == "m":
                delta = timedelta(minutes=value)
            elif unit == "h":
                delta = timedelta(hours=value)
            else:  # 'd'
                delta = timedelta(days=value)
            # L'evenement a lieu dans `delta` depuis maintenant (en GMT+2)
            event_gmt2 = now_gmt2 + delta
            event_utc = event_gmt2 - INVESTING_TZ_OFFSET
            ev["time"] = event_utc.strftime("%H:%M")
            ev["time_utc"] = event_utc.strftime("%H:%M")
            logger.debug(
                "Heure relative {} -> UTC {} (GMT+2 {} + {}min)",
                raw_time, ev["time"],
                now_gmt2.strftime("%H:%M"), value,
            )
            converted.append(ev)
            continue

        # 2) Heure absolue: "08:30" (en GMT+2)
        time_match = re.search(r"(\d{1,2}):(\d{2})", raw_time)
        if time_match:
            try:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                # Construire l'heure GMT+2 aujourd'hui
                event_gmt2 = now_gmt2.replace(
                    hour=hour, minute=minute, second=0, microsecond=0,
                )
                # Si l'evenement semble dans le passe (>30min), essayer demain
                if event_gmt2 < now_gmt2 - timedelta(minutes=30):
                    event_gmt2 += timedelta(days=1)

                event_utc = event_gmt2 - INVESTING_TZ_OFFSET
                ev["time"] = event_utc.strftime("%H:%M")
                ev["time_utc"] = event_utc.strftime("%H:%M")
            except (ValueError, TypeError):
                pass  # garder l'heure originale si parsing echoue

        converted.append(ev)

    return converted


def fetch_events_investing() -> list[dict]:
    """Scrape le calendrier economique Investing.com avec Playwright.

    Les heures sont converties en UTC avant d'etre retournees.

    Retourne:
        Liste d'evenements au format:
        [{
            "time": "06:30",         # heure UTC
            "time_utc": "06:30",     # heure UTC (explicite)
            "currency": "USD",
            "event": "Non-Farm Payrolls",
            "impact": "high" | "medium" | "low",
            "actual": "243K",
            "forecast": "185K",
            "previous": "228K",
        }]

    En cas d'echec, retourne une liste vide (le fallback statique
    de calendar.py prendra le relais).
    """
    if not _is_playwright_available():
        logger.warning("Playwright non installe - impossible de scraper Investing.com")
        return []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            events = _scrape_with_playwright()
            if events:
                # Convertir les heures GMT+2 -> UTC
                events = _convert_event_times_to_utc(events)
                logger.info(
                    "Investing.com: {} evenements (convertis en UTC)", len(events)
                )
            return events
        except Exception as e:
            logger.warning(
                "Tentative {}/{} Investing.com echouee: {}",
                attempt, MAX_RETRIES, e,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)

    logger.error("Investing.com: toutes les tentatives ont echoue")
    return []


def _scrape_with_playwright() -> list[dict]:
    """Effectue le scraping via Playwright avec navigateur stealth."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # Lancement Chromium avec options anti-detection
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            geolocation={"latitude": 48.8566, "longitude": 2.3522},
            permissions=["geolocation"],
        )

        # Supprimer webdriver et autres traces de bot
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['fr-FR', 'fr', 'en-US', 'en'],
            });
            window.chrome = { runtime: {} };
            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications'
                    ? Promise.resolve({ state: 'denied' })
                    : originalQuery(params)
            );
        """)

        page = context.new_page()

        # Navigation avec timeout
        logger.info("Investing.com: navigation vers le calendrier...")
        page.goto(INVESTING_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)

        # Attendre que la table soit chargee
        page.wait_for_selector(
            "table.datatable-v2_table__93S4Y",
            timeout=PAGE_LOAD_TIMEOUT_MS,
        )

        # Petit delai supplementaire pour le rendu complet
        page.wait_for_timeout(2000)

        # Extraction par evaluate JavaScript
        events = page.evaluate("""
            () => {
                const table = document.querySelector('table.datatable-v2_table__93S4Y');
                if (!table) return [];

                const rows = table.querySelectorAll('tbody tr');
                const events = [];

                rows.forEach((row) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 8) return;

                    // Ignorer les lignes de separateur de date
                    if (row.querySelector('td[colspan]')) return;

                    // Nom de l'evenement
                    const eventLink = cells[3]?.querySelector('a');
                    const eventName = eventLink
                        ? eventLink.textContent.trim()
                        : '';
                    if (!eventName) return;

                    // Heure
                    const time = cells[1]?.textContent.trim() || '';

                    // Devise (code pays -> code devise)
                    const rawCurrency = (
                        cells[2]?.textContent.trim() || ''
                    ).toUpperCase();
                    const currencyMap = """ + json.dumps(COUNTRY_TO_CURRENCY, indent=8) + """;
                    const currency = currencyMap[rawCurrency] || rawCurrency;

                    // Importance (nombre d'etoiles remplies)
                    const filledStars = cells[4]?.querySelectorAll(
                        '.opacity-60'
                    ) || [];
                    const allStars = cells[4]?.querySelectorAll('svg') || [];
                    let impact = 'low';
                    if (filledStars.length >= 3) impact = 'high';
                    else if (filledStars.length >= 2) impact = 'medium';

                    events.push({
                        time: time,
                        currency: currency,
                        event: eventName,
                        impact: impact,
                        actual: cells[5]?.textContent.trim() || '',
                        forecast: cells[6]?.textContent.trim() || '',
                        previous: cells[7]?.textContent.trim() || '',
                    });
                });

                return events;
            }
        """)

        browser.close()

    logger.info("Investing.com: {} evenements recuperes", len(events))
    return events


def filter_relevant_investing_events(
    events: list[dict], symbol: str = "EURUSD",
) -> list[dict]:
    """Filtre les evenements par devise du symbole et importance.

    Args:
        events: Liste d'evenements bruts.
        symbol: Paire forex (ex: "EURUSD", "GBPJPY").

    Retourne:
        Evenements HIGH/MEDIUM dont la devise correspond a la paire.
    """
    currencies = {symbol[:3], symbol[3:]}
    return [
        ev for ev in events
        if ev.get("impact") in ("high", "medium")
        and ev.get("currency") in currencies
    ]


if __name__ == "__main__":
    """Test en ligne de commande."""
    from pprint import pprint

    events = fetch_events_investing()
    print(f"Total: {len(events)} evenements")
    print("--- 10 premiers ---")
    for ev in events[:10]:
        print(f"  {ev['time']:>6s} {ev['currency']:4s} "
              f"[{ev['impact']:6s}] {ev['event'][:60]:60s} "
              f"P:{ev['previous']:10s} F:{ev['forecast']:10s}")
    print("--- Filtre USD/EUR ---")
    relevant = filter_relevant_investing_events(events, "EURUSD")
    for ev in relevant[:5]:
        print(f"  {ev['time']:>6s} {ev['currency']:4s} "
              f"[{ev['impact']:6s}] {ev['event'][:60]:60s}")