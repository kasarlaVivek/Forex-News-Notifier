from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS
from app.db import init_db
from app.workers.scheduler import start_scheduler, stop_scheduler
from app.api import events, subscriptions, stream, rules, test_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Forex News Notifier", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(subscriptions.router)
app.include_router(stream.router)
app.include_router(rules.router)
app.include_router(test_event.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Built React app (frontend/dist), copied here by the Dockerfile. Mounted last
# and with html=True so it acts as an SPA fallback without shadowing /api/*.
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
