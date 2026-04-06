import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import client from "../api/client";
import { getErrorMessage } from "../utils/errorMessages";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    setLoading(true);
    setError("");
    try {
      await client.post("/auth/password-reset/confirm", { token, new_password: password });
      navigate("/login?reset=success");
    } catch (err: unknown) {
      const msg = getErrorMessage(err, "");
      // If it's a token issue, show a specific message
      if (msg.toLowerCase().includes("token") || msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("invalid")) {
        setError("This reset link is invalid or has expired. Please request a new one.");
      } else {
        setError(msg || "Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-logo">QualiPulse</div>
          <h1 className="auth-title">Invalid link</h1>
          <p className="auth-subtitle">This reset link is missing or malformed.</p>
          <Link to="/forgot-password" className="btn btn-primary btn-block" style={{ textAlign: "center", textDecoration: "none" }}>Request a new one</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">Set new password</h1>
        <p className="auth-subtitle">Choose a strong password for your account.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <div>
            <label className="field-label">New password</label>
            <input
              type="password"
              className="field-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="At least 8 characters"
            />
          </div>
          <div>
            <label className="field-label">Confirm password</label>
            <input
              type="password"
              className="field-input"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              placeholder="Repeat your password"
            />
          </div>
          {error && <div className="error-banner">{error}</div>}
          <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
            {loading ? "Updating..." : "Set new password"}
          </button>
        </form>
      </div>
    </div>
  );
}
