// Thin client for the backend API (see backend/app.py). All calls are same-origin
// under /api: nginx proxies them in production, Vite in development.

async function request(path, options) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("Can't reach the server. Is the backend running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

export const getSession = (sessionId) => request(`/sessions/${encodeURIComponent(sessionId)}`);

export function uploadFile(sessionId, file) {
  const body = new FormData();
  body.append("session_id", sessionId);
  body.append("file", file);
  return request("/upload", { method: "POST", body });
}

export const setConnector = (sessionId, connectorId, connected) =>
  request(`/sessions/${encodeURIComponent(sessionId)}/connectors/${connectorId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connected }),
  });

export const disconnectAccount = (sessionId, connectorId) =>
  request(`/sessions/${encodeURIComponent(sessionId)}/connectors/${connectorId}/account`, { method: "DELETE" });

// Full-page navigation: the API redirects to Google/Microsoft and back to "/?oauth=…".
export const signInUrl = (sessionId, connectorId, provider) =>
  `/api/oauth/${provider}/start?` + new URLSearchParams({ session_id: sessionId, connector: connectorId });

// Streams one chat turn (server-sent events). Calls onTool(name) when the agent
// starts a tool and onDelta(text) for each piece of the reply; resolves with the
// final {reply, sources, trip}.
export async function streamChat(sessionId, message, { onTool, onDelta }) {
  let res;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch {
    throw new Error("Can't reach the server. Is the backend running?");
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`);
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
      else if (event === "error") throw new Error(data.message);
    }
  }
  if (!done) throw new Error("The reply was cut off. Please try again.");
  return done;
}

export const addItem = (sessionId, item) =>
  request(`/sessions/${encodeURIComponent(sessionId)}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });

export const removeItem = (sessionId, itemId) =>
  request(`/sessions/${encodeURIComponent(sessionId)}/items/${itemId}`, { method: "DELETE" });

export const getSeasonal = (when) => request(`/seasonal?when=${encodeURIComponent(when)}`);
