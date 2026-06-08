import { useState } from "react";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import { useAccount } from "./accountContext";

export default function AccountProfile() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const { me, setMe } = useAccount();
  const [name, setName] = useState(me?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSuccess(false);
    try {
      await client.patch("/auth/me", {
        name: name.trim(),
        preferred_language: i18n.language?.startsWith("fr") ? "fr" : "en",
      });
      setMe((prev) => (prev ? { ...prev, name: name.trim() } : prev));
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch {
      /* silently fail for now */
    } finally {
      setSaving(false);
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
          <p style={{ color: "var(--success)", fontSize: 14, minHeight: 20, visibility: success ? "visible" : "hidden" }}>
            {t("profile.saved")}
          </p>
          <button className="btn btn-primary" type="submit" disabled={saving} style={{ width: "fit-content" }}>
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
              onClick={async () => {
                i18n.changeLanguage(code);
                try {
                  await client.patch("/auth/me", { preferred_language: code });
                  setMe((prev) => (prev ? { ...prev, preferred_language: code } : prev));
                } catch {
                  /* best-effort */
                }
              }}
            >
              {code === "en" ? "English" : "Français"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
