# Forex / Metals / US Index — News Alert App: Build Plan

> A real-time event pipeline that notifies a forex, metals, and US index trader about
> price-moving news: FOMC/rate decisions, inflation (CPI) prints, geopolitical events,
> rising tensions, leader statements, and general risk-on/risk-off shifts.

## Decisions locked in

| Decision | Choice |
|---|---|
| **Alert delivery** | Web Push (Service Worker + VAPID) + in-app live feed |
| **Economic calendar source** | Scrape Forex Factory (free; actual vs forecast vs previous) |
| **MVP scope** | Calendar + RSS news first; Twitter/X and AI sentiment later |
| **Stack** | FastAPI backend, SQLite, React frontend |
| **Users** | Single-user (just you) — no auth/multi-tenancy |
| **Hosting** | Always-on, HTTPS-reachable (VPS or tunneled machine) |
| **Alert cap** | None — control noise by quality (impact gate + dedup), not quantity |
| **Quiet hours** | Always-on (no muting window) |
| **Pre-event reminder** | On — 30 min before high-impact scheduled events |

---

## What this app really is

At its core it's an **event pipeline**, not a CRUD app. The React frontend + FastAPI are
mostly for configuration, history, and a live feed. The real value lives in background
workers that continuously poll sources.

```
[Sources] -> [Ingest workers] -> [Normalize] -> [Score/Classify] -> [Dedup] -> [Alert engine] -> [You]
                                                       ^
                                                 SQLite (events, rules, sent log)
```

---

## Architecture

```
+---------------------------------------------------------------+
|  Background workers (APScheduler inside FastAPI)              |
|   - ForexFactory scraper   (every 1-5 min)                   |
|   - RSS poller             (every 1-2 min)                   |
|   - Surprise detector      (on calendar "actual" print)      |
+----------------+----------------------------------------------+
                 | writes
           +-----v-----+      +-------------------------------+
           |  SQLite   |<---->|  FastAPI REST + SSE            |
           +-----------+      +-------------+-----------------+
                                            | Server-Sent Events
                               +------------v------------------+
                               |  React PWA                     |
                               |  - Live feed (SSE)             |
                               |  - Service Worker -> Web Push  |
                               |  - Rules / mute config         |
                               +--------------------------------+
```

**Why SSE over WebSocket:** the feed is one-directional (server -> client); SSE
auto-reconnects and is simpler.

**Why Web Push matters:** via Service Worker + VAPID it delivers alerts **even when the
tab is closed**. Otherwise "web push" is just in-tab toasts.

---

## The sources (ranked by signal-to-noise & effort)

| Source | What it catches | How | Difficulty | Phase |
|---|---|---|---|---|
| **Economic calendar** | FOMC, CPI/inflation, NFP, rate decisions | Scrape Forex Factory | Medium — best ROI | 2 |
| **News headlines** | Geopolitical, central bank speak | RSS (Reuters, FXStreet, ForexLive) | Easy–Medium | 3 |
| **Twitter/X** | Leader tweets, breaking tension | X API (paid) or scrape | Hard — costs/fragile | Later |
| **Sentiment** | Aggregate risk-on/off mood | NLP/LLM on the above | Medium | Later |

> Twitter is intentionally deferred: scraping it is fragile and against ToS; the official
> X API is expensive. Calendar + RSS deliver ~80% of price-moving events reliably.

---

## Two event types (handled differently)

1. **Scheduled events** (FOMC, CPI) — known in advance.
   - Pull the calendar, store upcoming events.
   - Alert *before* (e.g. 30 min reminder) **and** when the `actual` number prints.
   - **Surprise = actual − forecast** is the real signal.

2. **Unscheduled events** (geopolitics, statements) — must poll continuously.
   - Classify impact, dedupe near-identical headlines, alert immediately.

---

## Data model (SQLite)

```
events
  id, source ('forexfactory'|'rss'), external_id (for dedup),
  type ('scheduled'|'news'), title, body, url,
  country, currency, impact ('high'|'med'|'low'),
  scheduled_at, forecast, previous, actual, surprise_score,
  instruments (json: ['XAUUSD','DXY','EURUSD']),
  created_at, fingerprint (hash for dedup)

instruments_rules        # which events you care about
  id, instrument, keywords (json), min_impact, enabled

subscriptions            # web push endpoints (VAPID)
  id, endpoint, p256dh, auth, created_at

alerts_sent              # so you never get the same alert twice
  id, event_id, channel, sent_at
```

