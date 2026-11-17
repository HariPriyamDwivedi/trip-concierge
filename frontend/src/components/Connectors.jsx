import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { signInUrl } from "../api.js";

const ICON = { calendar: "calendar", mail: "mail" };
const MARK = { google: "G", microsoft: "M" };

// Top-bar menu: connect Google and/or Microsoft once (each sign-in serves both
// Calendar and Mail), then switch the connectors on or off for this trip.
export default function Connectors({ sessionId, connectors, accounts, onToggle, onDisconnect, onMailFrom }) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(null);
  const ref = useRef(null);
  const on = connectors.filter((c) => c.connected).length;
  const providers = accounts?.providers || [];
  const linked = providers.filter((p) => p.account);
  const signInOptions = providers.filter((p) => p.available && !p.account);

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

  const busy = (key, fn) => async () => {
    setPending(key);
    try {
      await fn();
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="connectors" ref={ref}>
      <button className="btn ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog">
        <Icon name="plug" size={16} /> Connectors
        {on > 0 && <span className="count">{on}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Connectors">
          <p className="popover-title">Connectors for this trip</p>
          <p className="popover-intro">
            Trip Concierge only uses these to plan this trip. One sign-in connects both your calendar and mail; you can connect
            Google and Microsoft together.
          </p>

          <section className="accounts" aria-label="Accounts">
            <p className="section-label">Accounts</p>
            {linked.map((p) => (
              <div key={p.id} className="account-row">
                <span className={`provider-mark ${p.id}`} aria-hidden="true">{MARK[p.id]}</span>
                <div className="account-body">
                  <p className="account-name">{p.label}</p>
                  <p className="connector-meta">{p.account.account} · Calendar + Mail</p>
                </div>
                <button className="link" disabled={pending === p.id} onClick={busy(p.id, () => onDisconnect(p.id))}>
                  Sign out
                </button>
              </div>
            ))}
            {signInOptions.length > 0 && (
              <div className="sign-in">
                {signInOptions.map((p) => (
                  <a key={p.id} className="btn ghost small" href={signInUrl(sessionId, p.id)}>
                    <span className={`provider-mark small ${p.id}`} aria-hidden="true">{MARK[p.id]}</span>
                    {linked.length ? `Also connect ${p.label}` : `Connect ${p.label}`}
                  </a>
                ))}
              </div>
            )}
            {!providers.some((p) => p.available) && (
              <p className="connector-meta">Google / Microsoft sign-in isn't configured on this server; demo data is used.</p>
            )}
          </section>

          <p className="section-label">Use for this trip</p>
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
                  {c.id === "mail" && linked.length > 1 && (
                    <label className="send-from">
                      Send from
                      <select value={accounts.mail_from || ""} onChange={(e) => onMailFrom(e.target.value)} disabled={pending === "mail_from"}>
                        {linked.map((p) => (
                          <option key={p.id} value={p.id}>{p.account.account} ({p.label})</option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
                <button
                  role="switch"
                  aria-checked={c.connected}
                  aria-label={`${c.name} connector`}
                  className={`switch ${c.connected ? "on" : ""}`}
                  disabled={pending === c.id}
                  onClick={busy(c.id, () => onToggle(c.id, !c.connected))}
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
