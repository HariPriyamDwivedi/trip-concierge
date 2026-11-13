import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import Icon from "./Icon.jsx";

const SUGGESTIONS = [
  "Plan 3 nights in Kyoto for 2 — what should we do and what will it cost?",
  "Build a day-by-day Lisbon itinerary for 4 nights",
  "What's the best way to get around Mexico City?",
  "What does my booking say about check-in?",
];

const SOURCE_ICON = { file: "file", guide: "book", web: "globe" };

// What the concierge is doing while a reply streams, by tool name.
const TOOL_ACTIVITY = {
  find_attractions: "Finding things to do…",
  estimate_trip_cost: "Pricing the trip…",
  save_itinerary: "Saving the plan to your board…",
  search_my_documents: "Searching your files…",
  search_guides: "Checking the travel guides…",
  web_search: "Searching the web…",
  free_slots: "Checking your calendar…",
  send_itinerary: "Preparing the itinerary email…",
  schedule_reminder: "Setting a reminder…",
};

function hostname(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <ul className="sources" aria-label="Sources">
      {sources.map((s) => {
        const label = s.kind === "web" ? hostname(s.url) : s.label;
        const body = (
          <>
            <Icon name={SOURCE_ICON[s.kind] || "file"} size={13} />
            <span>{label}</span>
          </>
        );
        return (
          <li key={`${s.kind}:${s.url || s.label}`}>
            {s.url ? (
              <a className={`chip ${s.kind}`} href={s.url} target="_blank" rel="noreferrer" title={s.label}>
                {body}
              </a>
            ) : (
              <span className={`chip ${s.kind}`} title={s.kind === "guide" ? "Curated guide" : "Your file"}>
                {body}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const linkNewTab = { a: (props) => <a {...props} target="_blank" rel="noreferrer" /> };

export default function Chat({ messages, sending, notice, onDismissNotice, onSend, onUpload, seasonal }) {
  const [draft, setDraft] = useState("");
  const logRef = useRef(null);
  const fileRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const submit = (e) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    onSend(text);
    inputRef.current?.focus();
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
  };

  const pickFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onUpload(file);
  };

  return (
    <section className="pane chat" aria-label="Chat">
      <div className="log" ref={logRef} aria-live="polite">
        {messages.length === 0 && !sending ? (
          <div className="welcome">
            <h1>Where to next?</h1>
            <p>
              Tell me the destination, dates and who's coming. I'll suggest things to do, price it, lay out the days,
              and answer from your bookings, curated guides or the web — with sources.
            </p>
            {seasonal?.in_season?.length > 0 && (
              <div className="seasonal">
                <p className="seasonal-title">
                  <Icon name="sun" size={15} /> In season this {seasonal.months[0]}
                </p>
                <div className="seasonal-chips">
                  {seasonal.in_season.slice(0, 8).map((d) => (
                    <button
                      key={d.name}
                      className="chip"
                      title={d.why}
                      onClick={() => onSend(`Is ${d.name} a good trip this ${seasonal.months[0]}? What should I do there and what will it cost?`)}
                    >
                      {d.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => onSend(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg user">
                {m.text}
              </div>
            ) : (
              <div key={i} className={`msg assistant ${m.streaming ? "is-streaming" : ""}`} aria-busy={!!m.streaming}>
                {m.text ? (
                  <div className="md">
                    <Markdown components={linkNewTab}>{m.text}</Markdown>
                  </div>
                ) : (
                  <div className="typing" aria-label="Concierge is thinking">
                    <span />
                    <span />
                    <span />
                  </div>
                )}
                {m.streaming && m.activity && <p className="activity">{TOOL_ACTIVITY[m.activity] || "Working…"}</p>}
                <Sources sources={m.sources} />
              </div>
            ),
          )
        )}
      </div>

      {notice && (
        <div className={`notice ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
          <span>{notice.text}</span>
          <button className="icon-btn" onClick={onDismissNotice} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <form className="composer" onSubmit={submit}>
        <input ref={fileRef} type="file" accept=".txt,.md,.pdf" hidden onChange={pickFile} />
        <button
          type="button"
          className="icon-btn"
          onClick={() => fileRef.current?.click()}
          aria-label="Attach a file (.txt, .md or .pdf, max 5 MB)"
          title="Attach a booking or notes (.txt, .md, .pdf)"
        >
          <Icon name="clip" />
        </button>
        <textarea
          ref={inputRef}
          rows={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a trip…"
          aria-label="Message"
          maxLength={4000}
        />
        <button className="btn primary send" type="submit" disabled={!draft.trim() || sending} aria-label="Send">
          <Icon name="send" />
        </button>
      </form>
    </section>
  );
}