---

## Traded instruments (the watchlist)

```
XAGUSD  (silver)        XAUUSD  (gold)
EURUSD                  GBPUSD
AUDUSD                  USDCAD
SP500   (US index CFD)  NASDAQ  (US index CFD)
```

Currencies/economies that matter: **USD, EUR, GBP, AUD, CAD** + **metals** + **US equity
indices**. USD is in 6 of the 8 instruments, so USD/Fed events are the highest-fanout.

## Relevance engine (keyword -> instrument map)

This map does the heavy lifting before any AI. Each event is tagged with the affected
instruments; an alert fires only if a tagged instrument is on the watchlist AND the
impact/surprise gate passes.

```
# --- USD (affects nearly everything) ---
"Fed","FOMC","rate decision","Warsh","interest rate",
"CPI","inflation","PCE","NFP","non-farm","jobless","unemployment rate",
"GDP","retail sales","ISM"
   -> XAUUSD, XAGUSD, EURUSD, GBPUSD, AUDUSD, USDCAD, SP500, NASDAQ

# --- EUR ---
"ECB","Lagarde","Eurozone CPI","German","Bundesbank","euro area"
   -> EURUSD

# --- GBP ---
"BoE","Bank of England","Bailey","UK CPI","UK inflation","gilt"
   -> GBPUSD

# --- AUD (also a risk-on proxy; China-sensitive) ---
"RBA","Reserve Bank of Australia","Australia employment","Australia CPI"
   -> AUDUSD
"China","PBoC","Chinese data","iron ore"
   -> AUDUSD, XAUUSD, XAGUSD, SP500, NASDAQ   # risk + commodity channel

# --- CAD (petro-currency) ---
"BoC","Bank of Canada","Canada CPI","Canada employment"
   -> USDCAD
"oil","OPEC","crude","WTI"
   -> USDCAD, SP500, NASDAQ                    # oil hits CAD + risk sentiment

# --- Metals / safe haven ---
"gold","XAU","silver","XAG","precious metals","bullion"
   -> XAUUSD, XAGUSD

# --- Geopolitics / risk-off (safe-haven bid + equity selloff) ---
"war","strike","sanctions","missile","ceasefire","invasion",
"tension","conflict","attack","escalation"
   -> XAUUSD, XAGUSD, SP500, NASDAQ
```

**Impact gate:** Forex Factory tags events high/med/low — push only for `high`
(configurable). For scheduled events, the **surprise** (`actual` vs `forecast`) decides
whether the result alert fires.

---

## Project structure

```
backend/
  app/
    main.py              # FastAPI app + SSE endpoint + startup scheduler
    db.py, models.py
    workers/
      forexfactory.py    # scraper -> normalized events
      rss.py             # feedparser over Reuters/FXStreet/ForexLive
      scheduler.py       # APScheduler job registration
    services/
      tagging.py         # keyword -> instruments + impact
      dedup.py           # fingerprint + suppression
      push.py            # pywebpush + VAPID
    api/                 # events, rules, subscriptions routes
frontend/
  src/
    sw.js                # service worker (push + notification click)
    hooks/useEventStream.js  # SSE
    pages/Feed, Rules, History
```

---

## Phased build

- **Phase 1 — skeleton + delivery proven end-to-end**
  FastAPI + SQLite + schema, SSE feed, React PWA with Service Worker, VAPID web push
  working with a *fake test event*. (Get the pipe working before real data.)

- **Phase 2 — Forex Factory**
  Scraper -> normalize -> dedup -> tag instruments -> push on high-impact + on `actual`
  print with surprise score. Pre-event reminder (30 min before).

- **Phase 3 — RSS news**
  feedparser over a curated feed list -> keyword tagging -> impact heuristic ->
  dedup near-duplicate headlines -> push.

