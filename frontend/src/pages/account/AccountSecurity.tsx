import { useState } from "react";
import { useTranslation } from "react-i18next";
import client from "../../api/client";

export default function AccountSecurity() {
  const { t } = useTranslation(["settings", "common"]);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (newPassword.length < 8) {
      setError(t("profile.passwordError"));
      return;
    }
    try {
      await client.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? t("profile.passwordError"));
    }
  }

  return (
    <div className="settings-section">
      <div className="settings-card">
        <h2 className="settings-section-title">{t("profile.changePassword")}</h2>
        <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleChangePassword}>
          <div>
            <label className="field-label">{t("profile.currentPasswordLabel")}</label>
            <input
              type="password"
              className="field-input"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="field-label">{t("profile.newPasswordLabel")}</label>
            <input
              type="password"
              className="field-input"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t("profile.newPasswordPlaceholder")}
              required
              minLength={8}
            />
          </div>
          {error && <p className="error-text">{error}</p>}
          <p style={{ color: "var(--success)", fontSize: 14, minHeight: 20, visibility: success ? "visible" : "hidden" }}>
            {t("profile.passwordUpdated")}
          </p>
          <button className="btn btn-primary" type="submit" style={{ width: "fit-content" }}>
            {t("profile.updatePassword")}
          </button>
        </form>
      </div>
    </div>
  );
}
