import asyncio
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from app.services.broadcast import broadcaster

router = APIRouter(prefix="/api", tags=["stream"])


@router.get("/stream")
async def stream(request: Request):
    queue = broadcaster.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": "event", "data": message}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keep-alive"}
        finally:
            broadcaster.unsubscribe(queue)

    return EventSourceResponse(event_generator())
