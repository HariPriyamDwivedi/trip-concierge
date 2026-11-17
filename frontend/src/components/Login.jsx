import { useEffect, useRef, useState } from "react";
import { requestCode, verifyCode } from "../api.js";
import Icon from "./Icon.jsx";

// Sign in with an email or user ID and a 6-digit code sent to the account's email.
export default function Login({ onSignedIn }) {
  const [step, setStep] = useState("identify");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef(null);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  useEffect(() => {
    if (step === "code") codeRef.current?.focus();
  }, [step]);

  const send = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestCode(identifier.trim());
      setStep("code");
      setCooldown(30);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { user } = await verifyCode(identifier.trim(), code);
      onSignedIn(user);
    } catch (err) {
      setError(err.message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <div className="login-card">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="plane" size={16} />
          </span>
          <span>Trip Concierge</span>
        </div>
        {step === "identify" ? (
          <form onSubmit={send}>
            <h1>Sign in</h1>
            <p className="muted">We'll email you a 6-digit code. New here? Use your email and we'll create your account.</p>
            <label>
              Email or user ID
              <input
                autoFocus
                required
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="you@example.com or your_user_id"
              />
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn primary wide" disabled={busy || identifier.trim().length < 3}>
              {busy ? "Sending…" : "Email me a code"}
            </button>
          </form>
        ) : (
          <form onSubmit={verify}>
            <h1>Check your email</h1>
            <p className="muted">
              If <strong>{identifier}</strong> has an account (or is a new email), a code is on its way. It expires in 10 minutes.
            </p>
            {!identifier.includes("@") && (
              <p className="hint-box">
                Signing in with a user ID only works for an existing account. New here?{" "}
                <button type="button" className="link" onClick={() => { setStep("identify"); setIdentifier(""); setCode(""); setError(null); }}>
                  Use your email address
                </button>{" "}
                to create one.
              </p>
            )}
            <label>
              6-digit code
              <input
                ref={codeRef}
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="\d{6}"
                maxLength={6}
                className="code-input"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="btn primary wide" disabled={busy || code.length !== 6}>
              {busy ? "Checking…" : "Sign in"}
            </button>
            <div className="login-links">
              <button type="button" className="link" onClick={() => { setStep("identify"); setCode(""); setError(null); }}>
                Use a different email
              </button>
              <button type="button" className="link" onClick={send} disabled={cooldown > 0}>
                {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
