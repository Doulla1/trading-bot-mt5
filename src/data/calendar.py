"""Scraping du calendrier economique ForexFactory avec cache SQLite."""

import json
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from loguru import logger
from typing import Optional

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
CACHE_TTL_HOURS = 4


def fetch_events() -> list[dict]:
    """Recupere les evenements economiques depuis ForexFactory avec cache TTL (HIGH-04)."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Tenter le cache
    cached = _load_from_cache(today_str, now)
    if cached is not None:
        return cached

    # Scraper
    events = _scrape_forexfactory()
    _save_to_cache(today_str, events, now)
    return events


def _load_from_cache(date_str: str, now: datetime) -> list[dict] | None:
    """Charge les evenements depuis le cache SQLite si encore valide."""
    try:
        from src.data.database import get_db
        db = get_db()
        row = db.execute(
            "SELECT events_json, fetched_at FROM calendar_cache WHERE date = ?", [date_str]
        ).fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            if (now - fetched_at).total_seconds() < CACHE_TTL_HOURS * 3600:
                logger.debug("Calendrier: utilise le cache")
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
            "INSERT OR REPLACE INTO calendar_cache (date, events_json, fetched_at) VALUES (?, ?, ?)",
            [date_str, json.dumps(events), now.isoformat()],
        )
        db.commit()
    except Exception:
        pass


def _scrape_forexfactory() -> list[dict]:
    """Scrape le calendrier ForexFactory et retourne la liste d'evenements."""
    response = _fetch_forexfactory_page()
    if response is None:
        return _fallback_events()

    soup = BeautifulSoup(response.text, "lxml")
    calendar_table = soup.find("table", class_="calendar__table")
    if calendar_table is None:
        logger.warning("Table du calendrier ForexFactory introuvable")
        return _fallback_events()

    events = []
    for row in calendar_table.find_all("tr", class_="calendar__row"):
        ev = _parse_calendar_row(row)
        if ev:
            events.append(ev)

    logger.info(f"Calendrier: {len(events)} evenements recuperes")
    return events


def _fetch_forexfactory_page():
    """Telecharge la page du calendrier ForexFactory."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(FOREX_FACTORY_URL)
            resp.raise_for_status()
            return resp
    except httpx.HTTPError as e:
        logger.error(f"Echec scraping ForexFactory: {e}")
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
            "time": event_time, "currency": currency, "event": event_name,
            "impact": impact,
            "previous": _get_cell(row, "calendar__previous"),
            "forecast": _get_cell(row, "calendar__forecast"),
            "actual": _get_cell(row, "calendar__actual"),
        }
    except Exception:
        return None


def _parse_impact(row) -> str:
    """Determine le niveau d'impact d'un evenement."""
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


def _fallback_events() -> list:
    logger.warning("Fallback - aucun evenement economique")
    return []


def filter_relevant_events(events, symbol="EURUSD") -> list[dict]:
    """Filtre les evenements par devise du symbole."""
    currencies = [symbol[:3], symbol[3:]]
    return [ev for ev in events if ev.get("impact") in ("high", "medium") and ev.get("currency") in currencies]
