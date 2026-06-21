from typing import Optional
from pydantic import BaseModel


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": ..., "auth": ...}


class TestEventIn(BaseModel):
    title: str = "Test Alert: FOMC Rate Decision"
    body: str = "Fed holds rates steady — surprise vs forecast."
    impact: str = "high"
    instruments: Optional[list[str]] = None
