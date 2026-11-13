import { useCallback, useEffect, useState } from "react";
import { getSession, sendChat, setConnector, uploadFile } from "./api.js";
import Chat from "./components/Chat.jsx";
import Connectors from "./components/Connectors.jsx";
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
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null); // {kind: "error" | "info", text}
  const [tab, setTab] = useState("chat"); // mobile only: which pane is visible

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
      })
      .catch((err) => !cancelled && setNotice({ kind: "error", text: err.message }));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const send = useCallback(
    async (text) => {
      setNotice(null);
      setMessages((m) => [...m, { role: "user", text }]);
      setSending(true);
      try {
        const res = await sendChat(sessionId, text);
        setMessages((m) => [...m, { role: "assistant", text: res.reply, sources: res.sources }]);
        setTrip(res.trip);
      } catch (err) {
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

  const startNewTrip = () => {
    setMessages([]);
    setTrip({});
    setDocuments([]);
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
        <Connectors connectors={connectors} onToggle={toggleConnector} />
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
        />
        <TripBoard trip={trip} documents={documents} onUpload={upload} onAsk={send} busy={sending} />
      </main>
    </div>
  );
}
