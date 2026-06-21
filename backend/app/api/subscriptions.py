from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.db import get_session
from app.models import Subscription
from app.schemas import SubscriptionIn
from app.config import VAPID_PUBLIC_KEY

router = APIRouter(prefix="/api", tags=["subscriptions"])


@router.get("/vapid-public-key")
def get_vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(payload: SubscriptionIn, session: Session = Depends(get_session)):
    existing = session.exec(
        select(Subscription).where(Subscription.endpoint == payload.endpoint)
    ).first()
    if existing:
        return {"status": "already_subscribed"}

    sub = Subscription(
        endpoint=payload.endpoint,
        p256dh=payload.keys["p256dh"],
        auth=payload.keys["auth"],
    )
    session.add(sub)
    session.commit()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
def unsubscribe(payload: SubscriptionIn, session: Session = Depends(get_session)):
    existing = session.exec(
        select(Subscription).where(Subscription.endpoint == payload.endpoint)
    ).first()
    if existing:
        session.delete(existing)
        session.commit()
    return {"status": "unsubscribed"}
