"""Keyword -> instrument relevance map (see PLAN.md)."""

KEYWORD_RULES: list[tuple[list[str], list[str]]] = [
    (
        ["fed", "fomc", "rate decision", "warsh", "interest rate",
         "cpi", "inflation", "pce", "nfp", "non-farm", "jobless",
         "unemployment rate", "gdp", "retail sales", "ism"],
        ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "SP500", "NASDAQ"],
    ),
    (["ecb", "lagarde", "eurozone cpi", "bundesbank", "euro area"], ["EURUSD"]),
    (["boe", "bank of england", "bailey", "uk cpi", "uk inflation", "gilt"], ["GBPUSD"]),
    (["rba", "reserve bank of australia", "australia employment", "australia cpi"], ["AUDUSD"]),
    (["china", "pboc", "chinese data", "iron ore"],
     ["AUDUSD", "XAUUSD", "XAGUSD", "SP500", "NASDAQ"]),
    (["boc", "bank of canada", "canada cpi", "canada employment"], ["USDCAD"]),
    (["oil", "opec", "crude", "wti"], ["USDCAD", "SP500", "NASDAQ"]),
    (["gold", "xau", "silver", "xag", "precious metals", "bullion"], ["XAUUSD", "XAGUSD"]),
    (["war", "strike", "sanctions", "missile", "ceasefire", "invasion",
      "tension", "conflict", "attack", "escalation"],
     ["XAUUSD", "XAGUSD", "SP500", "NASDAQ"]),
]


def tag_instruments(text: str) -> list[str]:
    text_lower = text.lower()
    matched: set[str] = set()
    for keywords, instruments in KEYWORD_RULES:
        if any(kw in text_lower for kw in keywords):
            matched.update(instruments)
    return sorted(matched)


# Forex Factory calendar entries carry a currency code directly (its "country"
# field) — more reliable than keyword-matching the event title.
CURRENCY_INSTRUMENTS: dict[str, list[str]] = {
    "USD": ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "SP500", "NASDAQ"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
}


def _calendar_fallback_instruments(title: str) -> set[str]:
    """Keyword fallback for calendar entries, deliberately skipping the broad
    Fed/generic-econ-term rule (KEYWORD_RULES[0]). That rule exists for free
    text where the country isn't structurally known and "CPI"/"inflation"
    defaults to a USD assumption — but a calendar entry already carries its
    real currency, so e.g. a CAD CPI release must not also match the USD
    bucket just because "CPI" is a generic term. The remaining rules
    (oil/china/metals/geopolitics) are genuinely currency-agnostic and stay
    useful regardless of which currency the entry is tagged with."""
    text_lower = title.lower()
    matched: set[str] = set()
    for keywords, instruments in KEYWORD_RULES[1:]:
        if any(kw in text_lower for kw in keywords):
            matched.update(instruments)
    return matched


def tag_calendar_entry(currency: str, title: str) -> list[str]:
    """Instruments affected by a scheduled calendar entry: currency map first
    (authoritative — the feed tells us the real currency), keyword fallback
    second (catches oil/china/metals titles regardless of currency)."""
    matched = set(CURRENCY_INSTRUMENTS.get(currency, []))
    matched.update(_calendar_fallback_instruments(title))
    return sorted(matched)


def parse_numeric(value: str | None) -> float | None:
    """Parse Forex Factory style numbers: '2.5%', '180K', '-1.2M', '47.1'."""
    if not value:
        return None
    text = value.strip().replace(",", "").replace("%", "")
    if not text:
        return None
    multiplier = 1.0
    suffix = text[-1].upper()
    if suffix in ("K", "M", "B"):
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}[suffix]
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None
