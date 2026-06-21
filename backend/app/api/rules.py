from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.db import get_session
from app.models import InstrumentRule

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
def list_rules(session: Session = Depends(get_session)):
    # rows are seeded from WATCHLIST at app startup (see db.init_db)
    return session.exec(select(InstrumentRule)).all()


@router.patch("/{instrument}")
def update_rule(
    instrument: str,
    enabled: bool | None = None,
    min_impact: str | None = None,
    snooze_minutes: int | None = None,
    session: Session = Depends(get_session),
):
    """snooze_minutes: omit to leave snooze untouched, 0 to clear it, >0 to
    snooze for that many minutes from now."""
    rule = session.exec(
        select(InstrumentRule).where(InstrumentRule.instrument == instrument)
    ).first()
    if not rule:
        return {"error": "not_found"}
    if enabled is not None:
        rule.enabled = enabled
    if min_impact is not None:
        rule.min_impact = min_impact
    if snooze_minutes is not None:
        rule.snoozed_until = (
            None if snooze_minutes <= 0
            else datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=snooze_minutes)
        )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule
