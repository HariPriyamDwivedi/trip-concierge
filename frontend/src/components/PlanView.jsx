import { useCallback, useEffect, useState } from "react";
import {
  addItem,
  disconnectAccount,
  setMailFrom,
  getSeasonal,
  getTrip,
  listMedia,
  listTrips,
  removeItem,
  setConnector,
  streamChat,
  uploadDocument,
  uploadMedia,
} from "../api.js";
import Camera from "./Camera.jsx";
import Chat from "./Chat.jsx";
import Connectors from "./Connectors.jsx";
import Icon from "./Icon.jsx";
import { Viewer } from "./Memories.jsx";
import Notifications from "./Notifications.jsx";
import TripBoard, { TripSummary } from "./TripBoard.jsx";

// Text/PDF go to the concierge to read; anything else is kept as a memory.
const isDocument = (file) => /\.(txt|md|pdf)$/i.test(file.name);

// One trip: chat with the concierge beside the trip board.
export default function PlanView({ tripId, onTripChanged, onNewTrip, notice, setNotice }) {
  const [messages, setMessages] = useState([]);
  const [trip, setTrip] = useState({});
  const [meta, setMeta] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [connectors, setConnectors] = useState([]);
  const [accounts, setAccounts] = useState({ providers: [], mail_from: null });
  const [alerts, setAlerts] = useState([]);
  const [seasonal, setSeasonal] = useState(null);
  const [sending, setSending] = useState(false);
  const [camera, setCamera] = useState(false);
  const [media, setMedia] = useState([]); // this trip's photos, videos and files
  const [viewing, setViewing] = useState(null);
  const [trips, setTrips] = useState([]);

  const loadMedia = useCallback(() => {
    listMedia({ trip_id: tripId }).then(setMedia).catch(() => {});
  }, [tripId]);
  useEffect(loadMedia, [loadMedia]);
  useEffect(() => {
    if (viewing !== null) listTrips().then(setTrips).catch(() => {});
  }, [viewing]);
  const [tab, setTab] = useState("chat"); // small screens: which pane is visible

  useEffect(() => {
    const month = new Date().toLocaleString("en-US", { month: "long" });
    getSeasonal(month).then(setSeasonal).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setTrip({});
    getTrip(tripId)
      .then((view) => {
        if (cancelled) return;
        setMeta(view.trip_meta);
        setMessages(view.messages);
        setTrip(view.trip);
        setDocuments(view.documents);
        setConnectors(view.connectors || []);
        setAccounts(view.accounts || { providers: [], mail_from: null });
        setAlerts(view.notifications || []);
      })
      .catch((err) => !cancelled && setNotice({ kind: "error", text: err.message }));
    return () => {
      cancelled = true;
    };
  }, [tripId, setNotice]);

  const send = useCallback(
    async (text) => {
      setNotice(null);
      // The reply streams into a placeholder message (always the last one).
      const patchLast = (fn) => setMessages((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
      setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "", sources: [], streaming: true }]);
      setSending(true);
      try {
        const res = await streamChat(tripId, text, {
          onTool: (name) => patchLast((msg) => ({ ...msg, activity: name })),
          onDelta: (piece) => patchLast((msg) => ({ ...msg, text: msg.text + piece, activity: null })),
        });
        patchLast(() => ({ role: "assistant", text: res.reply, sources: res.sources }));
        setTrip(res.trip);
        setAlerts(res.notifications || []);
        onTripChanged?.();
      } catch (err) {
        setMessages((m) => (m[m.length - 1]?.streaming && !m[m.length - 1].text ? m.slice(0, -1) : m));
        patchLast((msg) => (msg.streaming ? { ...msg, streaming: false } : msg));
        setNotice({ kind: "error", text: err.message });
      } finally {
        setSending(false);
      }
    },
    [tripId, setNotice, onTripChanged],
  );

  const upload = useCallback(
    async (file) => {
      setNotice({ kind: "info", text: `Uploading ${file.name}…` });
      try {
        if (isDocument(file)) {
          const res = await uploadDocument(tripId, file);
          setDocuments(res.documents);
          setNotice({ kind: "info", text: `${res.filename} added — ask me anything about it.` });
        } else {
          await uploadMedia(file, { trip_id: tripId }, (p) =>
            setNotice({ kind: "info", text: `Uploading ${file.name}… ${Math.round(p * 100)}%` }),
          );
          setNotice({ kind: "info", text: `${file.name} saved to this trip's memories.` });
          loadMedia();
          onTripChanged?.();
        }
      } catch (err) {
        setNotice({ kind: "error", text: `Couldn't upload ${file.name}: ${err.message}` });
      }
    },
    [tripId, setNotice, onTripChanged, loadMedia],
  );

  const showAlert = useCallback((n) => setNotice({ kind: "info", text: `🔔 ${n.title} — ${n.body}` }), [setNotice]);

  const run = (fn) => async (...args) => {
    try {
      return await fn(...args);
    } catch (err) {
      setNotice({ kind: "error", text: err.message });
    }
  };
  const applyBoard = (res) => {
    setTrip(res.trip);
    setAlerts(res.notifications);
    onTripChanged?.();
  };

  return (
    <div className="plan">
      <div className="plan-bar">
        <div className="plan-title">
          <p className="eyebrow">Trip</p>
          <p className="plan-name">{meta?.title || "New trip"}</p>
        </div>
        <TripSummary trip={trip} />
        <nav className="tabs" aria-label="Pane">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")} aria-pressed={tab === "chat"}>
            <Icon name="chat" size={16} /> Chat
          </button>
          <button className={tab === "trip" ? "active" : ""} onClick={() => setTab("trip")} aria-pressed={tab === "trip"}>
            <Icon name="route" size={16} /> Board
          </button>
        </nav>
        <Notifications notifications={alerts} onAlert={showAlert} />
        <Connectors
          sessionId={tripId}
          connectors={connectors}
          onToggle={run(async (id, on) => setConnectors(await setConnector(tripId, id, on)))}
          accounts={accounts}
          onDisconnect={run(async (provider) => {
            const r = await disconnectAccount(tripId, provider);
            setConnectors(r.connectors);
            setAccounts(r.accounts);
          })}
          onMailFrom={run(async (provider) => {
            const r = await setMailFrom(tripId, provider);
            setConnectors(r.connectors);
            setAccounts(r.accounts);
          })}
        />
        <button className="btn ghost" onClick={onNewTrip}>
          <Icon name="plus" size={16} /> New trip
        </button>
      </div>

      <div className={`layout show-${tab}`}>
        <Chat
          messages={messages}
          sending={sending}
          notice={notice}
          onDismissNotice={() => setNotice(null)}
          onSend={send}
          onUpload={upload}
          onCamera={() => setCamera(true)}
          seasonal={seasonal}
        />
        <TripBoard
          trip={trip}
          documents={documents}
          onUpload={upload}
          onAsk={send}
          busy={sending}
          onAddItem={async (item) => applyBoard(await addItem(tripId, item))}
          onRemoveItem={run(async (id) => applyBoard(await removeItem(tripId, id)))}
          memories={media}
          onOpenMemory={setViewing}
          onCamera={() => setCamera(true)}
        />
      </div>

      {camera && (
        <Camera
          tripId={tripId}
          onClose={() => setCamera(false)}
          onSaved={(m) => {
            setCamera(false);
            setNotice({ kind: "info", text: `${m.kind === "video" ? "Video" : "Photo"} saved to this trip's memories.` });
            loadMedia();
            onTripChanged?.();
          }}
        />
      )}
      {viewing !== null && media[viewing] && (
        <Viewer
          items={media}
          index={viewing}
          trips={trips}
          onClose={() => setViewing(null)}
          onMove={(d) => setViewing((i) => Math.min(media.length - 1, Math.max(0, i + d)))}
          onChanged={(m) => {
            setMedia((list) => (m.trip_id === tripId ? list.map((x) => (x.id === m.id ? m : x)) : list.filter((x) => x.id !== m.id)));
            setNotice({ kind: "info", text: "Saved." });
          }}
          onDeleted={(id) => {
            setViewing(null);
            setMedia((list) => list.filter((x) => x.id !== id));
            onTripChanged?.();
          }}
        />
      )}
    </div>
  );
}
