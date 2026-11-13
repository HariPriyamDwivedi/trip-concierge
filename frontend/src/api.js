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

export const sendChat = (sessionId, message) =>
  request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });

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
