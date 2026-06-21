"""Impact heuristic for free-text news (RSS), which has no structured impact
field the way Forex Factory's calendar does. Same tiering logic as the
keyword -> instrument map in tagging.py, just classifying severity instead
of relevance."""

HIGH_IMPACT_KEYWORDS = [
    "fomc", "rate decision", "rate hike", "rate cut", "emergency meeting",
    "nfp", "non-farm payrolls", "cpi", "interest rate decision", "gdp",
    "war", "invasion", "missile", "nuclear", "ceasefire", "sanctions",
    "default", "recession", "attack", "strikes",
]

MED_IMPACT_KEYWORDS = [
    "speaks", "speech", "statement", "inflation", "pmi", "retail sales",
    "unemployment", "ecb", "boe", "rba", "boc", "jobless claims", "tariff",
    "lagarde", "bailey", "powell", "warsh",
]


def guess_impact(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in HIGH_IMPACT_KEYWORDS):
        return "high"
    if any(kw in text_lower for kw in MED_IMPACT_KEYWORDS):
        return "med"
    return "low"
