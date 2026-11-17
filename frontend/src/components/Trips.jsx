import Icon from "./Icon.jsx";

const STATUS = { upcoming: "Upcoming", ongoing: "On the road", past: "Past trip", planning: "Planning" };

const day = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

// All of the user's trips: upcoming and ongoing first, then planning, then past.
export default function Trips({ trips, currentId, onOpen, onNew, onOpenMemories }) {
  const order = { ongoing: 0, upcoming: 1, planning: 2, past: 3 };
  const sorted = [...trips].sort((a, b) => order[a.status] - order[b.status] || (b.updated_at > a.updated_at ? 1 : -1));
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1>Your trips</h1>
          <p className="muted">{trips.length} trip{trips.length === 1 ? "" : "s"} — pick one to keep planning or relive it.</p>
        </div>
        <button className="btn primary" onClick={onNew}>
          <Icon name="plus" size={16} /> New trip
        </button>
      </header>
      {sorted.length === 0 ? (
        <div className="empty big-empty">
          <Icon name="route" size={34} />
          <p>No trips yet. Start one and tell the concierge where you're headed.</p>
        </div>
      ) : (
        <ul className="trip-grid">
          {sorted.map((t) => (
            <li key={t.id} className={`trip-card ${t.status} ${t.id === currentId ? "current" : ""}`}>
              <button className="trip-open" onClick={() => onOpen(t.id)}>
                <span className={`badge status-${t.status}`}>{STATUS[t.status]}</span>
                <span className="trip-title">{t.title}</span>
                <span className="muted small">
                  {t.starts_at ? `${day(t.starts_at)}${t.ends_at && day(t.ends_at) !== day(t.starts_at) ? ` – ${day(t.ends_at)}` : ""}` : `Started ${day(t.created_at)}`}
                </span>
              </button>
              <div className="trip-foot">
                <button className="link" onClick={() => onOpenMemories(t.id)}>
                  <Icon name="image" size={13} /> {t.media_count} memor{t.media_count === 1 ? "y" : "ies"}
                </button>
                {t.id === currentId && <span className="muted small">Open now</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
