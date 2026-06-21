"""Phase 2 — Forex Factory economic calendar scraper.

Source: the public calendar JSON feed used by many forex calendar widgets
(nfs.faireconomy.media). Confirmed live shape:
    {"title": "...", "country": "USD", "date": "2026-06-22T08:30:00-04:00",
     "impact": "High"|"Medium"|"Low", "forecast": "0.7%", "previous": "0.4%",
     "actual": "..."}   <- "actual" only appears once the number has printed.

This feed rate-limits aggressively on rapid repeat requests (observed directly
while building this) — poll on a multi-minute interval (see scheduler.py) and
never retry-loop on failure; a failed poll just tries again next interval.

Each calendar entry alerts at most twice, tracked via AlertSent rows (not new
Event columns, to keep the schema minimal):
  - a "reminder" push ~PRE_EVENT_REMINDER_MINUTES before scheduled_at, only if
    no actual has printed yet.
  - a "result" push the first time `actual` appears, scored by
    surprise = actual - forecast.
Both still pass through the same impact-gate as everything else (passes_rules).
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.config import PRE_EVENT_REMINDER_MINUTES
from app.models import Event, AlertSent
from app.services.tagging import tag_calendar_entry, parse_numeric
from app.services.dedup import make_fingerprint
from app.services.broadcast import broadcaster
from app.services.direction import event_bias
from app.services.ingest import passes_rules
from app.services.push import send_push_to_all

logger = logging.getLogger(__name__)

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
IMPACT_MAP = {"high": "high", "medium": "med", "low": "low"}


async def fetch_calendar() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(FEED_URL)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # ValueError covers JSON decode failures (e.g. a "Rate Limited" HTML
        # page returned with a 200/non-200 status) — degrade gracefully.
        logger.warning("Forex Factory feed fetch failed: %s", exc)
        return []


def parse_entry(raw: dict) -> dict | None:
    title = (raw.get("title") or "").strip()
    currency = (raw.get("country") or "").strip().upper()
    impact = IMPACT_MAP.get((raw.get("impact") or "").strip().lower())
    date_str = raw.get("date")
    if not title or impact is None or not date_str:
        return None  # skips holidays/unrecognized rows

    try:
        scheduled_at = datetime.fromisoformat(date_str)
    except ValueError:
        return None
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)

    instruments = tag_calendar_entry(currency, title)
    if not instruments:
        return None  # not relevant to the watchlist (e.g. JPY/CHF/NZD/CNY-only)

    return {
        "title": title,
        "currency": currency,
        "impact": impact,
        "scheduled_at": scheduled_at,
        "forecast": raw.get("forecast") or None,
        "previous": raw.get("previous") or None,
        "actual": raw.get("actual") or None,
        "instruments": instruments,
        "url": raw.get("url") or None,
    }


async def upsert_event(session: Session, parsed: dict) -> Event:
    fingerprint = make_fingerprint(parsed["title"], parsed["currency"], parsed["scheduled_at"])
    existing = session.exec(select(Event).where(Event.fingerprint == fingerprint)).first()

    if existing is None:
        event = Event(
            source="forexfactory",
            type="scheduled",
            title=parsed["title"],
            currency=parsed["currency"],
            impact=parsed["impact"],
            scheduled_at=parsed["scheduled_at"],
            forecast=parsed["forecast"],
            previous=parsed["previous"],
            actual=parsed["actual"],
            instruments=parsed["instruments"],
            fingerprint=fingerprint,
            url=parsed["url"],
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        await broadcaster.publish({
            "id": event.id,
            "title": event.title,
            "body": f"Forecast: {event.forecast or 'n/a'} | Previous: {event.previous or 'n/a'}",
            "impact": event.impact,
            "instruments": event.instruments,
            "created_at": event.created_at,
            "scheduled_at": event.scheduled_at,
            "alerted": False,
            "bias": event_bias(event),
        })
        session.add(AlertSent(event_id=event.id, channel="sse"))
        session.commit()
        return event

    changed = False
    if parsed["actual"] and parsed["actual"] != existing.actual:
        existing.actual = parsed["actual"]
        changed = True
    if parsed["forecast"] and parsed["forecast"] != existing.forecast:
        existing.forecast = parsed["forecast"]
        changed = True
    if changed:
        session.add(existing)
        session.commit()
        session.refresh(existing)
    return existing


def _already_sent(session: Session, event_id: int, channel: str) -> bool:
    return session.exec(
        select(AlertSent).where(AlertSent.event_id == event_id, AlertSent.channel == channel)
    ).first() is not None


async def maybe_send_reminder(session: Session, event: Event, now: datetime) -> None:
    if event.actual or event.scheduled_at is None:
        return
    minutes_until = (event.scheduled_at - now).total_seconds() / 60
    if not (0 < minutes_until <= PRE_EVENT_REMINDER_MINUTES):
        return
    if _already_sent(session, event.id, "reminder"):
        return
    if not passes_rules(session, event.instruments, event.impact):
        return

    send_push_to_all(session, {
        "title": f"In {PRE_EVENT_REMINDER_MINUTES} min: {event.title} ({event.currency})",
        "body": f"Forecast: {event.forecast or 'n/a'} | Previous: {event.previous or 'n/a'}",
        "url": event.url or "/",
    })
    session.add(AlertSent(event_id=event.id, channel="reminder"))
    session.commit()


async def maybe_send_result(session: Session, event: Event) -> None:
    """Three separate, independently-idempotent concerns once `actual` prints:
    1. compute + store the surprise score (always — it's historical data,
       shouldn't depend on current rule state)
    2. broadcast the update to the live feed once (everyone sees it happened)
    3. send a push once, only if the impact gate passes
    Tracked via two AlertSent channels so a later rule change can't cause a
    re-broadcast storm or a duplicate push on subsequent polls."""
    if not event.actual:
        return

    if not _already_sent(session, event.id, "result-seen"):
        actual_num = parse_numeric(event.actual)
        forecast_num = parse_numeric(event.forecast)
        if actual_num is not None and forecast_num is not None:
            event.surprise_score = actual_num - forecast_num
            session.add(event)
            session.commit()
            session.refresh(event)

        surprise_text = f" (surprise: {event.surprise_score:+g})" if event.surprise_score is not None else ""
        await broadcaster.publish({
            "id": event.id,
            "title": event.title,
            "body": f"Actual {event.actual} vs forecast {event.forecast or 'n/a'}{surprise_text}",
            "impact": event.impact,
            "instruments": event.instruments,
            "created_at": event.created_at,
            "scheduled_at": event.scheduled_at,
            "alerted": passes_rules(session, event.instruments, event.impact),
            "bias": event_bias(event),
        })
        session.add(AlertSent(event_id=event.id, channel="result-seen"))
        session.commit()

    if _already_sent(session, event.id, "result"):
        return
    if not passes_rules(session, event.instruments, event.impact):
        return

    surprise_text = f" (surprise: {event.surprise_score:+g})" if event.surprise_score is not None else ""
    send_push_to_all(session, {
        "title": f"{event.title} ({event.currency}): {event.actual}",
        "body": f"Forecast {event.forecast or 'n/a'} | Previous {event.previous or 'n/a'}{surprise_text}",
        "url": event.url or "/",
    })
    session.add(AlertSent(event_id=event.id, channel="result"))
    session.commit()


async def poll_forexfactory(session: Session) -> None:
    raw_entries = await fetch_calendar()
    if not raw_entries:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for raw in raw_entries:
        parsed = parse_entry(raw)
        if parsed is None:
            continue
        event = await upsert_event(session, parsed)
        await maybe_send_reminder(session, event, now)
        await maybe_send_result(session, event)
