import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";

const SHOWN_KEY = "trip-concierge:alerts-shown";
const WINDOW_MS = 15 * 60 * 1000; // fire alerts that came due in the last 15 minutes

function loadShown() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SHOWN_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveShown(set) {
  try {
    localStorage.setItem(SHOWN_KEY, JSON.stringify([...set].slice(-500)));
  } catch {}
}

const dayLabel = (d) => {
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

// Bell in the top bar: upcoming trip alerts, plus browser notifications while the
// app is open (shortcut: no service worker / Web Push yet, so a closed tab gets none).
export default function Notifications({ notifications, onAlert }) {
  const [open, setOpen] = useState(false);
  const [permission, setPermission] = useState(() => (typeof Notification === "undefined" ? "unsupported" : Notification.permission));
  const [now, setNow] = useState(() => Date.now());
  const ref = useRef(null);

  // Check every 30 s for alerts that just came due.
  useEffect(() => {
    const tick = () => {
      const t = Date.now();
      setNow(t);
      const shown = loadShown();
      for (const n of notifications) {
        const due = new Date(n.due_at).getTime();
        if (due <= t && t - due < WINDOW_MS && !shown.has(n.id)) {
          shown.add(n.id);
          onAlert(n);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            new Notification(n.title, { body: n.body, tag: n.id });
          }
        }
      }
      saveShown(shown);
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, [notifications, onAlert]);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (e.type === "keydown" ? e.key === "Escape" : !ref.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const upcoming = notifications.filter((n) => new Date(n.due_at).getTime() > now - WINDOW_MS);
  const soon = upcoming.filter((n) => new Date(n.due_at).getTime() < now + 48 * 3600 * 1000).length;
  const groups = [];
  for (const n of upcoming.slice(0, 30)) {
    const label = dayLabel(new Date(n.due_at));
    if (groups.at(-1)?.label !== label) groups.push({ label, items: [] });
    groups.at(-1).items.push(n);
  }

  const enable = async () => setPermission(await Notification.requestPermission());

  return (
    <div className="connectors" ref={ref}>
      <button
        className="btn ghost"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Trip alerts${soon ? `, ${soon} in the next 48 hours` : ""}`}
      >
        <Icon name="bell" size={16} />
        {soon > 0 && <span className="count">{soon}</span>}
      </button>
      {open && (
        <div className="popover alerts" role="dialog" aria-label="Trip alerts">
          <p className="popover-title">Trip alerts</p>
          {permission === "default" && (
            <div className="alert-permission">
              <p className="small">Get a pop-up when an alert is due, while Trip Concierge is open.</p>
              <button className="btn primary small" onClick={enable}>
                Turn on alerts
              </button>
            </div>
          )}
          {permission === "denied" && <p className="small muted">Browser notifications are blocked; alerts still show here.</p>}
          {groups.length ? (
            groups.map((g) => (
              <div key={g.label}>
                <p className="alert-day">{g.label}</p>
                <ul className="alert-list">
                  {g.items.map((n) => (
                    <li key={n.id} className={new Date(n.due_at).getTime() <= now ? "due" : ""}>
                      <span className="alert-time">
                        {new Date(n.due_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <div>
                        <p className="alert-title">{n.title}</p>
                        <p className="small muted">{n.body}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          ) : (
            <p className="small muted">No upcoming alerts. Add bookings or activities to your trip to get them.</p>
          )}
        </div>
      )}
    </div>
  );
}
