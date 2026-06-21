from datetime import datetime, timezone
from sqlmodel import Session, select

from app.models import Event, InstrumentRule, AlertSent
from app.services.tagging import tag_instruments
from app.services.dedup import make_fingerprint
from app.services.broadcast import broadcaster
from app.services.direction import event_bias
from app.services.push import send_push_to_all

IMPACT_RANK = {"low": 0, "med": 1, "high": 2}


def passes_rules(session: Session, instruments: list[str], impact: str) -> bool:
    """An event alerts only if at least one tagged instrument has an enabled,
    non-snoozed rule whose min_impact is met. No matching instrument = no
    alert (still stored)."""
    if not instruments:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rules = session.exec(
        select(InstrumentRule).where(InstrumentRule.instrument.in_(instruments))
    ).all()
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.snoozed_until and rule.snoozed_until > now:
            continue
        if IMPACT_RANK.get(impact, 0) >= IMPACT_RANK.get(rule.min_impact, 2):
            return True
    return False


async def ingest_event(
    session: Session,
    *,
    source: str,
    type_: str,
    title: str,
    body: str | None = None,
    url: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    impact: str = "low",
    scheduled_at: datetime | None = None,
    forecast: str | None = None,
    previous: str | None = None,
    actual: str | None = None,
    surprise_score: float | None = None,
    external_id: str | None = None,
    instruments: list[str] | None = None,
) -> Event | None:
    """Normalize, dedup, tag, persist, and alert on one incoming event.

    Returns the stored Event, or None if it was a duplicate (already seen).
    """
    fingerprint = make_fingerprint(title, currency, scheduled_at)

    existing = session.exec(select(Event).where(Event.fingerprint == fingerprint)).first()
    if existing:
        return None  # dedup: same story already recorded

    tagged = instruments if instruments is not None else tag_instruments(f"{title} {body or ''}")

    event = Event(
        source=source,
        external_id=external_id,
        type=type_,
        title=title,
        body=body,
        url=url,
        country=country,
        currency=currency,
        impact=impact,
        scheduled_at=scheduled_at,
        forecast=forecast,
        previous=previous,
        actual=actual,
        surprise_score=surprise_score,
        instruments=tagged,
        fingerprint=fingerprint,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    should_alert = passes_rules(session, tagged, impact)

    await broadcaster.publish({
        "id": event.id,
        "title": event.title,
        "body": event.body,
        "impact": event.impact,
        "instruments": event.instruments,
        "created_at": event.created_at,
        "scheduled_at": event.scheduled_at,
        "alerted": should_alert,
        "bias": event_bias(event),
    })
    session.add(AlertSent(event_id=event.id, channel="sse"))
    session.commit()

    if should_alert:
        send_push_to_all(session, {
            "title": event.title,
            "body": event.body or ", ".join(event.instruments),
            "url": event.url or "/",
        })
        session.add(AlertSent(event_id=event.id, channel="push"))
        session.commit()

    return event
