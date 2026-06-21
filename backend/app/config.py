import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "forex_notifier.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "mailto:admin@example.com")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# Default watchlist — instruments this app cares about (see PLAN.md)
WATCHLIST = [
    "XAGUSD", "XAUUSD", "EURUSD", "GBPUSD",
    "AUDUSD", "USDCAD", "SP500", "NASDAQ",
]

# Phase 1 default: only high-impact events fire a push
DEFAULT_MIN_IMPACT = "high"

PRE_EVENT_REMINDER_MINUTES = 30
