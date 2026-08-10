import { useState } from "react";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import {
  setupTwoFactor,
  enableTwoFactor,
  disableTwoFactor,
  logoutAllSessions,
  deleteAccount,
} from "../../api/auth";
import { useAuth } from "../../hooks/useAuth";
import { getErrorMessage } from "../../utils/errorMessages";
import { useAccount } from "./accountContext";

export default function AccountSecurity() {
  const { t } = useTranslation(["settings", "common"]);
  const { saveToken, logout } = useAuth();
  const { me } = useAccount();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  // ── 2FA state ── seeded from the layout's /auth/me fetch (no extra call)
  const [totpEnabled, setTotpEnabled] = useState<boolean>(Boolean(me?.totp_enabled));
  const [setupData, setSetupData] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [enableCode, setEnableCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [disableCode, setDisableCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [showDisable, setShowDisable] = useState(false);
  const [twoFaError, setTwoFaError] = useState("");
  const [twoFaBusy, setTwoFaBusy] = useState(false);

  const [logoutAllBusy, setLogoutAllBusy] = useState(false);

  // ── Account deletion (danger zone) ──
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (newPassword.length < 8) {
      setError(t("profile.passwordError"));
      return;
    }
    try {
      const { data } = await client.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      // The backend revokes all sessions on password change and returns
      // fresh tokens for this one — store them or the next request 401s.
      if (data?.access_token) {
        saveToken(data.access_token, data.refresh_token);
      }
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? t("profile.passwordError"));
    }
  }

  async function handleStartSetup() {
    setTwoFaError("");
    setTwoFaBusy(true);
    try {
      const data = await setupTwoFactor();
      setSetupData(data);
    } catch (err: unknown) {
      setTwoFaError(getErrorMessage(err, t("security.twoFactor.genericError")));
    } finally {
      setTwoFaBusy(false);
    }
  }

  async function handleEnable(e: React.FormEvent) {
    e.preventDefault();
    setTwoFaError("");
    setTwoFaBusy(true);
    try {
      const res = await enableTwoFactor(enableCode.trim());
      setBackupCodes(res.backup_codes);
      setTotpEnabled(true);
      setSetupData(null);
      setEnableCode("");
    } catch (err: unknown) {
      setTwoFaError(getErrorMessage(err, t("security.twoFactor.invalidCode")));
    } finally {
      setTwoFaBusy(false);
    }
  }

  async function handleDisable(e: React.FormEvent) {
    e.preventDefault();
    setTwoFaError("");
    setTwoFaBusy(true);
    try {
      await disableTwoFactor(disableCode.trim(), disablePassword || undefined);
      setTotpEnabled(false);
      setShowDisable(false);
      setDisableCode("");
      setDisablePassword("");
      setBackupCodes(null);
    } catch (err: unknown) {
      setTwoFaError(getErrorMessage(err, t("security.twoFactor.invalidCode")));
    } finally {
      setTwoFaBusy(false);
    }
  }

  async function handleDeleteAccount(e: React.FormEvent) {
    e.preventDefault();
    setDeleteError("");
    if (!deleteConfirmValue) return;
    if (!window.confirm(t("security.deleteAccount.finalConfirm"))) return;
    setDeleteBusy(true);
    try {
      // Password accounts verify the password; Google-only accounts type
      // DELETE instead — the backend checks whichever applies.
      await deleteAccount(deleteConfirmValue, deleteConfirmValue);
      logout();
    } catch (err: unknown) {
      setDeleteError(getErrorMessage(err, t("security.deleteAccount.genericError")));
      setDeleteBusy(false);
    }
  }

  async function handleLogoutAll() {
    if (!window.confirm(t("security.logoutAll.confirm"))) return;
    setLogoutAllBusy(true);
    try {
      await logoutAllSessions();
    } catch {
      // Even if the call failed we still drop local tokens below.
    }
    logout();
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

      <div className="settings-card">
        <h2 className="settings-section-title">{t("security.twoFactor.title")}</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 14, marginTop: 0 }}>
          {t("security.twoFactor.description")}
        </p>
        {twoFaError && <p className="error-text">{twoFaError}</p>}

        {backupCodes && (
          <div style={{ background: "var(--surface-alt, #f8fafc)", border: "1px solid var(--border)", borderRadius: 8, padding: 16, marginBottom: 16 }}>
            <strong>{t("security.twoFactor.backupCodesTitle")}</strong>
            <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {t("security.twoFactor.backupCodesHint")}
            </p>
            <pre style={{ fontSize: 13, lineHeight: 1.8, whiteSpace: "pre-wrap", userSelect: "all" }}>
              {backupCodes.join("\n")}
            </pre>
            <button className="btn btn-secondary" type="button" onClick={() => setBackupCodes(null)}>
              {t("security.twoFactor.backupCodesDone")}
            </button>
          </div>
        )}

        {totpEnabled ? (
          <>
            <p style={{ color: "var(--success)", fontSize: 14 }}>
              ✓ {t("security.twoFactor.enabledStatus")}
            </p>
            {!showDisable ? (
              <button className="btn btn-secondary" type="button" onClick={() => setShowDisable(true)}>
                {t("security.twoFactor.disableCta")}
              </button>
            ) : (
              <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleDisable}>
                <div>
                  <label className="field-label">{t("security.twoFactor.currentCodeLabel")}</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    className="field-input"
                    value={disableCode}
                    onChange={(e) => setDisableCode(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="field-label">{t("profile.currentPasswordLabel")}</label>
                  <input
                    type="password"
                    className="field-input"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                  />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-danger-text" type="submit" disabled={twoFaBusy}>
                    {t("security.twoFactor.disableConfirm")}
                  </button>
                  <button className="btn btn-secondary" type="button" onClick={() => setShowDisable(false)}>
                    {t("common:cancel")}
                  </button>
                </div>
              </form>
            )}
          </>
        ) : setupData ? (
          <div style={{ maxWidth: 480 }}>
            <ol style={{ fontSize: 14, color: "var(--text-secondary)", paddingLeft: 20, lineHeight: 1.7 }}>
              <li>{t("security.twoFactor.step1")}</li>
              <li>
                {t("security.twoFactor.step2")}
                <div style={{ margin: "8px 0", padding: "10px 12px", background: "var(--surface-alt, #f8fafc)", border: "1px solid var(--border)", borderRadius: 8, fontFamily: "monospace", fontSize: 15, letterSpacing: 1, userSelect: "all" }}>
                  {setupData.secret}
                </div>
                <a href={setupData.otpauth_url} style={{ fontSize: 13 }}>
                  {t("security.twoFactor.openInApp")}
                </a>
              </li>
              <li>{t("security.twoFactor.step3")}</li>
            </ol>
            <form className="auth-form" onSubmit={handleEnable}>
              <div>
                <label className="field-label">{t("security.twoFactor.codeLabel")}</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  className="field-input"
                  value={enableCode}
                  onChange={(e) => setEnableCode(e.target.value)}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary" type="submit" disabled={twoFaBusy}>
                  {t("security.twoFactor.enableConfirm")}
                </button>
                <button className="btn btn-secondary" type="button" onClick={() => setSetupData(null)}>
                  {t("common:cancel")}
                </button>
              </div>
            </form>
          </div>
        ) : (
          <button className="btn btn-primary" type="button" disabled={twoFaBusy} onClick={handleStartSetup}>
            {t("security.twoFactor.enableCta")}
          </button>
        )}
      </div>

      <div className="settings-card">
        <h2 className="settings-section-title">{t("security.logoutAll.title")}</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 14, marginTop: 0 }}>
          {t("security.logoutAll.description")}
        </p>
        <button className="btn btn-secondary" type="button" disabled={logoutAllBusy} onClick={handleLogoutAll}>
          {t("security.logoutAll.cta")}
        </button>
      </div>

      <div className="settings-card" style={{ borderColor: "var(--danger, #b91c1c)" }}>
        <h2 className="settings-section-title" style={{ color: "var(--danger, #b91c1c)" }}>
          {t("security.deleteAccount.title")}
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 14, marginTop: 0 }}>
          {t("security.deleteAccount.description")}
        </p>
        {!showDeleteAccount ? (
          <button className="btn btn-danger-text" type="button" onClick={() => setShowDeleteAccount(true)}>
            {t("security.deleteAccount.cta")}
          </button>
        ) : (
          <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleDeleteAccount}>
            <div>
              <label className="field-label">{t("security.deleteAccount.confirmLabel")}</label>
              <input
                type="password"
                className="field-input"
                value={deleteConfirmValue}
                onChange={(e) => setDeleteConfirmValue(e.target.value)}
                autoComplete="current-password"
                required
              />
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6 }}>
                {t("security.deleteAccount.oauthHint")}
              </p>
            </div>
            {deleteError && <p className="error-text">{deleteError}</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-danger-text" type="submit" disabled={deleteBusy || !deleteConfirmValue}>
                {t("security.deleteAccount.confirmCta")}
              </button>
              <button
                className="btn btn-secondary"
                type="button"
                onClick={() => { setShowDeleteAccount(false); setDeleteConfirmValue(""); setDeleteError(""); }}
              >
                {t("common:cancel")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
