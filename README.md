# Forex News Notifier

A self-hosted alert system for a forex/metals/US-index trader. It watches an
economic calendar and news sources for events that can move price — FOMC/rate
decisions, CPI/inflation prints, geopolitical escalation, central bank
statements — and pushes an instant notification (browser Web Push + a live
in-app feed) when something relevant to your watchlist happens.

See [`PLAN.md`](./PLAN.md) for the full design rationale and phased roadmap.
This README covers how it's built and how to run it.

## Current status: Phase 4 complete

The skeleton and the **delivery pipe** (dedup → tag → store → SSE → push) are
built and proven end-to-end. Both ingestion sources are live: the Forex
Factory economic calendar scraper (`backend/app/workers/forexfactory.py`,
polling every 5 min with pre-event reminders + result alerts scored by
surprise) and the RSS news poller (`backend/app/workers/rss.py`, polling 5
forex/macro feeds every 2 min). The frontend has a Rules panel (mute an
instrument, change its impact threshold, snooze it), and clicking any feed
item opens a detail view with a heuristic directional-bias estimate per
affected instrument.

| Phase | Status |
|---|---|
| 1 — Skeleton + push pipe proven with a fake event |  Done |
| 2 — Forex Factory economic calendar scraper |  Done |
| 3 — RSS news ingestion |  Done |
| 4 — Rules UI, alert detail view, snooze |  Done |

## Watchlist

```
XAGUSD, XAUUSD, EURUSD, GBPUSD, AUDUSD, USDCAD, SP500, NASDAQ
```

---

## Architecture

```
+---------------------------------------------------------------+
|  Background workers (APScheduler inside FastAPI)              |
|   - ForexFactory scraper   (Phase 2 — polls every 5 min)      |
|   - RSS poller             (Phase 3 — polls every 2 min)      |
+----------------+----------------------------------------------+
                 | calls ingest_event()
           +-----v-----+      +-------------------------------+
           |  SQLite   |<---->|  FastAPI REST + SSE            |
           +-----------+      +-------------+-----------------+
                                            | Server-Sent Events
                               +------------v------------------+
                               |  React app (Vite)              |
                               |  - Live feed (SSE)              |
                               |  - Service Worker -> Web Push  |
                               +--------------------------------+
```

**Why SSE, not WebSocket** — the event feed only flows server → client, so a
one-directional, auto-reconnecting stream is simpler and sufficient.

**Why Web Push** — registered via a Service Worker with VAPID keys, push
notifications arrive even when the browser tab is closed. This is the actual
reason this app can wake you up about a CPI print instead of just being a
dashboard you have to remember to check.

---

## How it works (the pipeline)

Free-text/unscheduled events (the test endpoint, RSS) flow through one
function: **`backend/app/services/ingest.py::ingest_event()`**.

1. **Fingerprint & dedup** (`services/dedup.py`) — `hash(normalized title +
   currency + day)`. If the same story already exists (e.g. 4 outlets report
   one Fed headline), it's silently skipped. This is the project's actual
   noise-control mechanism — see [`PLAN.md`](./PLAN.md) for why a hard
   alerts/hour cap was deliberately rejected in favor of dedup + an impact
   gate.
2. **Tag instruments** (`services/tagging.py`) — a keyword → instrument map
   decides which of your 8 watchlist instruments an event affects (e.g. "Fed",
   "CPI", "Powell"/"Warsh" → all USD-linked pairs + indices; "ECB" → EURUSD
   only; "war"/"sanctions" → safe-haven metals + indices).
3. **Persist** — the event is always stored in SQLite (`Event` table),
   regardless of whether it ends up alerting, so the in-app history is
   complete.
4. **Impact gate** (`InstrumentRule` table, seeded from the watchlist at app
   startup) — an event only *alerts* if at least one tagged instrument has an
   enabled, non-snoozed rule whose `min_impact` is met (default: `high`
   only). Each instrument can be disabled or temporarily snoozed from the
   Rules panel in the frontend (`PATCH /api/rules/{instrument}`).
5. **Broadcast** — the event is pushed to every connected browser tab over
   SSE (`/api/stream`) immediately, regardless of the impact gate, so the live
   feed always shows everything. The payload includes a heuristic
   **directional bias** per affected instrument (see below).
6. **Push** — if the impact gate passed, a Web Push notification is sent to
   every subscribed browser via `services/push.py` (VAPID + `pywebpush`).
   Expired/invalid subscriptions (HTTP 404/410 from the push service) are
   pruned automatically.

