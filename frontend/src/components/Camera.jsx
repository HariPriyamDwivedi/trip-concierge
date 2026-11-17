import { useEffect, useRef, useState } from "react";
import { uploadMedia } from "../api.js";
import Icon from "./Icon.jsx";

// Take a photo or record a video with the device camera and save it as a memory.
// Uses getUserMedia (desktop and mobile browsers, HTTPS or localhost only); where
// that isn't available it falls back to the phone's own camera app via
// <input capture>. The camera stops as soon as the dialog closes.
export default function Camera({ tripId, onClose, onSaved }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const [mode, setMode] = useState("photo");
  const [facing, setFacing] = useState("environment");
  const [error, setError] = useState(null);
  const [recording, setRecording] = useState(false);
  const [shot, setShot] = useState(null); // {blob, url, type, name}
  const [place, setPlace] = useState("");
  const [caption, setCaption] = useState("");
  const [coords, setCoords] = useState(null);
  const [progress, setProgress] = useState(null);
  const supported = !!navigator.mediaDevices?.getUserMedia;
  // Phones open their camera app from <input capture>; desktops show a file picker.
  const touch = window.matchMedia?.("(pointer: coarse)").matches;

  useEffect(() => {
    if (!supported || shot) return undefined;
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: facing }, audio: mode === "video" })
      .then((stream) => {
        if (cancelled) return stream.getTracks().forEach((t) => t.stop());
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setError(null);
      })
      .catch((err) =>
        setError(err.name === "NotAllowedError" ? "Camera access was blocked. Allow it in the browser to take photos." : `Camera unavailable: ${err.message}`),
      );
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [facing, mode, shot, supported]);

  useEffect(() => () => shot && URL.revokeObjectURL(shot.url), [shot]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const stamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");

  const takePhoto = () => {
    const v = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d").drawImage(v, 0, 0);
    canvas.toBlob((blob) => setShot({ blob, url: URL.createObjectURL(blob), type: "image/jpeg", name: `photo-${stamp()}.jpg` }), "image/jpeg", 0.92);
  };

  const toggleRecording = () => {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    const type = ["video/mp4", "video/webm;codecs=vp9,opus", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
    const rec = new MediaRecorder(streamRef.current, type ? { mimeType: type } : undefined);
    chunksRef.current = [];
    rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
    rec.onstop = () => {
      const mime = (rec.mimeType || "video/webm").split(";")[0];
      const blob = new Blob(chunksRef.current, { type: mime });
      setRecording(false);
      setShot({ blob, url: URL.createObjectURL(blob), type: mime, name: `video-${stamp()}.${mime.includes("mp4") ? "mp4" : "webm"}` });
    };
    rec.start(1000);
    recorderRef.current = rec;
    setRecording(true);
  };

  const locate = () =>
    navigator.geolocation?.getCurrentPosition(
      (pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setError("Couldn't get your location; type the place instead."),
      { enableHighAccuracy: true, timeout: 10000 },
    );

  const save = async (fileOverride) => {
    const file = fileOverride || new File([shot.blob], shot.name, { type: shot.type });
    setProgress(0);
    try {
      const m = await uploadMedia(
        file,
        { trip_id: tripId, place, caption, lat: coords?.lat, lng: coords?.lng, taken_at: new Date().toISOString() },
        setProgress,
      );
      onSaved(m);
    } catch (err) {
      setError(err.message);
      setProgress(null);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal camera" role="dialog" aria-modal="true" aria-label="Camera">
        <header className="modal-head">
          <div className="segmented" role="radiogroup" aria-label="Capture">
            {["photo", "video"].map((m) => (
              <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} disabled={recording || !!shot} onClick={() => setMode(m)}>
                {m === "photo" ? "Photo" : "Video"}
              </button>
            ))}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close camera">×</button>
        </header>

        <div className="viewfinder">
          {shot ? (
            shot.type.startsWith("video") ? <video src={shot.url} controls playsInline /> : <img src={shot.url} alt="Captured" />
          ) : supported && !error ? (
            <video ref={videoRef} autoPlay playsInline muted />
          ) : (
            <div className="camera-fallback">
              <p>{error || "This browser can't open the camera here."}</p>
              {!touch && (
                <p className="small">
                  To use your webcam, open Trip Concierge in Chrome, Edge or Safari and allow camera access when asked.
                </p>
              )}
              <label className="btn primary">
                <Icon name={touch ? "camera" : "image"} size={16} /> {touch ? "Open the phone camera" : "Choose a photo or video instead"}
                <input type="file" accept="image/*,video/*" capture="environment" hidden onChange={(e) => e.target.files[0] && save(e.target.files[0])} />
              </label>
            </div>
          )}
          {recording && <span className="rec-dot">REC</span>}
        </div>

        {shot ? (
          <div className="capture-meta">
            <label>
              Place
              <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="e.g. Fushimi Inari, Kyoto" />
            </label>
            <label>
              Caption
              <input value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="What made this moment?" />
            </label>
            <button type="button" className="btn ghost small" onClick={locate}>
              <Icon name="pin" size={14} /> {coords ? `Location added (${coords.lat.toFixed(3)}, ${coords.lng.toFixed(3)})` : "Add my current location"}
            </button>
            {error && <p className="form-error">{error}</p>}
            <div className="form-actions">
              <button className="btn ghost" onClick={() => setShot(null)} disabled={progress !== null}>Retake</button>
              <button className="btn primary" onClick={() => save()} disabled={progress !== null}>
                {progress !== null ? `Saving… ${Math.round(progress * 100)}%` : "Save to memories"}
              </button>
            </div>
          </div>
        ) : (
          supported && !error && (
            <div className="shutter-row">
              <button className="icon-btn" onClick={() => setFacing((f) => (f === "user" ? "environment" : "user"))} aria-label="Switch camera" disabled={recording}>
                <Icon name="route" />
              </button>
              {mode === "photo" ? (
                <button className="shutter" onClick={takePhoto} aria-label="Take photo" />
              ) : (
                <button className={`shutter video ${recording ? "on" : ""}`} onClick={toggleRecording} aria-label={recording ? "Stop recording" : "Start recording"} />
              )}
              <span style={{ width: 38 }} />
            </div>
          )
        )}
      </div>
    </div>
  );
}
