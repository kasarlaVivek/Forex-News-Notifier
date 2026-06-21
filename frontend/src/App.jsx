import { useEffect, useState } from "react";
import { useEventStream } from "./hooks/useEventStream";
import { usePush } from "./hooks/usePush";
import { api } from "./api";
import "./App.css";

const IMPACT_COLOR = { high: "#e5484d", med: "#f5a623", low: "#8b8d98" };
const BIAS_COLOR = { bullish: "#2ecc71", bearish: "#e5484d", neutral: "#8b8d98" };
const BIAS_ARROW = { bullish: "▲", bearish: "▼", neutral: "–" };
const DAY_MS = 24 * 60 * 60 * 1000;
const SNOOZE_OPTIONS = [
  { label: "Snooze...", minutes: null },
  { label: "15 min", minutes: 15 },
  { label: "1 hr", minutes: 60 },
  { label: "4 hr", minutes: 240 },
  { label: "24 hr", minutes: 1440 },
];

function App() {
  const { liveEvents, connected } = useEventStream();
  const { supported, subscribed, error, subscribe } = usePush();
  const [history, setHistory] = useState([]);
  const [sending, setSending] = useState(false);
  const [rules, setRules] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [feedView, setFeedView] = useState("breaking");

  useEffect(() => {
    api.getEvents().then(setHistory).catch(() => {});
    refreshRules();
  }, []);

  function refreshRules() {
    api.getRules().then(setRules).catch(() => {});
  }

  async function patchRule(instrument, body) {
    const updated = await api.updateRule(instrument, body);
    setRules((prev) => prev.map((r) => (r.instrument === instrument ? updated : r)));
  }

  const events = mergeEvents(liveEvents, history);
  const scheduledGroups = groupScheduledByDate(events.filter((evt) => evt.scheduled_at));
  const suddenEvents = events.filter(
    (evt) => !evt.scheduled_at && Date.now() - parseUtc(evt.created_at).getTime() <= DAY_MS
  );

  async function sendTestAlert() {
    setSending(true);
    try {
      await api.sendTestEvent({
        title: `Test Alert: FOMC surprise at ${new Date().toLocaleTimeString(undefined, { timeZone: "UTC" })} UTC`,
        body: "Fed cuts rates 50bps — far below 25bps forecast.",
        impact: "high",
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Forex News Notifier</h1>
        <span className={`dot ${connected ? "live" : "down"}`} title={connected ? "Live" : "Disconnected"} />
      </header>

      <section className="controls">
        {supported ? (
          <button onClick={subscribe} disabled={subscribed}>
            {subscribed ? "Push notifications enabled" : "Enable push notifications"}
          </button>
        ) : (
          <span>Push not supported in this browser</span>
        )}
        {error && <span className="error">{error}</span>}
        <button onClick={sendTestAlert} disabled={sending}>
          {sending ? "Sending..." : "Send test alert"}
        </button>
      </section>

      <RulesPanel rules={rules} onPatch={patchRule} />

      <section className="feed">
        <h2>Live feed</h2>
        <div className="feed-tabs">
          <button
            className={feedView === "breaking" ? "active" : ""}
            onClick={() => setFeedView("breaking")}
          >
            Breaking news {suddenEvents.length > 0 && <span className="tab-count">{suddenEvents.length}</span>}
          </button>
          <button
            className={feedView === "scheduled" ? "active" : ""}
            onClick={() => setFeedView("scheduled")}
          >
            Scheduled — week ahead
          </button>
        </div>

        {events.length === 0 && <p className="empty">No events yet. Send a test alert to try the pipe.</p>}

        {feedView === "scheduled" &&
          (scheduledGroups.length > 0 ? (
            <div className="feed-section">
              {scheduledGroups.map(([dateKey, evts]) => (
                <div className="date-group" key={dateKey}>
                  <div className="date-heading">{formatDateHeading(dateKey)}</div>
                  <ul>{evts.map((evt) => renderEventItem(evt, setSelectedEvent))}</ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty">No scheduled events in the week ahead.</p>
          ))}

        {feedView === "breaking" &&
          (suddenEvents.length > 0 ? (
            <div className="feed-section">
              <ul>{suddenEvents.map((evt) => renderEventItem(evt, setSelectedEvent))}</ul>
            </div>
          ) : (
            <p className="empty">No breaking news in the last 24h.</p>
          ))}
      </section>

      {selectedEvent && <EventDetail evt={selectedEvent} onClose={() => setSelectedEvent(null)} />}
    </div>
  );
}

function renderEventItem(evt, onSelect) {
  return (
    <li key={evt.id} className="event" onClick={() => onSelect(evt)}>
      <span className="impact" style={{ background: IMPACT_COLOR[evt.impact] || "#8b8d98" }}>
        {evt.impact}
      </span>
      <div className="event-body">
        <div className="event-title">{evt.title}</div>
        {evt.body && <div className="event-desc">{evt.body}</div>}
        <div className="event-meta">
          <BiasChips bias={evt.bias} instruments={evt.instruments} />
          {evt.scheduled_at
            ? ` · Scheduled: ${formatTime(evt.scheduled_at)}`
            : ` · ${formatTime(evt.created_at)}`}
        </div>
      </div>
    </li>
  );
}

const WEEK_AHEAD_DAYS = 7;

// Calendar entries (FOMC, CPI, NFP...) carry a known scheduled_at. The
// scheduled section is a forward-looking calendar — the week ahead, today
// through +6 days — grouped by date (soonest first) and chronological within
// each day, so it reads top-to-bottom like an upcoming agenda. Anything
// already in the past, or further out than a week, is left out rather than
// cluttering that view; the full history is still available via the raw
// event list elsewhere. Unscheduled news (RSS/breaking) has no date of its
// own to group by — it's shown as a single reverse-chronological list
// instead, in continuation, the same way the feed has always rendered.
function groupScheduledByDate(scheduledEvents) {
  const todayKey = new Date().toISOString().slice(0, 10);
  const cutoffKey = new Date(Date.now() + WEEK_AHEAD_DAYS * 86400000).toISOString().slice(0, 10);

  const groups = new Map();
  for (const evt of scheduledEvents) {
    const dateKey = parseUtc(evt.scheduled_at).toISOString().slice(0, 10);
    if (dateKey < todayKey || dateKey >= cutoffKey) continue;
    if (!groups.has(dateKey)) groups.set(dateKey, []);
    groups.get(dateKey).push(evt);
  }
  for (const evts of groups.values()) {
    evts.sort((a, b) => parseUtc(a.scheduled_at) - parseUtc(b.scheduled_at));
  }
  return [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : 1));
}

function formatDateHeading(dateKey) {
  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  if (dateKey === today) return "Today";
  if (dateKey === tomorrow) return "Tomorrow";
  return new Date(`${dateKey}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function BiasChips({ bias, instruments }) {
  if (!instruments || instruments.length === 0) return null;
  return (
    <span className="bias-chips">
      {instruments.map((instrument) => {
        const value = bias?.[instrument] || "neutral";
        return (
          <span key={instrument} className="bias-chip" style={{ color: BIAS_COLOR[value] }} title={`${instrument}: ${value}`}>
            {instrument} {BIAS_ARROW[value]}
          </span>
        );
      })}
    </span>
  );
}

function EventDetail({ evt, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        <span className="impact" style={{ background: IMPACT_COLOR[evt.impact] || "#8b8d98" }}>
          {evt.impact}
        </span>
        <h3>{evt.title}</h3>
        <div className="event-meta">
          {evt.source} {evt.currency ? `· ${evt.currency}` : ""}
          {evt.scheduled_at
            ? ` · Scheduled: ${formatTime(evt.scheduled_at)}`
            : ` · ${formatTime(evt.created_at)}`}
        </div>
        {evt.body && <p className="event-desc">{evt.body}</p>}

        {(evt.forecast || evt.previous || evt.actual) && (
          <div className="detail-grid">
            {evt.previous && <div><strong>Previous</strong><span>{evt.previous}</span></div>}
            {evt.forecast && <div><strong>Forecast</strong><span>{evt.forecast}</span></div>}
            {evt.actual && <div><strong>Actual</strong><span>{evt.actual}</span></div>}
            {evt.surprise_score != null && (
              <div><strong>Surprise</strong><span>{evt.surprise_score > 0 ? "+" : ""}{evt.surprise_score}</span></div>
            )}
          </div>
        )}

        <div className="detail-bias">
          <strong>Possible impact (heuristic, not a prediction):</strong>
          <div className="bias-chips large">
            {(evt.instruments || []).map((instrument) => {
              const value = evt.bias?.[instrument] || "neutral";
              return (
                <span key={instrument} className="bias-chip" style={{ color: BIAS_COLOR[value] }}>
                  {instrument} {BIAS_ARROW[value]} {value}
                </span>
              );
            })}
          </div>
        </div>

        {evt.url && (
          <a href={evt.url} target="_blank" rel="noreferrer" className="detail-link">
            View source ↗
          </a>
        )}
      </div>
    </div>
  );
}

function RulesPanel({ rules, onPatch }) {
  const [open, setOpen] = useState(false);
  if (rules.length === 0) return null;

  return (
    <section className="rules-panel">
      <button className="rules-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide rules ▲" : "Rules ▼"}
      </button>
      {open && (
        <ul className="rules-list">
          {rules.map((rule) => {
            const snoozedUntil = isSnoozed(rule) ? formatTime(rule.snoozed_until) : null;
            return (
              <li key={rule.instrument} className="rule-row">
                <label className="rule-enabled">
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={(e) => onPatch(rule.instrument, { enabled: e.target.checked })}
                  />
                  {rule.instrument}
                </label>
                <select
                  value={rule.min_impact}
                  onChange={(e) => onPatch(rule.instrument, { min_impact: e.target.value })}
                >
                  <option value="low">low</option>
                  <option value="med">med</option>
                  <option value="high">high</option>
                </select>
                <select
                  value=""
                  onChange={(e) => {
                    const minutes = Number(e.target.value);
                    if (!Number.isNaN(minutes) && e.target.value !== "") {
                      onPatch(rule.instrument, { snooze_minutes: minutes });
                    }
                  }}
                >
                  {SNOOZE_OPTIONS.map((opt) => (
                    <option key={opt.label} value={opt.minutes ?? ""} disabled={opt.minutes === null}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {snoozedUntil ? (
                  <span className="snooze-status">
                    Snoozed until {snoozedUntil}
                    <button className="unsnooze" onClick={() => onPatch(rule.instrument, { snooze_minutes: 0 })}>
                      clear
                    </button>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function isSnoozed(rule) {
  return rule.snoozed_until && parseUtc(rule.snoozed_until) > new Date();
}

function mergeEvents(live, history) {
  const byId = new Map();
  for (const evt of [...live, ...history]) {
    if (evt.id != null) byId.set(evt.id, { ...byId.get(evt.id), ...evt });
  }
  // A {"id", "deleted": true} message (test alerts auto-expire after ~1 min,
  // see workers/cleanup.py) merges into the existing record — drop it here
  // rather than ever rendering it.
  return [...byId.values()]
    .filter((evt) => !evt.deleted)
    .sort((a, b) => parseUtc(b.created_at) - parseUtc(a.created_at));
}

// The backend stores/serializes timestamps as UTC but without a timezone
// designator (a SQLite + naive-datetime round-trip quirk) — e.g.
// "2026-06-21T06:11:11.93". Without a trailing "Z", the JS Date constructor
// parses date-time strings as local time, silently shifting every event time
// in the feed by the browser's UTC offset. Treat any designator-less ISO
// string as UTC explicitly.
function parseUtc(ts) {
  if (!ts) return new Date(NaN);
  const hasDesignator = /[zZ]|[+-]\d\d:\d\d$/.test(ts);
  return new Date(hasDesignator ? ts : `${ts}Z`);
}

function formatTime(ts) {
  if (!ts) return "";
  // Always display in UTC (not the browser's local timezone) — this app's
  // data (scheduled_at, created_at) is UTC throughout, and converting to
  // local time per-viewer just adds confusion for a single-user app.
  const formatted = parseUtc(ts).toLocaleString(undefined, {
    timeZone: "UTC",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${formatted} UTC`;
}

export default App;
