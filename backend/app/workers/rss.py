"""Phase 3 — RSS news poller (forex/commodity/macro headlines).

Unlike Forex Factory's structured calendar, free-text headlines carry no
impact field, so impact is a keyword heuristic (services/impact.py). Every
relevant entry flows through the same ingest_event() pipeline as the test
endpoint: dedup -> store -> broadcast -> push.

Entries are tagged before calling ingest_event() (not left to its default
tagging) so irrelevant headlines can be dropped entirely, mirroring how
forexfactory.py drops calendar rows for currencies outside the watchlist.

Entries older than MAX_ENTRY_AGE are skipped — not just a perf optimization:
dedup's fingerprint falls back to *today's* date when there's no
scheduled_at (see services/dedup.py), so without an age filter the first
poll of a feed would ingest its entire backlog as "new today" events.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
from sqlmodel import Session

from app.services.ingest import ingest_event
from app.services.impact import guess_impact
from app.services.tagging import tag_instruments

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

FEEDS: list[str] = [
    "https://www.forexlive.com/feed/news",
    "https://www.fxstreet.com/rss/news",
    "https://www.investing.com/rss/news_1.rss",   # Forex News
    "https://www.investing.com/rss/news_11.rss",  # Commodities & Futures
    "https://www.investing.com/rss/news_95.rss",  # Economic Indicators
]

MAX_ENTRY_AGE = timedelta(hours=48)


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _published_at(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc).replace(tzinfo=None)


async def _fetch_feed(url: str):
    try:
        return await asyncio.to_thread(feedparser.parse, url, request_headers={"User-Agent": USER_AGENT})
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return None


async def poll_rss(session: Session) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for url in FEEDS:
        parsed = await _fetch_feed(url)
        if parsed is None:
            continue
        if parsed.bozo:
            logger.warning("RSS feed %s returned malformed/unreachable data: %s",
                            url, getattr(parsed, "bozo_exception", None))
        if not parsed.entries:
            continue

        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            if not title:
                continue

            published_at = _published_at(entry)
            if published_at and now - published_at > MAX_ENTRY_AGE:
                continue

            body = _strip_html(entry.get("summary"))
            instruments = tag_instruments(f"{title} {body or ''}")
            if not instruments:
                continue  # not relevant to the watchlist

            await ingest_event(
                session,
                source="rss",
                type_="news",
                title=title,
                body=body,
                url=entry.get("link"),
                impact=guess_impact(f"{title} {body or ''}"),
                instruments=instruments,
                external_id=entry.get("id") or entry.get("link"),
            )
