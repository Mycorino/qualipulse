import { useState, FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { login, getMe } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { saveToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resetSuccess = searchParams.get("reset") === "success";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError("Please enter your email address.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    setLoading(true);
    try {
      const res = await login(trimmedEmail, password);
      saveToken(res.access_token, res.refresh_token);

      // Check if onboarding is completed — route accordingly
      try {
        const me = await getMe();
        if (!me.onboarding_completed) {
          navigate("/welcome");
        } else {
          navigate("/dashboard");
        }
      } catch {
        // If getMe fails, just go to dashboard
        navigate("/dashboard");
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Login failed. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">Welcome back</h1>
        <p className="auth-subtitle">Sign in to your account</p>

        {resetSuccess && (
          <div className="success-banner">Password updated successfully. Sign in with your new password.</div>
        )}
        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
            autoFocus
            autoComplete="email"
          />

          <label className="field-label" htmlFor="login-password">Password</label>
          <div style={{ position: "relative" }}>
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              className="field-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              style={{ paddingRight: "52px" }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              style={{
                position: "absolute",
                right: "12px",
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-muted)",
                fontSize: "13px",
                padding: "4px",
              }}
              tabIndex={-1}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>

          <div style={{ textAlign: "right", marginTop: "4px" }}>
            <Link to="/forgot-password" className="auth-link">Forgot your password?</Link>
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="auth-footer" style={{ marginTop: 12 }}>
          Don't have an account? <Link to="/signup">Sign up free</Link>
        </p>
      </div>
    </div>
  );
}
