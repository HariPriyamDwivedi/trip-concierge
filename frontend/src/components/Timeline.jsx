import { useState } from "react";
import Icon from "./Icon.jsx";

export const KIND = {
  train: { icon: "train", label: "Train", from: "From station", to: "To station", ref: "PNR", start: "Departs", end: "Arrives" },
  flight: { icon: "plane", label: "Flight", from: "From airport", to: "To airport", ref: "Flight / PNR", start: "Departs", end: "Lands" },
  bus: { icon: "bus", label: "Bus", from: "Boarding point", to: "Drop point", ref: "Booking ref", start: "Departs", end: "Arrives" },
  stay: { icon: "bed", label: "Stay", from: "Address / area", to: null, ref: "Booking ref", start: "Check-in", end: "Check-out" },
  activity: { icon: "star", label: "Activity", from: "Where", to: null, ref: "Booking ref", start: "Starts", end: "Ends" },
};

const when = (iso) =>
  iso
    ? new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "";

const EMPTY = { kind: "train", title: "", starts_at: "", ends_at: "", from_place: "", to_place: "", reference: "" };

function AddForm({ onAdd, onCancel }) {
  const [f, setF] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const k = KIND[f.kind];
  const set = (key) => (e) => setF({ ...f, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const item = Object.fromEntries(Object.entries(f).map(([key, v]) => [key, v.trim ? v.trim() || null : v]));
    try {
      await onAdd(item);
      setF(EMPTY);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="item-form" onSubmit={submit}>
      <div className="kind-picker" role="radiogroup" aria-label="Type">
        {Object.entries(KIND).map(([key, v]) => (
          <button
            type="button"
            key={key}
            role="radio"
            aria-checked={f.kind === key}
            className={f.kind === key ? "on" : ""}
            onClick={() => setF({ ...f, kind: key })}
          >
            <Icon name={v.icon} size={14} /> {v.label}
          </button>
        ))}
      </div>
      <label className="span-all">
        Name
        <input required aria-label="Name" value={f.title} onChange={set("title")} placeholder={f.kind === "train" ? "e.g. Shatabdi 12002" : f.kind === "stay" ? "e.g. Zostel Manali" : "e.g. Old town walk"} />
      </label>
      <label>
        {k.start}
        <input required aria-label={k.start} type="datetime-local" value={f.starts_at} onChange={set("starts_at")} />
      </label>
      <label>
        {k.end} <span className="muted">(optional)</span>
        <input aria-label={k.end} type="datetime-local" value={f.ends_at} onChange={set("ends_at")} min={f.starts_at || undefined} />
      </label>
      <label>
        {k.from}
        <input aria-label={k.from} value={f.from_place} onChange={set("from_place")} />
      </label>
      {k.to && (
        <label>
          {k.to}
          <input aria-label={k.to} value={f.to_place} onChange={set("to_place")} />
        </label>
      )}
      <label>
        {k.ref} <span className="muted">(optional)</span>
        <input aria-label={k.ref} value={f.reference} onChange={set("reference")} />
      </label>
      {error && <p className="form-error span-all" role="alert">{error}</p>}
      <div className="form-actions span-all">
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn primary small" disabled={saving}>
          Add to trip
        </button>
      </div>
    </form>
  );
}

// Chronological trains, flights, buses, stays and activities; each one drives alerts.
export default function Timeline({ items, onAdd, onRemove }) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="card span-2">
      <header className="card-head">
        <h2>
          <Icon name="bell" size={16} /> Bookings & alerts
        </h2>
        {!adding && (
          <button className="btn ghost small" onClick={() => setAdding(true)}>
            <Icon name="plus" size={14} /> Add
          </button>
        )}
      </header>
      {adding && <AddForm onAdd={async (i) => { await onAdd(i); setAdding(false); }} onCancel={() => setAdding(false)} />}
      {items.length ? (
        <ol className="timeline">
          {items.map((it) => {
            const k = KIND[it.kind];
            return (
              <li key={it.id} className={`tl-item ${it.kind}`}>
                <span className="tl-icon">
                  <Icon name={k.icon} size={16} />
                </span>
                <div className="tl-body">
                  <p className="tl-title">
                    {it.title}
                    {it.reference && <span className="badge">{it.reference}</span>}
                  </p>
                  <p className="muted small">
                    {k.start} {when(it.starts_at)}
                    {it.from_place ? ` · ${it.from_place}` : ""}
                    {it.ends_at ? ` → ${k.end.toLowerCase()} ${when(it.ends_at)}` : ""}
                    {it.to_place ? ` · ${it.to_place}` : ""}
                  </p>
                </div>
                <button className="icon-btn small-icon" onClick={() => onRemove(it.id)} aria-label={`Remove ${it.title}`}>
                  <Icon name="trash" size={15} />
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        !adding && (
          <div className="empty">
            <p>
              Add your trains, flights, buses, stays and activities — or upload the booking and ask me to add it. You'll get
              alerts for chart preparation, boarding, your stop, check-in and start times.
            </p>
          </div>
        )
      )}
    </section>
  );
}
