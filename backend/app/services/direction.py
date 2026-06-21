"""Heuristic directional bias per instrument — a transparent, rule-based
estimate for at-a-glance triage, not a prediction. Three independent signals
are tried in order (scheduled-data surprise, central-bank policy language,
general risk sentiment); the first one that actually applies to a given
instrument wins. Anything that doesn't match a known pattern stays "neutral"
rather than guessing — most events should resolve to neutral.
"""

# (base, quote) currencies for each FX pair on the watchlist. The instrument's
# price rises when its base currency strengthens (or its quote weakens).
PAIR_CURRENCIES: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
}

SAFE_HAVENS = {"XAUUSD", "XAGUSD"}
RISK_ASSETS = {"SP500", "NASDAQ"}

# Indicators where actual > forecast reads as a hawkish/growth-positive
# surprise (currency strengthens). Matched as a substring of the title.
POSITIVE_SURPRISE_INDICATORS = [
    "cpi", "gdp", "retail sales", "pmi", "ism", "non-farm payrolls", "nfp",
    "ppi", "consumer confidence", "durable goods", "employment change",
    "industrial production", "housing starts",
]

# Indicators where actual > forecast reads as a weaker economy (more
# unemployment/claims than expected = currency weakens).
NEGATIVE_SURPRISE_INDICATORS = [
    "unemployment rate", "jobless claims", "initial claims", "continuing claims",
]

RISK_OFF_KEYWORDS = [
    "war", "invasion", "missile", "nuclear", "attack", "strikes", "sanctions",
    "conflict", "escalation", "martial law", "default",
]
RISK_ON_KEYWORDS = [
    "ceasefire", "truce", "peace deal", "peace talks", "de-escalation", "agreement reached",
]
HAWKISH_KEYWORDS = ["rate hike", "raises rates", "hawkish", "rate increase"]
DOVISH_KEYWORDS = ["rate cut", "cuts rates", "dovish", "emergency cut", "rate decrease"]


def _surprise_direction(title: str, currency: str | None, surprise_score: float | None) -> str | None:
    """"up"/"down" for the event's own currency, based on actual-vs-forecast. None if no rule fits."""
    if surprise_score is None or not currency or surprise_score == 0:
        return None
    title_lower = title.lower()
    if any(kw in title_lower for kw in POSITIVE_SURPRISE_INDICATORS):
        return "up" if surprise_score > 0 else "down"
    if any(kw in title_lower for kw in NEGATIVE_SURPRISE_INDICATORS):
        return "down" if surprise_score > 0 else "up"
    return None


def _policy_direction(text: str) -> str | None:
    text_lower = text.lower()
    if any(kw in text_lower for kw in HAWKISH_KEYWORDS):
        return "up"
    if any(kw in text_lower for kw in DOVISH_KEYWORDS):
        return "down"
    return None


def _sentiment(text: str) -> str | None:
    text_lower = text.lower()
    if any(kw in text_lower for kw in RISK_OFF_KEYWORDS):
        return "risk_off"
    if any(kw in text_lower for kw in RISK_ON_KEYWORDS):
        return "risk_on"
    return None


def compute_bias(
    *,
    title: str,
    body: str | None,
    currency: str | None,
    instruments: list[str],
    surprise_score: float | None,
) -> dict[str, str]:
    """Per-instrument estimate: "bullish" | "bearish" | "neutral"."""
    text = f"{title} {body or ''}"
    bias = {instrument: "neutral" for instrument in instruments}

    policy_dir = _policy_direction(text)
    fx_dir = _surprise_direction(title, currency, surprise_score) or policy_dir
    sentiment = _sentiment(text)

    for instrument in instruments:
        pair = PAIR_CURRENCIES.get(instrument)
        if pair and currency in pair and fx_dir:
            base, _quote = pair
            pair_up = (fx_dir == "up") == (currency == base)
            bias[instrument] = "bullish" if pair_up else "bearish"
            continue

        if instrument in SAFE_HAVENS:
            if sentiment == "risk_off":
                bias[instrument] = "bullish"
            elif sentiment == "risk_on":
                bias[instrument] = "bearish"
            elif policy_dir == "up":
                bias[instrument] = "bearish"  # hawkish policy talk pressures gold/silver
            elif policy_dir == "down":
                bias[instrument] = "bullish"
            elif currency == "USD" and fx_dir == "up":
                bias[instrument] = "bearish"  # stronger USD pressures gold/silver
            elif currency == "USD" and fx_dir == "down":
                bias[instrument] = "bullish"
            continue

        if instrument in RISK_ASSETS:
            if sentiment == "risk_off":
                bias[instrument] = "bearish"
            elif sentiment == "risk_on":
                bias[instrument] = "bullish"
            continue

    return bias


def event_bias(event) -> dict[str, str]:
    return compute_bias(
        title=event.title,
        body=event.body,
        currency=event.currency,
        instruments=event.instruments or [],
        surprise_score=event.surprise_score,
    )
