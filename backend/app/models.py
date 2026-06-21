from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source: str  # 'forexfactory' | 'rss' | 'test'
    external_id: Optional[str] = Field(default=None, index=True)
    type: str  # 'scheduled' | 'news'
    title: str
    body: Optional[str] = None
    url: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    impact: str = "low"  # 'high' | 'med' | 'low'
    scheduled_at: Optional[datetime] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    surprise_score: Optional[float] = None
    instruments: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    fingerprint: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class InstrumentRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    instrument: str = Field(index=True, unique=True)
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    min_impact: str = "high"
    enabled: bool = True
    snoozed_until: Optional[datetime] = None


class Subscription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    endpoint: str = Field(unique=True)
    p256dh: str
    auth: str
    created_at: datetime = Field(default_factory=utcnow)


class AlertSent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(index=True)
    channel: str  # 'push' | 'sse'
    sent_at: datetime = Field(default_factory=utcnow)
