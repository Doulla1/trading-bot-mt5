"""Calendrier economique : sources multiples avec cascade fiable.

v3.0:
  1. Investing.com (Playwright)   -> source principale, JS obligatoire
  2. ForexFactory (httpx+BS4)     -> fallback si Playwright indisponible
  3. Evenements statiques         -> dernier recours si tout echoue

Cache SQLite (TTL 4h) pour eviter les appels repetitifs."""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from loguru import logger

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
CACHE_TTL_HOURS = 4


# ===================================================================
# API publique
# ===================================================================

def fetch_events() -> list[dict]:
    """Recupere les evenements economiques avec cascade de sources.

    Priorite:
      1. Cache SQLite (si frais)
      2. Investing.com (Playwright, navigateur headless)
      3. ForexFactory (httpx + BeautifulSoup)
      4. Evenements statiques recurrents

    Retourne:
        Liste d'evenements avec les cles:
        time, currency, event, impact, actual, forecast, previous
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # 1. Cache
    cached = _load_from_cache(today_str, now)
    if cached is not None:
        return cached

    # 2. Investing.com (Playwright)
    events = _try_investing()
    if events:
        _save_to_cache(today_str, events, now)
        return events

    # 3. ForexFactory (httpx fallback)
    events = _scrape_forexfactory()
    if events:
        _save_to_cache(today_str, events, now)
        return events

    # 4. Statique (dernier recours)
    logger.warning("Toutes les sources ont echoue - fallback statique")
    events = _get_static_events()
    if events:
        _save_to_cache(today_str, events, now)
    return events


def filter_relevant_events(events: list[dict], symbol: str = "EURUSD") -> list[dict]:
    """Filtre les evenements par devise du symbole et importance HIGH/MEDIUM.

    Args:
        events: Liste d'evenements bruts.
        symbol: Paire forex (ex: "EURUSD", "GBPJPY").

    Retourne:
        Evenements pertinents pour la paire.
    """
    currencies = {symbol[:3], symbol[3:]}
    return [
        ev for ev in events
        if ev.get("impact") in ("high", "medium")
        and ev.get("currency") in currencies
    ]


# ===================================================================
# Cache SQLite
# ===================================================================

def _load_from_cache(date_str: str, now: datetime) -> list[dict] | None:
    """Charge les evenements depuis le cache SQLite si encore valide."""
    try:
        from src.data.database import get_db
        db = get_db()
        row = db.execute(
            "SELECT events_json, fetched_at FROM calendar_cache WHERE date = ?",
            [date_str],
        ).fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            if (now - fetched_at).total_seconds() < CACHE_TTL_HOURS * 3600:
                logger.debug("Calendrier: utilise le cache (TTL {}h)", CACHE_TTL_HOURS)
                return json.loads(row["events_json"])
    except Exception:
        pass
    return None


def _save_to_cache(date_str: str, events: list, now: datetime) -> None:
    """Sauvegarde les evenements dans le cache SQLite."""
    try:
        from src.data.database import get_db
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO calendar_cache (date, events_json, fetched_at) "
            "VALUES (?, ?, ?)",
            [date_str, json.dumps(events), now.isoformat()],
        )
        db.commit()
    except Exception:
        pass


# ===================================================================
# Source 1: Investing.com (Playwright)
# ===================================================================

def _try_investing() -> list[dict]:
    """Tente le scraping Investing.com via Playwright.

    Retourne liste vide si Playwright n'est pas installe ou si la
    page n'a pas pu etre chargee.
    """
    try:
        from src.data.investing_calendar import fetch_events_investing
        events = fetch_events_investing()
        if events:
            logger.info("Calendrier: {} evenements depuis Investing.com", len(events))
        return events
    except ImportError:
        logger.debug("Investing.com: module non disponible")
        return []
    except Exception as e:
        logger.warning("Investing.com: echec ({})", e)
        return []


# ===================================================================
# Source 2: ForexFactory (httpx + BeautifulSoup)
# ===================================================================

def _scrape_forexfactory() -> list[dict]:
    """Scrape le calendrier ForexFactory via HTTP simple."""
    response = _fetch_forexfactory_page()
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "lxml")
    calendar_table = soup.find("table", class_="calendar__table")
    if calendar_table is None:
        logger.warning("ForexFactory: table du calendrier introuvable")
        return []

    events = []
    for row in calendar_table.find_all("tr", class_="calendar__row"):
        ev = _parse_calendar_row(row)
        if ev:
            events.append(ev)

    logger.info("ForexFactory: {} evenements recuperes", len(events))
    return events


def _fetch_forexfactory_page():
    """Telecharge la page du calendrier ForexFactory."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(FOREX_FACTORY_URL)
            resp.raise_for_status()
            return resp
    except httpx.HTTPError as e:
        logger.error("ForexFactory: echec HTTP ({})", e)
        return None


