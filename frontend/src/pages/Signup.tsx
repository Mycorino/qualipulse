import { useState, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";

export default function Signup() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showLoginHint, setShowLoginHint] = useState(false);
  const [loading, setLoading] = useState(false);
  const { saveToken } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    // Client-side validation
    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedName) {
      setError("Please enter your company or name.");
      return;
    }
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      const res = await signup(trimmedName, trimmedEmail, password);
      saveToken(res.access_token, res.refresh_token);
      navigate("/welcome");
    } catch (err: unknown) {
      const msg = getErrorMessage(err, "Signup failed. Please try again.");
      // Check if account already exists — add helpful context
      if (msg.toLowerCase().includes("already exists")) {
        setError(msg);
        setShowLoginHint(true);
      } else {
        setError(msg);
        setShowLoginHint(false);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">Create your account</h1>
        <p className="auth-subtitle">Start running AI-powered research interviews in minutes.</p>

        {error && (
          <div className="error-banner">
            {error}
            {showLoginHint && (
              <> <Link to="/login" style={{ color: "var(--primary)", fontWeight: 600 }}>Sign in instead →</Link></>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label className="field-label">Company or your name</label>
          <input
            type="text"
            className="field-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Research"
            required
            autoFocus
          />

          <label className="field-label">Work email</label>
          <input
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
          />

          <label className="field-label">Password</label>
          <input
            type="password"
            className="field-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            required
            minLength={8}
          />

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? "Creating account..." : "Get started free"}
          </button>
        </form>

        <p className="auth-terms">
          By signing up, you agree to our <Link to="/terms">Terms of Service</Link> and <Link to="/privacy">Privacy Policy</Link>.
        </p>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
