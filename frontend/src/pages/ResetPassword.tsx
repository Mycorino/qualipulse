import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../api/client";
import { getErrorMessage } from "../utils/errorMessages";

export default function ResetPassword() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError(t("auth:resetPassword.passwordsMismatch")); return; }
    if (password.length < 8) { setError(t("auth:resetPassword.passwordTooShort")); return; }
    setLoading(true);
    setError("");
    try {
      await client.post("/auth/password-reset/confirm", { token, new_password: password });
      navigate("/login?reset=success");
    } catch (err: unknown) {
      const msg = getErrorMessage(err, "");
      // If it's a token issue, show a specific message
      if (msg.toLowerCase().includes("token") || msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("invalid")) {
        setError(t("auth:resetPassword.tokenExpired"));
      } else {
        setError(msg || t("auth:resetPassword.defaultError"));
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
          <h1 className="auth-title">{t("auth:resetPassword.invalidLinkTitle")}</h1>
          <p className="auth-subtitle">{t("auth:resetPassword.invalidLinkSubtitle")}</p>
          <Link to="/forgot-password" className="btn btn-primary btn-block" style={{ textAlign: "center", textDecoration: "none" }}>{t("auth:resetPassword.requestNew")}</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">{t("auth:resetPassword.title")}</h1>
        <p className="auth-subtitle">{t("auth:resetPassword.subtitle")}</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <div>
            <label className="field-label">{t("auth:resetPassword.newPasswordLabel")}</label>
            <input
              type="password"
              className="field-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder={t("auth:resetPassword.newPasswordPlaceholder")}
            />
          </div>
          <div>
            <label className="field-label">{t("auth:resetPassword.confirmPasswordLabel")}</label>
            <input
              type="password"
              className="field-input"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              placeholder={t("auth:resetPassword.confirmPasswordPlaceholder")}
            />
          </div>
          {error && <div className="error-banner">{error}</div>}
          <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
            {loading ? t("auth:resetPassword.updating") : t("auth:resetPassword.submit")}
          </button>
        </form>
      </div>
    </div>
  );
}