- **Phase 4 — polish**
  Rules UI (mute instruments, set min impact, quiet hours), alert history, snooze.
  *Then* optional AI sentiment / Twitter later.

---

## Key risks (designed around)

1. **Forex Factory is scrape-hostile** — configurable poll interval, custom user-agent,
   retry/backoff, graceful degradation so a layout change doesn't crash the worker.
   Swapping in a paid calendar API later is a one-file change behind the same `events`
   interface.

2. **Duplicate spam** — fingerprint = hash(normalized title + currency + day);
   `alerts_sent` guarantees one push per event.

3. **Web push needs HTTPS** — fine on `localhost` for dev; needs a TLS domain (or a
   tunnel like Cloudflare Tunnel) to get pushes on your phone. Also requires the server
   to be always-on and reachable.

---

## Resolved deployment decisions

- **Single-user** — no auth, no multi-tenancy, no user table. One set of rules, one set
  of push subscriptions. Keeps everything simple.
- **HTTPS-reachable, always-on** host — satisfies Web Push requirements (TLS + reachable
  endpoint), so pushes reach the phone even with the tab closed.

## Where to focus refinement (highest leverage first)

1. **The relevance / filtering engine** — THE make-or-break part. The difference between
   a tool you trust and one you silence is whether it alerts on what moves price and stays
   quiet otherwise. Worth nailing down before coding:
     - Exact instrument set you trade (e.g. XAUUSD, DXY, US30/NAS100/SPX500, EURUSD...).
     - The keyword -> instrument mapping for each.
     - Default impact threshold (start: high-impact only).
     - Surprise threshold: how big must actual-vs-forecast be to fire a result alert.
2. **Alert fatigue controls** — DECISION: **no hard numeric cap.** A max-alerts/hour cap
   is the wrong tool: the moment it would trigger (a major event spawning a burst of
   related headlines) is exactly when you want every alert. Instead control noise by
   QUALITY, not QUANTITY:
     - **Impact gate** — high-impact only (the biggest filter).
     - **Dedup** — collapse near-identical headlines within a time window (fingerprint),
       so a story reported by 4 outlets = 1 alert, not 4.
     - **Quiet hours** — DECISION: always-on, no silence window for MVP (toggle exists
       in the rules table for later, default off).
     - **Per-instrument mute** — silence a pair you're not trading this week.
   This way a quiet market = few alerts naturally, and a chaotic market still gets through
   fully. If a safety valve is ever wanted, prefer a soft "collapse same-event bursts"
   over dropping alerts.

   **Pre-event reminder — DECISION: ON.** Fire a reminder 30 min before each high-impact
   scheduled event (FOMC, CPI, NFP, rate decisions), in addition to the alert when the
   `actual` value prints.
3. **Forex Factory scraping reliability** — poll cadence, how to detect the `actual`
   value appearing, graceful degradation. Second-most-likely thing to break.
4. **RSS feed list** — which exact feeds (Reuters, FXStreet, ForexLive, etc.). Easy to
   change later, low risk.

> Least worth over-planning now: DB schema, project structure, React layout — these are
> standard and cheap to adjust. Spend your thinking on #1 and #2.

---

## Final settings (locked) — ready to build

| Setting | Value |
|---|---|
| Instruments | XAGUSD, XAUUSD, EURUSD, GBPUSD, AUDUSD, USDCAD, SP500, NASDAQ |
| Delivery | Web Push (Service Worker + VAPID) + in-app SSE feed |
| Calendar source | Forex Factory scrape (Phase 2) |
| News source | RSS — Reuters / FXStreet / ForexLive (Phase 3) |
| Twitter / AI sentiment | Deferred (post-MVP) |
| Users | Single-user, no auth |
| Hosting | Always-on, HTTPS-reachable |
| Impact gate | High-impact only (configurable) |
| Alert cap | None — quality gating + dedup instead |
| Quiet hours | Always-on (no mute window) |
| Pre-event reminder | On — 30 min before high-impact scheduled events |

**Plan status: COMPLETE.** Next step when ready = produce the file-by-file Phase 1
implementation plan (skeleton + web-push pipe proven end-to-end with a fake test event),
then build Phase 1 -> 2 -> 3 -> 4.