### Scheduled vs. unscheduled events

- **Scheduled** (FOMC, CPI, NFP) — polled every 5 minutes from the Forex
  Factory calendar feed by `workers/forexfactory.py`. Calendar entries carry
  their own currency (more reliable than keyword tagging), so they use a
  dedicated `upsert_event()` instead of `ingest_event()` — a single calendar
  row gets created once and then *updated in place* as `forecast`/`actual`
  change, and each entry can alert **twice**, tracked via `AlertSent` rows
  (not extra `Event` columns):
  - a **reminder** push ~30 min before `scheduled_at`
    (`PRE_EVENT_REMINDER_MINUTES` in `config.py`), only if no `actual` has
    printed yet;
  - a **result** push the first time `actual` appears, scored by **surprise
    = actual − forecast** (`services/tagging.py::parse_numeric` handles
    Forex-Factory-style values like `"2.5%"`, `"180K"`, `"-1.2M"`).

  The live SSE feed always shows the actual-printed update the moment it's
  seen (tracked via a separate `result-seen` channel), even if that
  particular release doesn't pass the impact gate — only the *push* is
  gated, consistent with the rest of the app.
- **Unscheduled** (geopolitics, central bank statements) — polled every 2 min
  from 5 RSS feeds (`workers/rss.py`), tagged and deduped through
  `ingest_event()` like the test endpoint. Impact is a keyword heuristic
  (`services/impact.py::guess_impact`) since RSS headlines carry no
  structured impact field. Entries older than 48h are skipped — not just a
  perf optimization: dedup's fingerprint falls back to *today's* date when
  there's no `scheduled_at`, so without an age filter the first poll of a
  feed would ingest its entire backlog as "new today".

Both paths share the same impact gate (`passes_rules()` in `ingest.py`) and
the same `InstrumentRule` table, which is seeded from the watchlist at app
startup (`db.py::init_db`) — not lazily on first API call, since the
scheduler's first poll can fire before the frontend is ever opened.

The Forex Factory feed (`nfs.faireconomy.media/ff_calendar_thisweek.json`)
rate-limits aggressively on rapid repeat requests — confirmed directly while
building this (a 429, and once an HTML "Rate Limited" page instead of JSON).
`fetch_calendar()` degrades gracefully on any fetch/parse failure (logs and
returns `[]`, leaving the next 5-minute poll to retry) rather than crashing
the scheduler.

### Possible impact (directional bias)

Every event in the feed carries a `bias` field: a per-instrument
**bullish / bearish / neutral** estimate, computed on the fly by
`services/direction.py::compute_bias()` — never stored, so changing the
heuristic doesn't require a migration. It's a transparent rule table, not a
prediction or sentiment model:

- **Scheduled data with a surprise score** — known indicators (CPI, GDP,
  retail sales, PMI... vs. unemployment rate, jobless claims) are tagged as
  "higher-than-forecast is currency-positive" or "...-negative"; the sign of
  `surprise_score` then flips bullish/bearish per FX pair based on whether
  the event's currency is the pair's base or quote leg.
- **Central-bank policy language** ("hawkish"/"rate hike" vs.
  "dovish"/"rate cut") nudges the same currency logic, and pressures gold/
  silver inversely.
- **Risk sentiment** (war/escalation/sanctions vs. ceasefire/de-escalation)
  drives gold/silver and the indices in the classic safe-haven / risk-on
  direction.

Anything that doesn't match a known pattern stays **neutral** rather than
guessing — most events, especially generic RSS headlines, should and will
resolve to neutral. Clicking any feed item opens a detail view (full body,
forecast/previous/actual, source link, and the bias breakdown per
instrument).

### No alert cap, by design

There is intentionally **no max-alerts-per-hour limit**. A hard cap is wrong
for this use case: a burst of related headlines during a real crisis is
exactly when every alert matters. Noise is controlled by **quality, not
quantity** — dedup + the impact gate. See [`PLAN.md`](./PLAN.md) for the full
reasoning.

---

## Project structure