def _parse_calendar_row(row) -> dict | None:
    """Parse une ligne du tableau calendrier ForexFactory."""
    try:
        impact = _parse_impact(row)
        currency_cell = row.find("td", class_="calendar__currency")
        currency = currency_cell.text.strip() if currency_cell else ""
        event_cell = row.find("td", class_="calendar__event")
        event_name = event_cell.text.strip() if event_cell else ""
        time_cell = row.find("td", class_="calendar__time")
        event_time = time_cell.text.strip() if time_cell else ""

        if not currency or not event_name:
            return None
        return {
            "time": event_time,
            "currency": currency,
            "event": event_name,
            "impact": impact,
            "previous": _get_cell(row, "calendar__previous"),
            "forecast": _get_cell(row, "calendar__forecast"),
            "actual": _get_cell(row, "calendar__actual"),
        }
    except Exception:
        return None


def _parse_impact(row) -> str:
    """Determine le niveau d'impact d'un evenement ForexFactory."""
    impact_cell = row.find("td", class_="calendar__impact")
    if not impact_cell:
        return "low"
    impact_span = impact_cell.find("span")
    if not impact_span:
        return "low"
    classes = " ".join(impact_span.get("class", []))
    if "high" in classes:
        return "high"
    if "medium" in classes:
        return "medium"
    return "low"


def _get_cell(row, class_name) -> Optional[str]:
    cell = row.find("td", class_=class_name)
    return cell.text.strip() if cell else None


# ===================================================================
# Source 3: Evenements statiques recurrents (fallback ultime)
# ===================================================================

def _get_static_events() -> list[dict]:
    """Genere les evenements economiques majeurs recurrents.

    Utilise uniquement quand toutes les autres sources ont echoue.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    static_db = {
        "Monday": [
            ("09:00", "EUR", "German Ifo Business Climate", "medium"),
            ("14:45", "EUR", "ECB President Lagarde Speaks", "high"),
        ],
        "Tuesday": [
            ("14:00", "USD", "CB Consumer Confidence", "medium"),
        ],
        "Wednesday": [
            ("12:30", "USD", "Core Durable Goods Orders m/m", "medium"),
            ("14:30", "USD", "Crude Oil Inventories", "medium"),
            ("18:00", "USD", "FOMC Meeting Minutes", "high"),
        ],
        "Thursday": [
            ("12:30", "USD", "Unemployment Claims", "high"),
            ("12:30", "USD", "GDP q/q", "high"),
            ("14:00", "USD", "Pending Home Sales m/m", "medium"),
        ],
        "Friday": [
            ("12:30", "USD", "Core PCE Price Index m/m", "high"),
            ("12:30", "USD", "Non-Farm Employment Change", "high"),
            ("12:30", "USD", "Average Hourly Earnings m/m", "high"),
            ("14:00", "USD", "ISM Manufacturing PMI", "high"),
        ],
    }

    us_holidays = {
        "01-01", "01-15", "02-19", "05-27", "06-19",
        "07-04", "09-02", "11-28", "12-25",
    }

    events = []
    for day_offset in [0, 1]:
        target_date = now + timedelta(days=day_offset)
        day_name = target_date.strftime("%A")
        date_str = target_date.strftime("%Y-%m-%d")
        month_day = target_date.strftime("%m-%d")

        if month_day in us_holidays:
            events.append({
                "time": "All day", "currency": "USD",
                "event": "US Bank Holiday (marche calme)", "impact": "high",
                "date": date_str, "previous": "", "forecast": "",
            })

        if day_name in static_db:
            for event_time, currency, event_name, impact in static_db[day_name]:
                events.append({
                    "time": event_time, "currency": currency,
                    "event": event_name, "impact": impact,
                    "date": date_str, "previous": "", "forecast": "",
                })

    logger.info(
        "Fallback calendrier: {} evenements generes pour {}-{}",
        len(events), today, tomorrow,
    )
    return events
