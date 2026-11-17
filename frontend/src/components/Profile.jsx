import { useEffect, useMemo, useState } from "react";
import { getMe, updateMe } from "../api.js";
import Icon from "./Icon.jsx";

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["UTC"];

// Profile: name, user ID, home city and home time zone, plus a few stats.
export default function Profile({ user, onUpdated, onSignOut, setNotice }) {
  const [form, setForm] = useState({ name: user.name || "", username: user.username || "", home_city: user.home_city || "", timezone: user.timezone || "UTC" });
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(false);
  const browserZone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);

  useEffect(() => {
    getMe().then((r) => setStats(r.stats)).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { user: updated } = await updateMe(form);
      onUpdated(updated);
      setNotice({ kind: "info", text: "Profile saved." });
    } catch (err) {
      setNotice({ kind: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="page profile">
      <header className="page-head">
        <div>
          <h1>Profile</h1>
          <p className="muted">Signed in as {user.email} · member since {new Date(user.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</p>
        </div>
        <button className="btn ghost" onClick={onSignOut}>
          <Icon name="logout" size={16} /> Sign out
        </button>
      </header>

      {stats && (
        <div className="stats">
          <div className="stat"><span className="stat-num">{stats.trips}</span><span className="muted small">trips</span></div>
          <div className="stat"><span className="stat-num">{stats.memories}</span><span className="muted small">memories</span></div>
          <div className="stat"><span className="stat-num">{stats.places}</span><span className="muted small">places on your map</span></div>
        </div>
      )}

      <form className="card profile-form" onSubmit={save}>
        <label>
          Name
          <input value={form.name} onChange={set("name")} maxLength={80} />
        </label>
        <label>
          User ID <span className="muted small">— you can sign in with this instead of your email</span>
          <input value={form.username} onChange={set("username")} maxLength={30} pattern="[a-zA-Z0-9][a-zA-Z0-9_.]{1,28}[a-zA-Z0-9]" />
        </label>
        <label>
          Email
          <input value={user.email} disabled />
        </label>
        <label>
          Home city
          <input value={form.home_city} onChange={set("home_city")} maxLength={80} placeholder="e.g. Pune" />
        </label>
        <label>
          Home time zone <span className="muted small">— used for reminders and times you enter without a zone</span>
          <select value={form.timezone} onChange={set("timezone")}>
            {/* the saved zone first: browsers may list it under another name (Asia/Calcutta vs Asia/Kolkata) */}
            {[...new Set([form.timezone, "UTC", browserZone, ...ZONES])].map((z) => (
              <option key={z} value={z}>{z}{z === browserZone ? " (this device)" : ""}</option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
        </div>
      </form>
    </section>
  );
}
