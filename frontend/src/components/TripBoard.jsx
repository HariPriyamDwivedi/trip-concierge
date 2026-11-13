import { useRef } from "react";
import Icon from "./Icon.jsx";

const usd = (n) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

function formatDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const hasTime = /T\d{2}:\d{2}/.test(value);
  return d.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(hasTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

// Compact "Kyoto · 3 nights · 2 travellers · $840" line for the top bar.
export function TripSummary({ trip }) {
  const b = trip.budget;
  if (!trip.city) return <div className="summary muted">No trip yet</div>;
  return (
    <div className="summary" aria-label="Trip summary">
      <span className="summary-city">
        <Icon name="pin" size={14} /> {trip.city}
      </span>
      {b && (
        <>
          <span>{b.nights} nights</span>
          <span>{b.travelers} travellers</span>
          <span className="summary-total">{usd(b.estimated_total_usd)}</span>
        </>
      )}
    </div>
  );
}

function Card({ icon, title, className = "", action, children }) {
  return (
    <section className={`card ${className}`}>
      <header className="card-head">
        <h2>
          <Icon name={icon} size={16} /> {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function Empty({ children, ask, onAsk, busy }) {
  return (
    <div className="empty">
      <p>{children}</p>
      {ask && (
        <button className="btn ghost small" onClick={() => onAsk(ask)} disabled={busy}>
          {ask}
        </button>
      )}
    </div>
  );
}

export default function TripBoard({ trip, documents, onUpload, onAsk, busy }) {
  const fileRef = useRef(null);
  const city = trip.city;
  const budget = trip.budget;
  const days = trip.itinerary?.days || [];
  const things = trip.attractions?.items || [];
  const reminders = trip.reminders || [];
  const emails = trip.emails || [];

  return (
    <section className="pane board" aria-label="Trip board">
      <div className={`hero ${city ? "" : "is-empty"}`}>
        <p className="eyebrow">Your trip</p>
        <h1>{city || "Your trip takes shape here"}</h1>
        <p className="hero-sub">
          {budget
            ? `${budget.nights} nights · ${budget.travelers} travellers`
            : city
              ? "Ask for a budget or a day-by-day plan"
              : "Chat with the concierge — destinations, budget, days and bookings appear on this board."}
        </p>
      </div>

      <div className="grid">
        <Card icon="wallet" title="Budget" className="budget">
          {budget ? (
            <>
              <p className="big">{usd(budget.estimated_total_usd)}</p>
              <p className="muted">
                {usd(budget.daily_cost_usd)} per person per day × {budget.nights} nights × {budget.travelers} travellers
              </p>
              <p className="fineprint">Rough mid-range estimate for lodging, food and local transport.</p>
            </>
          ) : (
            <Empty ask={city ? `What will ${city} cost for 3 nights for 2?` : null} onAsk={onAsk} busy={busy}>
              No estimate yet.
            </Empty>
          )}
        </Card>

        <Card icon="star" title={city ? `Things to do in ${trip.attractions?.city || city}` : "Things to do"}>
          {things.length ? (
            <ul className="things">
              {things.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          ) : (
            <Empty ask={city ? `What should I do in ${city}?` : null} onAsk={onAsk} busy={busy}>
              Suggestions appear here.
            </Empty>
          )}
        </Card>

        <Card icon="route" title="Itinerary" className="span-2">
          {days.length ? (
            <ol className="days">
              {days.map((d, i) => (
                <li key={i} className="day">
                  <div className="day-label">
                    <span className="day-num">Day {i + 1}</span>
                    <span className="day-title">{d.title}</span>
                  </div>
                  <ol className="stops">
                    {d.stops.map((s, j) => (
                      <li key={j}>{s}</li>
                    ))}
                  </ol>
                </li>
              ))}
            </ol>
          ) : (
            <Empty ask={city ? `Build a day-by-day plan for ${city}` : null} onAsk={onAsk} busy={busy}>
              The day-by-day plan appears here once the concierge drafts one.
            </Empty>
          )}
        </Card>

        <Card
          icon="file"
          title="Documents"
          action={
            <>
              <input ref={fileRef} type="file" accept=".txt,.md,.pdf" hidden onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) onUpload(f);
              }} />
              <button className="btn ghost small" onClick={() => fileRef.current?.click()}>
                <Icon name="clip" size={14} /> Add
              </button>
            </>
          }
        >
          {documents.length ? (
            <ul className="docs">
              {documents.map((d) => (
                <li key={d}>
                  <Icon name="file" size={15} /> {d}
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Add bookings, tickets or notes (.txt, .md, .pdf) and ask about them.</Empty>
          )}
        </Card>

        <Card icon="bell" title="Reminders & drafts">
          {reminders.length || emails.length ? (
            <ul className="events">
              {reminders.map((r, i) => (
                <li key={`r${i}`}>
                  <Icon name="bell" size={15} />
                  <div>
                    <p>{r.message}</p>
                    <p className="muted small">{formatDate(r.remind_at)}</p>
                  </div>
                </li>
              ))}
              {emails.map((e, i) => (
                <li key={`e${i}`}>
                  <Icon name="mail" size={15} />
                  <div>
                    <p>{e.subject}</p>
                    <p className="muted small">
                      to {e.to}{" "}
                      <span className={`badge ${e.status === "sent" ? "ok" : ""}`}>
                        {e.status === "sent" ? "Sent" : "Draft · not sent"}
                      </span>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Reminders and itinerary email drafts show up here.</Empty>
          )}
        </Card>
      </div>
    </section>
  );
}
