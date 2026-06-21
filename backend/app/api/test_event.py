from fastapi import APIRouter, Depends
from sqlmodel import Session
from app.db import get_session
from app.schemas import TestEventIn
from app.services.ingest import ingest_event

router = APIRouter(prefix="/api", tags=["test"])


@router.post("/test-event")
async def create_test_event(payload: TestEventIn, session: Session = Depends(get_session)):
    """Fires a fake event through the full pipe: dedup -> tag -> store ->
    SSE broadcast -> web push. Used to prove Phase 1 end-to-end before any
    real scraping is wired up."""
    event = await ingest_event(
        session,
        source="test",
        type_="news",
        title=payload.title,
        body=payload.body,
        impact=payload.impact,
        instruments=payload.instruments,
    )
    if event is None:
        return {"status": "duplicate_skipped"}
    return {"status": "ok", "event_id": event.id}
