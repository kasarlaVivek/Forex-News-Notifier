import asyncio
import json
from datetime import datetime
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        # Every datetime in this app is UTC by convention, but SQLite round-trips
        # drop tzinfo — append "Z" explicitly so the frontend never has to guess
        # (a naive ISO string with no designator gets parsed as local time by JS).
        iso = value.isoformat()
        return iso if value.tzinfo else f"{iso}Z"
    return str(value)


class EventBroadcaster:
    """In-memory pub/sub hub feeding all connected SSE clients."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=_json_default)
        for queue in list(self._subscribers):
            await queue.put(message)


broadcaster = EventBroadcaster()
