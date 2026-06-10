from datetime import datetime, timezone
from src.data.calendar import enrich_event_with_delay
from src.ai.prompts import _format_calendar

def test_enrich_event_with_delay_future():
    now_utc = datetime(2026, 6, 10, 1, 3, 37)
    ev = {"time": "01:30", "currency": "AUD", "event": "AUD Retail Sales", "impact": "medium"}
    enriched = enrich_event_with_delay(ev, now_utc)
    
    assert enriched["minutes_to_event"] == 26
    assert enriched["date"] == "2026-06-10"

def test_enrich_event_with_delay_past():
    now_utc = datetime(2026, 6, 10, 1, 3, 37)
    ev = {"time": "00:45", "currency": "USD", "event": "USD Fed Speech", "impact": "high"}
    enriched = enrich_event_with_delay(ev, now_utc)
    
    assert enriched["minutes_to_event"] == -18
    assert enriched["date"] == "2026-06-10"

def test_enrich_event_with_delay_all_day():
    now_utc = datetime(2026, 6, 10, 1, 3, 37)
    ev = {"time": "All day", "currency": "EUR", "event": "EUR Bank Holiday", "impact": "low"}
    enriched = enrich_event_with_delay(ev, now_utc)
    
    assert enriched["minutes_to_event"] is None

def test_format_calendar_with_delay_future_short():
    evs = [
        {
            "time": "01:30",
            "date": "2026-06-10",
            "currency": "AUD",
            "event": "AUD News",
            "impact": "medium",
            "minutes_to_event": 26
        }
    ]
    formatted = _format_calendar(evs)
    assert "[MED] 2026-06-10 01:30 (in 26 mins) | AUD | AUD News" in formatted

def test_format_calendar_with_delay_future_long():
    evs = [
        {
            "time": "12:15",
            "date": "2026-06-10",
            "currency": "USD",
            "event": "USD News",
            "impact": "high",
            "minutes_to_event": 671
        }
    ]
    formatted = _format_calendar(evs)
    assert "[HIGH] 2026-06-10 12:15 (in 11h 11m / 671 mins) | USD | USD News" in formatted

def test_format_calendar_with_delay_past_short():
    evs = [
        {
            "time": "00:45",
            "date": "2026-06-10",
            "currency": "USD",
            "event": "USD News",
            "impact": "high",
            "minutes_to_event": -18
        }
    ]
    formatted = _format_calendar(evs)
    assert "[HIGH] 2026-06-10 00:45 (18 mins ago) | USD | USD News" in formatted

def test_format_calendar_with_delay_past_long():
    evs = [
        {
            "time": "23:45",
            "date": "2026-06-09",
            "currency": "USD",
            "event": "USD News",
            "impact": "high",
            "minutes_to_event": -78
        }
    ]
    formatted = _format_calendar(evs)
    assert "[HIGH] 2026-06-09 23:45 (1h 18m ago / -78 mins ago) | USD | USD News" in formatted
