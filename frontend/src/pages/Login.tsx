import { useState, FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { login, getMe } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";
import LanguageSwitcher from "../components/LanguageSwitcher";

export default function Login() {
  const { t } = useTranslation("auth");
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
        navigate("/dashboard");
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.signIn")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <LanguageSwitcher />
        </div>
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">{t("login.title")}</h1>
        <p className="auth-subtitle">{t("login.subtitle")}</p>

        {resetSuccess && (
          <div className="success-banner">{t("login.resetSuccess")}</div>
        )}
        {error && <div className="error-banner">{error}</div>}

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
