import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session

from app.db import engine
from app.workers.forexfactory import poll_forexfactory
from app.workers.rss import poll_rss
from app.workers.cleanup import cleanup_test_events

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_forexfactory_job() -> None:
    with Session(engine) as session:
        try:
            await poll_forexfactory(session)
        except Exception:
            logger.exception("forexfactory poll failed")


async def _run_rss_job() -> None:
    with Session(engine) as session:
        try:
            await poll_rss(session)
        except Exception:
            logger.exception("rss poll failed")


async def _run_cleanup_job() -> None:
    with Session(engine) as session:
        try:
            await cleanup_test_events(session)
        except Exception:
            logger.exception("test event cleanup failed")


def start_scheduler() -> None:
    # 5 min: the Forex Factory feed rate-limits aggressively on rapid polling.
    scheduler.add_job(_run_forexfactory_job, "interval", minutes=5, id="forexfactory")
    # 2 min: RSS feeds (forexlive/fxstreet/investing.com) are tolerant of frequent polling.
    scheduler.add_job(_run_rss_job, "interval", minutes=2, id="rss")
    # 20s: frequent enough that a test alert disappears close to 1 min after creation.
    scheduler.add_job(_run_cleanup_job, "interval", seconds=20, id="cleanup")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
