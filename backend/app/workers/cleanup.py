"""Background sweep that removes test alerts shortly after creation.

The "Send test alert" button is a manual smoke test for the delivery pipe
(dedup -> tag -> store -> SSE -> push) — useful for verifying push still
works after touching ingest.py/push.py or browser permissions, but with both
real ingestion sources (Forex Factory + RSS) now live, test events have no
reason to stick around in the feed/history. A broadcast delete notice lets
already-connected clients drop it from the live view immediately rather than
waiting for their next history refresh.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import Event, AlertSent
from app.services.broadcast import broadcaster

logger = logging.getLogger(__name__)

TEST_EVENT_TTL = timedelta(minutes=1)


async def cleanup_test_events(session: Session) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - TEST_EVENT_TTL
    stale = session.exec(
        select(Event).where(Event.source == "test", Event.created_at < cutoff)
    ).all()
    for event in stale:
        alerts = session.exec(select(AlertSent).where(AlertSent.event_id == event.id)).all()
        for alert in alerts:
            session.delete(alert)
        session.delete(event)
        session.commit()
        await broadcaster.publish({"id": event.id, "deleted": True})
