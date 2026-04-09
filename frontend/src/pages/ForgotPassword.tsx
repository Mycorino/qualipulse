import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../api/client";
import { getErrorMessage } from "../utils/errorMessages";

export default function ForgotPassword() {
  const { t } = useTranslation();
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
      setError(getErrorMessage(err, t("auth:forgotPassword.defaultError")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">{t("auth:forgotPassword.title")}</h1>
        <p className="auth-subtitle">
          {t("auth:forgotPassword.subtitle")}
        </p>
        {sent ? (
          <div className="success-banner">
            {t("auth:forgotPassword.successMessage")}
          </div>
        ) : null}
        {sent ? (
          <button
            className="btn btn-ghost"
            style={{ marginTop: 12 }}
            onClick={() => { setSent(false); setEmail(""); }}
          >
            {t("auth:forgotPassword.tryDifferentEmail")}
          </button>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <div>
              <label className="field-label" htmlFor="forgot-email">{t("auth:forgotPassword.emailLabel")}</label>
              <input
                id="forgot-email"
                type="email"
                className="field-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder={t("auth:forgotPassword.emailPlaceholder")}
                autoComplete="email"
              />
            </div>
            {error && <div className="error-banner">{error}</div>}
            <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
              {loading ? t("auth:forgotPassword.sending") : t("auth:forgotPassword.submit")}
            </button>
          </form>
        )}
        <div className="auth-footer">
          <Link to="/login" className="auth-link">{t("auth:forgotPassword.backToLogin")}</Link>
        </div>
      </div>
    </div>
  );
}
