import hashlib
import re
from datetime import datetime


def make_fingerprint(title: str, currency: str | None, scheduled_at: datetime | None) -> str:
    normalized_title = re.sub(r"\s+", " ", title.strip().lower())
    day = scheduled_at.date().isoformat() if scheduled_at else datetime.utcnow().date().isoformat()
    raw = f"{normalized_title}|{currency or ''}|{day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
