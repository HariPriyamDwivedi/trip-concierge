import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { deleteMedia, listMedia, updateMedia, uploadMedia } from "../api.js";
import Camera from "./Camera.jsx";
import Icon from "./Icon.jsx";

const KINDS = [
  ["", "All"],
  ["photo", "Photos"],
  ["video", "Videos"],
  ["file", "Files"],
];
const GROUPS = [
  ["month", "By date"],
  ["place", "By place"],
  ["trip", "By trip"],
];

const when = (m) => new Date(m.taken_at || m.created_at);
const size = (n) => (n > 2 ** 20 ? `${(n / 2 ** 20).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function groupBy(items, by, trips) {
  const title = Object.fromEntries(trips.map((t) => [t.id, t.title]));
  const groups = new Map();
  for (const m of items) {
    const key =
      by === "place" ? m.place || "Somewhere" : by === "trip" ? title[m.trip_id] || "Not in a trip" : when(m).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  return [...groups.entries()];
}

export function Tile({ m, onOpen }) {
  return (
    <button className={`tile ${m.kind}`} onClick={() => onOpen(m)} title={m.caption || m.filename}>
      {m.thumb_url ? (
        <img src={m.thumb_url} alt={m.caption || m.filename} loading="lazy" />
      ) : m.kind === "video" ? (
        <video src={`${m.url}#t=0.5`} preload="metadata" muted playsInline />
      ) : (
        <span className="tile-file">
          <Icon name="file" size={26} />
          <span>{m.filename}</span>
        </span>
      )}
      {m.kind === "video" && <span className="tile-badge">▶</span>}
    </button>
  );
}

