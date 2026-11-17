// Thin client for the backend API (see backend/app.py). All calls are same-origin
// under /api (nginx proxies them in production, Vite in development), and the
// HttpOnly session cookie travels with them automatically.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : null;
    throw new ApiError(detail || `Request failed (${res.status})`, res.status);
  }
  return data;
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body ?? {}),
});
const trip = (id) => `/trips/${encodeURIComponent(id)}`;

// ── Auth & profile ─────────────────────────────────────────────────────────
export const requestCode = (identifier) => request("/auth/request-code", json("POST", { identifier }));
export const verifyCode = (identifier, code) => request("/auth/verify", json("POST", { identifier, code }));
export const logout = () => request("/auth/logout", { method: "POST" });
export const getMe = () => request("/me");
export const updateMe = (fields) => request("/me", json("PATCH", fields));

// ── Trips ──────────────────────────────────────────────────────────────────
export const listTrips = () => request("/trips");
export const createTrip = (title) => request("/trips", json("POST", { title }));
export const renameTrip = (id, title) => request(trip(id), json("PATCH", { title }));
export const getTrip = (id) => request(trip(id));
export const addItem = (id, item) => request(`${trip(id)}/items`, json("POST", item));
export const removeItem = (id, itemId) => request(`${trip(id)}/items/${itemId}`, { method: "DELETE" });
export const setConnector = (id, connectorId, connected) =>
  request(`${trip(id)}/connectors/${connectorId}`, json("PUT", { connected }));
// One Google or Microsoft sign-in connects both Mail and Calendar.
export const disconnectAccount = (id, provider) => request(`${trip(id)}/accounts/${provider}`, { method: "DELETE" });
export const setMailFrom = (id, provider) => request(`${trip(id)}/mail-from`, json("PUT", { provider }));
export const signInUrl = (tripId, provider) => `/api/oauth/${provider}/start?` + new URLSearchParams({ trip_id: tripId });
export const getSeasonal = (when) => request(`/seasonal?when=${encodeURIComponent(when)}`);

export function uploadDocument(id, file) {
  const body = new FormData();
  body.append("file", file);
  return request(`${trip(id)}/documents`, { method: "POST", body });
}

// Streams one chat turn (server-sent events). Calls onTool(name) when the agent
// starts a tool and onDelta(text) for each piece of the reply; resolves with the
// final {reply, sources, trip, notifications}.
export async function streamChat(id, message, { onTool, onDelta }) {
  let res;
  try {
    res = await fetch(`/api${trip(id)}/chat/stream`, json("POST", { message }));
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0);
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`, res.status);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let done = null;
  for (;;) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += value;
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] || "{}");
      if (event === "tool") onTool?.(data.name);
      else if (event === "delta") onDelta?.(data.text);
      else if (event === "done") done = data;
      else if (event === "error") throw new ApiError(data.message, 500);
    }
  }
  if (!done) throw new ApiError("The reply was cut off. Please try again.", 0);
  return done;
}

// ── Memories ───────────────────────────────────────────────────────────────
export const listMedia = (filters = {}) =>
  request("/media?" + new URLSearchParams(Object.entries(filters).filter(([, v]) => v)));
export const updateMedia = (mediaId, fields) => request(`/media/${mediaId}`, json("PATCH", fields));
export const deleteMedia = (mediaId) => request(`/media/${mediaId}`, { method: "DELETE" });
export const listPlaces = () => request("/places");

// Upload with progress (fetch has no upload progress, so XHR). meta: {trip_id,
// caption, place, lat, lng, taken_at}; onProgress(0..1).
export function uploadMedia(file, meta = {}, onProgress) {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    for (const [k, v] of Object.entries(meta)) if (v !== undefined && v !== null && v !== "") body.append(k, v);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/media");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(typeof data.detail === "string" ? data.detail : `Upload failed (${xhr.status})`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed: can't reach the server.", 0));
    xhr.send(body);
  });
}
