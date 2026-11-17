import { useCallback, useEffect, useState } from "react";
import { createTrip, getMe, listTrips, logout } from "./api.js";
import Icon from "./components/Icon.jsx";
import Login from "./components/Login.jsx";
import MapView from "./components/MapView.jsx";
import Memories from "./components/Memories.jsx";
import PlanView from "./components/PlanView.jsx";
import Profile from "./components/Profile.jsx";
import Trips from "./components/Trips.jsx";

const PAGES = [
  ["plan", "Plan", "chat"],
  ["trips", "Trips", "route"],
  ["memories", "Memories", "image"],
  ["map", "Map", "globe"],
];

// The current trip is remembered per user on this device (storage may be unavailable).
const tripKey = (user) => `trip-concierge:trip:${user.id}`;
function loadTripId(user) {
  try {
    return localStorage.getItem(tripKey(user));
  } catch {
    return null;
  }
}
function saveTripId(user, id) {
  try {
    localStorage.setItem(tripKey(user), id);
  } catch {}
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = checking, null = signed out
  const [trips, setTrips] = useState([]);
  const [tripId, setTripId] = useState(null);
  const [page, setPage] = useState("plan");
  const [memFilter, setMemFilter] = useState({});
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    getMe()
      .then((r) => setUser(r.user))
      .catch(() => setUser(null));
  }, []);

  const refreshTrips = useCallback(() => listTrips().then(setTrips).catch(() => {}), []);

  // After sign-in: load trips and open the last one (or start the first).
  useEffect(() => {
    if (!user) return;
    listTrips().then(async (list) => {
      setTrips(list);
      const saved = loadTripId(user);
      if (saved && list.some((t) => t.id === saved)) setTripId(saved);
      else if (list.length) setTripId(list[0].id);
      else {
        const t = await createTrip();
        setTrips([t]);
        setTripId(t.id);
      }
    });
  }, [user]);

  useEffect(() => {
    if (user && tripId) saveTripId(user, tripId);
  }, [user, tripId]);

  // Back from Google/Microsoft sign-in: show the outcome once, then clean the URL.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (!q.has("oauth")) return;
    const name = q.get("provider") === "microsoft" ? "Microsoft" : "Google";
    setNotice(
      q.get("oauth") === "connected"
        ? { kind: "info", text: `${name} connected as ${q.get("account")} — Calendar and Mail are on for this trip.` }
        : { kind: "error", text: `Sign-in didn't finish: ${q.get("message")}` },
    );
    if (q.get("trip_id")) setTripId(q.get("trip_id"));
    window.history.replaceState(null, "", "/");
  }, []);

  const newTrip = async () => {
    try {
      const t = await createTrip();
      setTrips((list) => [t, ...list]);
      setTripId(t.id);
      setPage("plan");
    } catch (err) {
      setNotice({ kind: "error", text: err.message });
    }
  };

  const signOut = async () => {
    await logout().catch(() => {});
    setUser(null);
    setTrips([]);
    setTripId(null);
    setPage("plan");
  };

  if (user === undefined) return <div className="splash" aria-busy="true" />;
  if (user === null) return <Login onSignedIn={setUser} />;

  const initials = (user.name || user.email).split(/[\s._@]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="plane" size={16} />
          </span>
          <span className="brand-name">Trip Concierge</span>
        </div>
        <nav className="main-nav" aria-label="Main">
          {PAGES.map(([id, label, icon]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              aria-current={page === id ? "page" : undefined}
              onClick={() => {
                if (id === "memories") setMemFilter({});
                setPage(id);
              }}
            >
              <Icon name={icon} size={16} /> <span className="nav-label">{label}</span>
            </button>
          ))}
        </nav>
        <button
          className={`avatar ${page === "profile" ? "active" : ""}`}
          onClick={() => setPage("profile")}
          aria-label={`Profile: ${user.name || user.email}`}
          title={user.name || user.email}
        >
          {initials}
        </button>
      </header>

      <main className="main">
        {page === "plan" && tripId && (
          <PlanView key={tripId} tripId={tripId} notice={notice} setNotice={setNotice} onTripChanged={refreshTrips} onNewTrip={newTrip} />
        )}
        {page === "trips" && (
          <Trips
            trips={trips}
            currentId={tripId}
            onNew={newTrip}
            onOpen={(id) => {
              setTripId(id);
              setPage("plan");
            }}
            onOpenMemories={(id) => {
              setMemFilter({ trip: id });
              setPage("memories");
            }}
          />
        )}
        {page === "memories" && (
          <Memories trips={trips} initialPlace={memFilter.place} initialTrip={memFilter.trip} onChanged={refreshTrips} setNotice={setNotice} />
        )}
        {page === "map" && (
          <MapView
            setNotice={setNotice}
            onOpenPlace={(place) => {
              setMemFilter({ place });
              setPage("memories");
            }}
          />
        )}
        {page === "profile" && <Profile user={user} onUpdated={setUser} onSignOut={signOut} setNotice={setNotice} />}
      </main>

      {notice && page !== "plan" && (
        <div className={`toast ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
          <span>{notice.text}</span>
          <button className="icon-btn" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}
    </div>
  );
}