export function Viewer({ items, index, trips, onClose, onMove, onChanged, onDeleted }) {
  const m = items[index];
  const [caption, setCaption] = useState(m.caption || "");
  const [place, setPlace] = useState(m.place || "");
  const [tripId, setTripId] = useState(m.trip_id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setCaption(m.caption || "");
    setPlace(m.place || "");
    setTripId(m.trip_id || "");
    setError(null);
  }, [m]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onMove(1);
      if (e.key === "ArrowLeft") onMove(-1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, onMove]);

  const save = async () => {
    setBusy(true);
    try {
      onChanged(await updateMedia(m.id, { caption, place, trip_id: tripId }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(`Delete ${m.filename}? This can't be undone.`)) return;
    try {
      await deleteMedia(m.id);
      onDeleted(m.id);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="modal-backdrop viewer-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="viewer" role="dialog" aria-modal="true" aria-label={m.filename}>
        <div className="viewer-media">
          {m.kind === "photo" ? (
            <img src={m.url} alt={m.caption || m.filename} />
          ) : m.kind === "video" ? (
            <video src={m.url} controls autoPlay playsInline />
          ) : m.kind === "audio" ? (
            <audio src={m.url} controls />
          ) : (
            <a className="btn primary" href={m.url} target="_blank" rel="noreferrer">
              <Icon name="file" size={16} /> Open {m.filename}
            </a>
          )}
          <button className="viewer-nav prev" onClick={() => onMove(-1)} aria-label="Previous" disabled={index === 0}>‹</button>
          <button className="viewer-nav next" onClick={() => onMove(1)} aria-label="Next" disabled={index === items.length - 1}>›</button>
        </div>
        <aside className="viewer-info">
          <div className="modal-head">
            <p className="viewer-title">{m.filename}</p>
            <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
          </div>
          <p className="muted small">
            {when(m).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · {size(m.size)}
            {m.lat != null && ` · ${m.lat.toFixed(3)}, ${m.lng.toFixed(3)}`}
          </p>
          <label>
            Caption
            <textarea rows={3} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Add a memory note" />
          </label>
          <label>
            Place
            <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="e.g. Anjuna, Goa" />
          </label>
          <label>
            Trip
            <select value={tripId} onChange={(e) => setTripId(e.target.value)}>
              <option value="">Not in a trip</option>
              {trips.map((t) => (
                <option key={t.id} value={t.id}>{t.title}</option>
              ))}
            </select>
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button className="btn ghost small danger" onClick={remove}>
              <Icon name="trash" size={14} /> Delete
            </button>
            <a className="btn ghost small" href={m.url} download={m.filename}>Download</a>
            <button className="btn primary small" onClick={save} disabled={busy}>Save</button>
          </div>
        </aside>
      </div>
    </div>
  );
}

// Google Photos–style library of everything the user kept from their travels.
export default function Memories({ trips, initialPlace, initialTrip, onChanged, setNotice }) {
  const [items, setItems] = useState(null);
  const [kind, setKind] = useState("");
  const [by, setBy] = useState("month");
  const [place, setPlace] = useState(initialPlace || "");
  const [tripFilter, setTripFilter] = useState(initialTrip || "");
  const [open, setOpen] = useState(null);
  const [camera, setCamera] = useState(false);
  const [uploads, setUploads] = useState([]); // [{name, progress, error}]
  const [dragging, setDragging] = useState(false);
  const [uploadTrip, setUploadTrip] = useState("");
  const [uploadPlace, setUploadPlace] = useState("");
  const fileRef = useRef(null);

  const load = useCallback(() => {
    listMedia({ kind, place, trip_id: tripFilter })
      .then(setItems)
      .catch((err) => setNotice({ kind: "error", text: err.message }));
  }, [kind, place, tripFilter, setNotice]);
  useEffect(load, [load]);
  useEffect(() => setPlace(initialPlace || ""), [initialPlace]);
  useEffect(() => {
    setTripFilter(initialTrip || "");
    if (initialTrip) setUploadTrip(initialTrip);
  }, [initialTrip]);

  const groups = useMemo(() => groupBy(items || [], by, trips), [items, by, trips]);
  const flat = useMemo(() => groups.flatMap(([, g]) => g), [groups]);

  const addFiles = async (files) => {
    const list = [...files];
    setUploads(list.map((f) => ({ name: f.name, progress: 0 })));
    for (const [i, f] of list.entries()) {
      const set = (patch) => setUploads((u) => u.map((x, j) => (j === i ? { ...x, ...patch } : x)));
      try {
        await uploadMedia(f, { trip_id: uploadTrip, place: uploadPlace }, (p) => set({ progress: p }));
        set({ progress: 1 });
      } catch (err) {
        set({ error: err.message });
      }
    }
    load();
    onChanged?.();
    setTimeout(() => setUploads((u) => u.filter((x) => x.error)), 2500);
  };

  return (
    <section
      className={`page memories ${dragging ? "dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => e.currentTarget === e.target && setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
      }}
    >
      <header className="page-head">
        <div>
          <h1>Memories</h1>
          <p className="muted">Photos, videos and files from your travels — {items ? `${items.length} kept` : "loading…"}</p>
        </div>
        <div className="page-actions">
          <button className="btn ghost" onClick={() => setCamera(true)}>
            <Icon name="camera" size={16} /> Camera
          </button>
          <button className="btn primary" onClick={() => fileRef.current?.click()}>
            <Icon name="plus" size={16} /> Upload
          </button>
          <input ref={fileRef} type="file" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
        </div>
      </header>

      <div className="toolbar">
        <div className="segmented" role="radiogroup" aria-label="Type">
          {KINDS.map(([k, label]) => (
            <button key={label} role="radio" aria-checked={kind === k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{label}</button>
          ))}
        </div>
        <div className="segmented" role="radiogroup" aria-label="Group">
          {GROUPS.map(([g, label]) => (
            <button key={g} role="radio" aria-checked={by === g} className={by === g ? "on" : ""} onClick={() => setBy(g)}>{label}</button>
          ))}
        </div>
        {tripFilter && (
          <button className="chip filter" onClick={() => setTripFilter("")}>
            <Icon name="route" size={13} /> {trips.find((t) => t.id === tripFilter)?.title || "Trip"} ×
          </button>
        )}
        {place && (
          <button className="chip filter" onClick={() => setPlace("")}>
            <Icon name="pin" size={13} /> {place} ×
          </button>
        )}
        <span className="toolbar-spacer" />
        <label className="inline-field">
          New uploads go to
          <select value={uploadTrip} onChange={(e) => setUploadTrip(e.target.value)} aria-label="Trip for new uploads">
            <option value="">No trip</option>
            {trips.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
        </label>
        <input className="inline-input" value={uploadPlace} onChange={(e) => setUploadPlace(e.target.value)} placeholder="Place (optional)" aria-label="Place for new uploads" />
      </div>

      {uploads.length > 0 && (
        <ul className="upload-list" aria-live="polite">
          {uploads.map((u, i) => (
            <li key={i} className={u.error ? "failed" : ""}>
              <span>{u.name}</span>
              {u.error ? <span className="form-error">{u.error}</span> : <progress max={1} value={u.progress} />}
            </li>
          ))}
        </ul>
      )}

      {items && items.length === 0 ? (
        <div className="empty big-empty">
          <Icon name="image" size={34} />
          <p>No memories yet. Drop photos and videos here, upload files, or open the camera.</p>
        </div>
      ) : (
        groups.map(([label, group]) => (
          <section key={label} className="mem-group">
            <h2>
              {label} <span className="muted small">{group.length}</span>
            </h2>
            <div className="mem-grid">
              {group.map((m) => <Tile key={m.id} m={m} onOpen={() => setOpen(flat.indexOf(m))} />)}
            </div>
          </section>
        ))
      )}

      {dragging && <div className="drop-hint">Drop to add to your memories</div>}

      {open !== null && flat[open] && (
        <Viewer
          items={flat}
          index={open}
          trips={trips}
          onClose={() => setOpen(null)}
          onMove={(d) => setOpen((i) => Math.min(flat.length - 1, Math.max(0, i + d)))}
          onChanged={(m) => {
            setItems((list) => list.map((x) => (x.id === m.id ? m : x)));
            setNotice({ kind: "info", text: "Saved." });
            onChanged?.();
          }}
          onDeleted={(id) => {
            setOpen(null);
            setItems((list) => list.filter((x) => x.id !== id));
            onChanged?.();
          }}
        />
      )}
      {camera && (
        <Camera
          tripId={uploadTrip}
          onClose={() => setCamera(false)}
          onSaved={() => {
            setCamera(false);
            load();
            onChanged?.();
          }}
        />
      )}
    </section>
  );
}
