const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${options.method || "GET"} ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  base: API_BASE,
  getEvents: (limit = 50) => request(`/api/events?limit=${limit}`),
  getRules: () => request("/api/rules"),
  updateRule: (instrument, body) =>
    request(`/api/rules/${instrument}?${new URLSearchParams(body)}`, { method: "PATCH" }),
  getVapidPublicKey: () => request("/api/vapid-public-key"),
  subscribe: (subscription) =>
    request("/api/subscribe", { method: "POST", body: JSON.stringify(subscription) }),
  unsubscribe: (subscription) =>
    request("/api/unsubscribe", { method: "POST", body: JSON.stringify(subscription) }),
  sendTestEvent: (payload) =>
    request("/api/test-event", { method: "POST", body: JSON.stringify(payload) }),
};
