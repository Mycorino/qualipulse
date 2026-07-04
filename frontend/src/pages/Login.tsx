import { useState, FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";
import { login, loginWith2FA, getMe, getGoogleAuthorizeUrl } from "../api/auth";
import { useAuth, setCachedOnboarded } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";
import LanguageSwitcher from "../components/LanguageSwitcher";

export default function Login() {
  const { t } = useTranslation("auth");
  useHead({ title: t("login.metaTitle") });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // 2FA step: set after a successful password check on a 2FA-enabled account.
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const { saveToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resetSuccess = searchParams.get("reset") === "success";
  const googleErrorParam = searchParams.get("google_error");
  const [googleLoading, setGoogleLoading] = useState(false);
  const { i18n } = useTranslation();

  async function handleGoogleSignIn() {
    setError("");
    setGoogleLoading(true);
    try {
      const url = await getGoogleAuthorizeUrl("/dashboard", i18n.language);
      window.location.href = url;
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.googleError")));
      setGoogleLoading(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError(t("login.errors.emailRequired"));
      return;
    }
    if (!password) {
      setError(t("login.errors.passwordRequired"));
      return;
    }

    setLoading(true);
    try {
      const res = await login(trimmedEmail, password);
      if (res.requires_2fa && res.pending_token) {
        setPendingToken(res.pending_token);
        return;
      }
      await finishLogin(res.access_token!, res.refresh_token);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.errors.generic")));
    } finally {
      setLoading(false);
    }
  }

  async function finishLogin(accessToken: string, refreshToken?: string) {
    saveToken(accessToken, refreshToken);
    // Check if onboarding is completed — route accordingly
    try {
      const me = await getMe();
      setCachedOnboarded(!!me.onboarding_completed);
      if (!me.onboarding_completed) {
        navigate("/welcome", { replace: true });
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch {
      navigate("/dashboard", { replace: true });
    }
  }

  async function handleTwoFactorSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!totpCode.trim() || !pendingToken) return;
    setLoading(true);
    try {
      const res = await loginWith2FA(pendingToken, totpCode.trim());
      await finishLogin(res.access_token, res.refresh_token);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.twoFactor.invalidCode")));
    } finally {
      setLoading(false);
    }
  }

  if (pendingToken) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <Link to="/" className="auth-logo" style={{ textDecoration: "none", color: "inherit" }}>QualiPulse</Link>
          <h1 className="auth-title">{t("login.twoFactor.title")}</h1>
          <p className="auth-subtitle">{t("login.twoFactor.subtitle")}</p>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <form onSubmit={handleTwoFactorSubmit}>
            <label className="field-label" htmlFor="login-totp">{t("login.twoFactor.codeLabel")}</label>
            <input
              id="login-totp"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              className="field-input"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              placeholder="123456"
              required
              autoFocus
            />
            <p style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", margin: "4px 0 12px" }}>
              {t("login.twoFactor.backupHint")}
            </p>
            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? t("login.signingIn") : t("login.twoFactor.verify")}
            </button>
          </form>
          <p className="auth-footer" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="auth-link"
              style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
              onClick={() => { setPendingToken(null); setTotpCode(""); setError(""); }}
            >
              {t("login.twoFactor.backToLogin")}
            </button>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <LanguageSwitcher />
        </div>
        <Link to="/" className="auth-logo" style={{ textDecoration: "none", color: "inherit" }}>QualiPulse</Link>
        <h1 className="auth-title">{t("login.title")}</h1>
        <p className="auth-subtitle">{t("login.subtitle")}</p>

        {resetSuccess && (
          <div className="success-banner">{t("login.resetSuccess")}</div>
        )}
        {googleErrorParam && !error && (
          <div className="error-banner" role="alert">{t("login.googleError")}</div>
        )}
        {error && <div className="error-banner" role="alert">{error}</div>}

        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={googleLoading}
          className="btn btn-secondary btn-block google-btn"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            marginBottom: 12,
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.49h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A8.99 8.99 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.97 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3.01-2.33z"/>
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A8.96 8.96 0 0 0 9 0 8.99 8.99 0 0 0 .96 4.96l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
          </svg>
          {googleLoading ? t("login.googleStarting") : t("login.google")}
        </button>

        <div className="auth-divider" style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          margin: "16px 0",
          color: "var(--text-muted)",
          fontSize: "var(--text-xs)",
        }}>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span>{t("login.or")}</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>

        <form onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="login-email">{t("login.emailLabel")}</label>
          <input
            id="login-email"
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("login.emailPlaceholder")}
            required
            autoFocus
            autoComplete="email"
          />

          <label className="field-label" htmlFor="login-password">{t("login.passwordLabel")}</label>
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
              className="password-toggle"
              tabIndex={0}
              aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
            >
              {showPassword ? t("login.hidePassword") : t("login.showPassword")}
            </button>
          </div>

          <div style={{ textAlign: "right", marginTop: "4px" }}>
            <Link to="/forgot-password" className="auth-link">{t("login.forgotPassword")}</Link>
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? t("login.signingIn") : t("login.signIn")}
          </button>
        </form>
        <p className="auth-footer" style={{ marginTop: 12 }}>
          {t("login.noAccount")} <Link to="/signup">{t("login.signUpFree")}</Link>
        </p>
      </div>
    </div>
  );
}
