import { useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";

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
      await client.post("/auth/password-reset/request", { email });
      setSent(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Reset your password</h1>
        <p className="auth-subtitle">
          Enter your email and we'll send you a reset link.
        </p>
        {sent ? (
          <div className="auth-success">
            ✓ If that email is registered, you'll receive a reset link shortly. Check your inbox.
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
                placeholder="you@example.com"
              />
            </div>
            {error && <p className="error-text">{error}</p>}
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "Sending..." : "Send reset link"}
            </button>
          </form>
        )}
        <div className="auth-footer">
          <Link to="/login" className="auth-link">← Back to login</Link>
        </div>
      </div>
    </div>
  );
}
