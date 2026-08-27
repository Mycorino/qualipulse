import { useState } from "react";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import { useToast } from "../../components/Toast";
import { useAccount } from "./accountContext";

export default function AccountProfile() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const { me, setMe } = useAccount();
  const { toast } = useToast();
  const [name, setName] = useState(me?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [betaSaving, setBetaSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(false);

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSuccess(false);
    setError(false);
    try {
      await client.patch("/auth/me", {
        name: name.trim(),
        preferred_language: i18n.language?.startsWith("fr") ? "fr" : "en",
      });
      setMe((prev) => (prev ? { ...prev, name: name.trim() } : prev));
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  }

  async function handleChangeLanguage(code: "en" | "fr") {
    const previous = i18n.language?.startsWith("fr") ? "fr" : "en";
    if (previous === code) return;
    i18n.changeLanguage(code);
    try {
      await client.patch("/auth/me", { preferred_language: code });
      setMe((prev) => (prev ? { ...prev, preferred_language: code } : prev));
      localStorage.setItem("qp_language", code);
    } catch {
      // Persisting failed — revert so the UI never lies about the saved value.
      i18n.changeLanguage(previous);
      toast(t("profile.saveError", { defaultValue: "Could not save — please try again." }), "error");
    }
  }

  async function handleToggleBeta(next: boolean) {
    setBetaSaving(true);
    try {
      await client.patch("/auth/me", { beta_features_enabled: next });
      setMe((prev) => (prev ? { ...prev, beta_features_enabled: next } : prev));
      toast(
        next
          ? t("beta.enabled", { defaultValue: "Beta features enabled" })
          : t("beta.disabled", { defaultValue: "Beta features disabled" }),
        "success"
      );
    } catch {
      toast(t("profile.saveError", { defaultValue: "Could not save — please try again." }), "error");
    } finally {
      setBetaSaving(false);
    }
  }

  return (
    <div className="settings-section">
      <div className="settings-card">
        <h2 className="settings-section-title">{t("profile.title")}</h2>
        <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleSaveProfile}>
          <div>
            <label className="field-label">{t("profile.nameLabel")}</label>
            <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="field-label">
              {t("profile.emailLabel")}{" "}
              <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-tertiary)" }}>
                ({t("profile.emailReadOnly")})
              </span>
            </label>
            <input
              className="field-input"
              value={me?.email ?? ""}
              disabled
              style={{ opacity: 0.6, cursor: "not-allowed" }}
            />
          </div>
          {error && (
            <p className="error-text" style={{ margin: 0 }}>
              {t("profile.saveError", { defaultValue: "Could not save — please try again." })}
            </p>
          )}
          <p style={{ color: "var(--success)", fontSize: 14, minHeight: 20, visibility: success ? "visible" : "hidden" }}>
            {t("profile.saved")}
          </p>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={saving || !name.trim()}
            style={{ width: "fit-content" }}
          >
            {saving ? t("profile.saving") : t("profile.saveChanges")}
          </button>
        </form>
      </div>

      <div className="settings-card" style={{ marginTop: 20 }}>
        <h2 className="settings-section-title">{t("profile.languageTitle")}</h2>
        <p className="muted-text" style={{ marginBottom: 12, fontSize: 13 }}>
          {t("profile.languageWarning")}
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {(["en", "fr"] as const).map((code) => (
            <button
              key={code}
              className={`btn ${i18n.language?.slice(0, 2) === code ? "btn-primary" : "btn-ghost"}`}
              style={{ minWidth: 100, minHeight: 44 }}
              onClick={() => handleChangeLanguage(code)}
            >
              {code === "en" ? "English" : "Français"}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-card" style={{ marginTop: 20 }}>
        <h2 className="settings-section-title">
          {t("beta.title", { defaultValue: "Beta features" })}
        </h2>
        <p className="muted-text" style={{ marginBottom: 12, fontSize: 13 }}>
          {t("beta.help", {
            defaultValue:
              "Try features we are still refining, before they are released to everyone. They work, but expect rough edges, and tell us what you find. You can turn this off at any time.",
          })}
        </p>
        <label className="setting-toggle-row" htmlFor="beta-features-toggle">
          <input
            id="beta-features-toggle"
            type="checkbox"
            checked={me?.beta_features_enabled === true}
            disabled={betaSaving}
            onChange={(e) => void handleToggleBeta(e.target.checked)}
          />
          <div className="setting-toggle-row__copy">
            <strong>{t("beta.toggleLabel", { defaultValue: "Enable beta features" })}</strong>
            <span className="muted-text" style={{ fontSize: 12 }}>
              {t("beta.toggleHelp", {
                defaultValue:
                  "Currently unlocks live voice interviews, a real-time spoken conversation instead of the record-and-send flow. Turning this off returns every study to the standard interview.",
              })}
            </span>
          </div>
        </label>
      </div>
    </div>
  );
}
