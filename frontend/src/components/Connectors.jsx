import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";

const ICON = { calendar: "calendar", mail: "mail" };

// Top-bar menu to switch the Mail and Calendar connectors on or off for this trip.
export default function Connectors({ connectors, onToggle }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(null);
  const ref = useRef(null);
  const connected = connectors.filter((c) => c.connected).length;

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

  const toggle = async (c) => {
    setPending(c.id);
    try {
      await onToggle(c.id, !c.connected);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="connectors" ref={ref}>
      <button className="btn ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog">
        <Icon name="plug" size={16} /> Connectors
        {connected > 0 && <span className="count">{connected}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Connectors">
          <p className="popover-title">Connectors for this trip</p>
          <p className="popover-intro">
            Trip Concierge only uses these to plan this trip. Turn one on to let the concierge use it.
          </p>
          <ul>
            {connectors.map((c) => (
              <li key={c.id} className="connector">
                <span className="connector-icon">
                  <Icon name={ICON[c.id] || "plug"} size={18} />
                </span>
                <div className="connector-body">
                  <p className="connector-name">
                    {c.name}
                    <span className={`badge ${c.mode === "live" ? "ok" : ""}`}>{c.mode === "live" ? "Live" : c.mode === "demo" ? "Demo" : "Not set up"}</span>
                  </p>
                  <p className="connector-text">{c.purpose}</p>
                  <p className="connector-meta">
                    {c.provider} · {c.limits}
                  </p>
                </div>
                <button
                  role="switch"
                  aria-checked={c.connected}
                  aria-label={`${c.name} connector`}
                  className={`switch ${c.connected ? "on" : ""}`}
                  disabled={pending === c.id}
                  onClick={() => toggle(c)}
                >
                  <span />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
