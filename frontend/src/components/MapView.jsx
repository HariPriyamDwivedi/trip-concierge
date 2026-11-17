import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { listPlaces } from "../api.js";
import Icon from "./Icon.jsx";

function FitToPins({ pins }) {
  const map = useMap();
  useEffect(() => {
    if (pins.length === 1) map.setView([pins[0].lat, pins[0].lng], 10);
    else if (pins.length > 1) map.fitBounds(pins.map((p) => [p.lat, p.lng]), { padding: [48, 48], maxZoom: 10 });
  }, [pins, map]);
  return null;
}

// A zoomable world map of every place the user has memories from.
export default function MapView({ onOpenPlace, setNotice }) {
  const [pins, setPins] = useState(null);

  useEffect(() => {
    listPlaces()
      .then(setPins)
      .catch((err) => setNotice({ kind: "error", text: err.message }));
  }, [setNotice]);

  const total = (pins || []).reduce((n, p) => n + p.count, 0);

  return (
    <section className="page map-page">
      <header className="page-head">
        <div>
          <h1>Your travel map</h1>
          <p className="muted">
            {pins ? `${pins.length} place${pins.length === 1 ? "" : "s"} · ${total} memories` : "Loading…"} — zoom in and out, click a place to see what you kept.
          </p>
        </div>
      </header>
      <div className="map-wrap">
        <MapContainer center={[20, 10]} zoom={2} minZoom={2} worldCopyJump scrollWheelZoom className="map">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {(pins || []).map((p) => (
            <CircleMarker
              key={p.place}
              center={[p.lat, p.lng]}
              radius={Math.min(26, 8 + Math.sqrt(p.count) * 4)}
              pathOptions={{ color: "#0f766e", weight: 2, fillColor: "#14b8a6", fillOpacity: 0.55 }}
            >
              <Popup>
                <div className="pin-popup">
                  {p.cover_url && <img src={p.cover_url} alt={p.place} />}
                  <p className="pin-title">{p.place}</p>
                  <p className="pin-meta">
                    {p.photos} photo{p.photos === 1 ? "" : "s"} · {p.videos} video{p.videos === 1 ? "" : "s"}
                    {p.count - p.photos - p.videos > 0 ? ` · ${p.count - p.photos - p.videos} other` : ""}
                  </p>
                  <button className="btn primary small" onClick={() => onOpenPlace(p.place)}>
                    <Icon name="image" size={14} /> View memories
                  </button>
                </div>
              </Popup>
            </CircleMarker>
          ))}
          <FitToPins pins={pins || []} />
        </MapContainer>
        {pins && pins.length === 0 && (
          <div className="map-empty">
            <p>No places yet. Add a place (or turn on location) when you save photos and videos, and they'll appear here.</p>
          </div>
        )}
      </div>
    </section>
  );
}
