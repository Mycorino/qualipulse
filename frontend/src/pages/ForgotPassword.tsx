import { useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { getErrorMessage } from "../utils/errorMessages";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await client.post("/auth/password-reset/request", { email: email.trim().toLowerCase() });
      setSent(true);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Something went wrong. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">Reset your password</h1>
        <p className="auth-subtitle">
          Enter your email and we'll send you a reset link.
        </p>
        {sent ? (
          <div className="success-banner">
            Check your inbox — if that email is registered, you'll receive a reset link shortly.
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <div>
              <label className="field-label">Email</label>
              <input
                type="email"
                className="field-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@company.com"
              />
            </div>
            {error && <div className="error-banner">{error}</div>}
            <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
              {loading ? "Sending..." : "Send reset link"}
            </button>
          </form>
        )}
        <div className="auth-footer">
          <Link to="/login" className="auth-link">Back to login</Link>
        </div>
      </div>
    </div>
  );
}
