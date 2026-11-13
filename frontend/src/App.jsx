import { useCallback, useEffect, useState } from "react";
import { addItem, disconnectAccount, getSeasonal, getSession, removeItem, setConnector, streamChat, uploadFile } from "./api.js";
import Chat from "./components/Chat.jsx";
import Connectors from "./components/Connectors.jsx";
import Notifications from "./components/Notifications.jsx";
import TripBoard, { TripSummary } from "./components/TripBoard.jsx";
import Icon from "./components/Icon.jsx";

const STORAGE_KEY = "trip-concierge:session";

const newSessionId = () => "trip-" + Math.random().toString(36).slice(2, 12);

// Remember the current trip across reloads; storage can be unavailable (private mode).
function loadSessionId() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
  } catch {}
  return newSessionId();
}

function saveSessionId(id) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {}
}

export default function App() {
  const [sessionId, setSessionId] = useState(loadSessionId);
  const [messages, setMessages] = useState([]);
  const [trip, setTrip] = useState({});
  const [documents, setDocuments] = useState([]);
  const [connectors, setConnectors] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [seasonal, setSeasonal] = useState(null);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null); // {kind: "error" | "info", text}
  const [tab, setTab] = useState("chat"); // mobile only: which pane is visible

  // Destinations in season this month, for the welcome screen.
  useEffect(() => {
    const month = new Date().toLocaleString("en-US", { month: "long" });
    getSeasonal(month).then(setSeasonal).catch(() => {});
  }, []);

  // Back from Google/Microsoft sign-in: show the outcome once, then clean the URL.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (!q.has("oauth")) return;
    const name = q.get("connector") === "mail" ? "Mail" : "Calendar";
    setNotice(
      q.get("oauth") === "connected"
        ? { kind: "info", text: `${name} connected as ${q.get("account")}.` }
        : { kind: "error", text: `Sign-in didn't finish: ${q.get("message")}` },
    );
    window.history.replaceState(null, "", "/");
  }, []);

  useEffect(() => {
    saveSessionId(sessionId);
    let cancelled = false;
    getSession(sessionId)
      .then((view) => {
        if (cancelled) return;
        setMessages(view.messages);
        setTrip(view.trip);
        setDocuments(view.documents);
        setConnectors(view.connectors || []);
        setAlerts(view.notifications || []);
      })
      .catch((err) => !cancelled && setNotice({ kind: "error", text: err.message }));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const send = useCallback(
    async (text) => {
      setNotice(null);
      // The reply streams into a placeholder message (always the last one).
      const patchLast = (fn) => setMessages((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
      setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "", sources: [], streaming: true }]);
      setSending(true);
      try {
        const res = await streamChat(sessionId, text, {
          onTool: (name) => patchLast((msg) => ({ ...msg, activity: name })),
          onDelta: (piece) => patchLast((msg) => ({ ...msg, text: msg.text + piece, activity: null })),
        });
        patchLast(() => ({ role: "assistant", text: res.reply, sources: res.sources }));
        setTrip(res.trip);
        setAlerts(res.notifications || []);
      } catch (err) {
        setMessages((m) => (m[m.length - 1]?.streaming && !m[m.length - 1].text ? m.slice(0, -1) : m));
        patchLast((msg) => (msg.streaming ? { ...msg, streaming: false } : msg));
        setNotice({ kind: "error", text: err.message });
      } finally {
        setSending(false);
      }
    },
    [sessionId],
  );

  const upload = useCallback(
    async (file) => {
      setNotice({ kind: "info", text: `Uploading ${file.name}…` });
      try {
        const res = await uploadFile(sessionId, file);
        setDocuments(res.documents);
        setNotice({ kind: "info", text: `${res.filename} added — ask me anything about it.` });
      } catch (err) {
        setNotice({ kind: "error", text: `Couldn't upload ${file.name}: ${err.message}` });
      }
    },
    [sessionId],
  );

  const toggleConnector = useCallback(
    async (id, connected) => {
      try {
        setConnectors(await setConnector(sessionId, id, connected));
      } catch (err) {
        setNotice({ kind: "error", text: err.message });
      }
    },
    [sessionId],
  );

  const disconnect = useCallback(
    async (id) => {
      try {
        setConnectors(await disconnectAccount(sessionId, id));
      } catch (err) {
        setNotice({ kind: "error", text: err.message });
      }
    },
    [sessionId],
  );

  const applyBoard = (res) => {
    setTrip(res.trip);
    setAlerts(res.notifications);
  };
  const addTripItem = useCallback(async (item) => applyBoard(await addItem(sessionId, item)), [sessionId]);
  const removeTripItem = useCallback(
    async (id) => {
      try {
        applyBoard(await removeItem(sessionId, id));
      } catch (err) {
        setNotice({ kind: "error", text: err.message });
      }
    },
    [sessionId],
  );
  const showAlert = useCallback((n) => setNotice({ kind: "info", text: `🔔 ${n.title} — ${n.body}` }), []);

  const startNewTrip = () => {
    setMessages([]);
    setTrip({});
    setDocuments([]);
    setAlerts([]);
    setNotice(null);
    setTab("chat");
    setSessionId(newSessionId());
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="plane" size={16} />
          </span>
          <span>Trip Concierge</span>
        </div>
        <TripSummary trip={trip} />
        <nav className="tabs" aria-label="View">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")} aria-pressed={tab === "chat"}>
            <Icon name="chat" size={16} /> Chat
          </button>
          <button className={tab === "trip" ? "active" : ""} onClick={() => setTab("trip")} aria-pressed={tab === "trip"}>
            <Icon name="route" size={16} /> Trip
          </button>
        </nav>
        <Notifications notifications={alerts} onAlert={showAlert} />
        <Connectors sessionId={sessionId} connectors={connectors} onToggle={toggleConnector} onDisconnect={disconnect} />
        <button className="btn ghost" onClick={startNewTrip}>
          <Icon name="plus" size={16} /> New trip
        </button>
      </header>

      <main className={`layout show-${tab}`}>
        <Chat
          messages={messages}
          sending={sending}
          notice={notice}
          onDismissNotice={() => setNotice(null)}
          onSend={send}
          onUpload={upload}
          seasonal={seasonal}
        />
        <TripBoard
          trip={trip}
          documents={documents}
          onUpload={upload}
          onAsk={send}
          busy={sending}
          onAddItem={addTripItem}
          onRemoveItem={removeTripItem}
        />
      </main>
    </div>
  );
}
