import json
import logging
from pywebpush import webpush, WebPushException
from sqlmodel import Session, select

from app.config import VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL
from app.models import Subscription

logger = logging.getLogger(__name__)


def send_push_to_all(session: Session, payload: dict) -> None:
    if not VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY not set — skipping web push (run scripts/generate_vapid_keys.py)")
        return

    subscriptions = session.exec(select(Subscription)).all()
    data = json.dumps(payload)

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=data,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
        except WebPushException as exc:
            logger.warning("Push failed for endpoint %s: %s", sub.endpoint, exc)
            if exc.response is not None and exc.response.status_code in (404, 410):
                session.delete(sub)
                session.commit()
        except Exception:
            # A single malformed/stale subscription (bad keys, encoding
            # failure, network error, etc.) must not block alerts to
            # everyone else subscribed.
            logger.exception("Unexpected push failure for endpoint %s", sub.endpoint)