```
backend/
  app/
    main.py              # FastAPI app, lifespan (DB init + scheduler), routers
    config.py             # watchlist, impact defaults, VAPID/env config
    db.py, models.py      # SQLModel + SQLite (Event, InstrumentRule, Subscription, AlertSent)
    schemas.py            # Pydantic request bodies
    api/
      events.py           # GET /api/events — history
      rules.py             # GET/PATCH /api/rules — per-instrument mute + impact threshold
      stream.py            # GET /api/stream — SSE live feed
      subscriptions.py    # POST /api/subscribe, /api/unsubscribe, GET /api/vapid-public-key
      test_event.py        # POST /api/test-event — fires a fake event through the full pipe
    services/
      ingest.py            # the pipeline: dedup -> tag -> store -> broadcast -> push
      tagging.py           # keyword -> instrument relevance map
      dedup.py              # fingerprint hashing
      impact.py              # keyword heuristic for RSS impact (high/med/low)
      direction.py            # heuristic bullish/bearish/neutral bias per instrument
      broadcast.py          # in-memory pub/sub hub feeding SSE clients
      push.py                # VAPID web push via pywebpush
    workers/
      scheduler.py          # APScheduler registration
      forexfactory.py        # Phase 2 — calendar poll (5 min), reminder + result alerts
      rss.py                  # Phase 3 — RSS poll (2 min), 5 forex/macro feeds
  scripts/
    generate_vapid_keys.py  # generates a VAPID keypair for Web Push
  requirements.txt
  .env.example

frontend/
  src/
    App.jsx                 # live feed, Rules panel, event detail modal, "send test alert"
    api.js                   # backend REST client
    hooks/
      useEventStream.js      # SSE subscription hook
      usePush.js               # Service Worker registration + push subscribe flow
  public/
    sw.js                     # Service Worker: handles `push` and `notificationclick`
    manifest.webmanifest      # makes the app installable (PWA)
  vite.config.js
  .env.example

PLAN.md     # full design doc: source ranking, risks, phased roadmap
README.md   # this file
```

---

## Dev setup

### Prerequisites
- Python 3.11+ (developed on 3.13)
- Node 20.19+ / 22.13+ (developed on Node 22.12 — npm will warn on engines but
  it works)

### 1. Backend

```bash
cd backend
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env
./venv/Scripts/python.exe scripts/generate_vapid_keys.py
# Paste the printed VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY into backend/.env

./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

The SQLite DB file (`forex_notifier.db`) and tables are created automatically
on first boot. The 8-instrument watchlist is auto-seeded into `InstrumentRule`
at app startup (`db.py::init_db`) — not lazily on first API call, since the
scheduler's first poll can fire before the frontend is ever opened.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env
# Paste the same VAPID public key (from step 1) into VITE_VAPID_PUBLIC_KEY

npm run dev
```

Open the printed URL (default `http://127.0.0.1:5173`).

> **Note (Windows):** `vite.config.js` pins the dev server to `host:
> 127.0.0.1` explicitly. Vite's default `localhost` binding resolved to the
> IPv6 loopback (`::1`) only on this machine, which some tools (including
> plain `curl 127.0.0.1`) couldn't reach. Browsers resolve `localhost`/`127.0.0.1`
> fine either way, but the explicit bind avoids surprises.

### 3. Try it

1. In the browser, click **"Enable push notifications"** and grant
   permission. This registers the Service Worker (`public/sw.js`) and posts
   the subscription to `/api/subscribe`.
2. Click **"Send test alert"**. This calls `POST /api/test-event`, which runs
   the full pipeline: dedup check → instrument tagging → store in SQLite →
   broadcast to the live feed over SSE → Web Push to your browser.
3. You should see the event appear instantly in the feed **and** get an OS
   notification — even if you switch to another tab.

> The "Enable push" → grant-permission → receive-a-real-notification flow
> needs an actual interactive browser; it isn't something verifiable from a
> headless/CLI environment. The backend pipeline (dedup, tagging, storage,
> SSE broadcast, and the push-send call itself) has been verified end-to-end
> with curl; the very last hop (OS notification popping up) should be
> confirmed once in your own browser the first time you run this.

### Production note

Web Push requires the page to be served over **HTTPS** (or `localhost` for
dev) to register a Service Worker. To get pushes on your phone per the plan
(always-on, HTTPS-reachable), you'll need a real TLS domain or a tunnel (e.g.
Cloudflare Tunnel) pointed at wherever you deploy the FastAPI + built React
app.

---

## Roadmap (next steps)

Phases 1–4 are done — skeleton/push pipe, the Forex Factory calendar
scraper, RSS news ingestion, and the Rules UI/snooze/detail-view/bias
heuristic described above.

- **Later** — Twitter/X and live-press-conference ingestion for leader/
  political statements (deliberately deferred for now — see `PLAN.md`),
  LLM-based sentiment/impact scoring to replace the current keyword
  heuristics in `services/impact.py` and `services/direction.py`.
