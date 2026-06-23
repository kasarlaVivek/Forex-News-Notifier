from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.db import get_session
from app.models import Event
from app.services.direction import event_bias

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(limit: int = 50, session: Session = Depends(get_session)):
    recent = session.exec(
        select(Event).order_by(Event.created_at.desc()).limit(limit)
    ).all()

    # Calendar events are created once (when ForexFactory is polled) and then
    # never touched again, while breaking news is created continuously. A
    # plain "most recently created" limit lets news crowd every scheduled
    # event out of the result long before its date arrives, so the week-ahead
    # view goes empty. Pull those back in explicitly, regardless of the limit.
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    scheduled = session.exec(
        select(Event).where(Event.scheduled_at >= since).order_by(Event.scheduled_at.asc())
    ).all()

    # The reverse can also happen: a single ForexFactory poll inserts dozens
    # of calendar rows within the same second, which can fill every "recent"
    # slot and crowd breaking news out of the response entirely. Pull back
    # the last day of unscheduled news explicitly too, mirroring the fix
    # above (and the frontend's own 24h "breaking news" window).
    breaking = session.exec(
        select(Event)
        .where(Event.scheduled_at.is_(None), Event.created_at >= since)
        .order_by(Event.created_at.desc())
    ).all()

    seen = {e.id for e in recent}
    events = recent + [e for e in scheduled + breaking if e.id not in seen]
    return [{**event.model_dump(), "bias": event_bias(event)} for event in events]
