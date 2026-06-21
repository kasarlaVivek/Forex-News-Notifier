from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.db import get_session
from app.models import Event
from app.services.direction import event_bias

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(limit: int = 50, session: Session = Depends(get_session)):
    events = session.exec(
        select(Event).order_by(Event.created_at.desc()).limit(limit)
    ).all()
    return [{**event.model_dump(), "bias": event_bias(event)} for event in events]
