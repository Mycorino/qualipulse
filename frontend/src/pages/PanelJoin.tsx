import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguagePicker from "../components/LanguagePicker";
import { joinPanel } from "../api/panel";

/**
 * Public panel recruitment page (/participants) — the front door for people
 * who want to join the participant pool before any specific study exists.
 * Double opt-in: the form only triggers a confirmation email; consent is
 * recorded when the emailed link is clicked (→ /panel/confirm).
 */
export default function PanelJoin() {
  const { t, i18n } = useTranslation("panel");
  const [firstName, setFirstName] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(false);

  const canSubmit = email.trim().length > 3 && consent && !submitting;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(false);
    try {
      await joinPanel({
        email: email.trim(),
        first_name: firstName.trim() || undefined,
        lang: (i18n.language || "en").slice(0, 2),
        consent: true,
      });
      setSent(true);
    } catch {
      setError(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="interview-page">
      <div className="interview-container" style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <LanguagePicker />
        </div>
        {sent ? (
          <div className="panel-enrich__header" style={{ textAlign: "center" }}>
            <h2 className="panel-enrich__title">{t("joinSentTitle")}</h2>
            <p className="panel-enrich__subtitle">{t("joinSentBody", { email: email.trim() })}</p>
          </div>
        ) : (
          <div className="panel-enrich__header">
            <h1 className="panel-enrich__title">{t("joinTitle")}</h1>
            <p className="panel-enrich__subtitle">{t("joinSubtitle")}</p>

            <ol style={{ margin: "16px 0 24px", paddingLeft: 22, display: "grid", gap: 8, textAlign: "left" }}>
              <li>{t("joinStep1")}</li>
              <li>{t("joinStep2")}</li>
              <li>{t("joinStep3")}</li>
            </ol>

            <form onSubmit={handleSubmit}>
              <input
                type="text"
                className="field-input"
                style={{ width: "100%", marginBottom: 12 }}
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder={t("joinFirstNamePlaceholder")}
                autoComplete="given-name"
              />
              <input
                type="email"
                className="field-input"
                style={{ width: "100%", marginBottom: 12 }}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("emailPlaceholder")}
                autoComplete="email"
                required
              />
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", margin: "4px 0 16px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  style={{ marginTop: 3, minWidth: 16, minHeight: 16 }}
                />
                <span style={{ fontSize: "0.9rem", lineHeight: 1.5 }}>
                  {t("joinConsentPrefix")}{" "}
                  <Link to="/privacy" target="_blank">{t("joinConsentPrivacy")}</Link>{" "}
                  {t("joinConsentAnd")}{" "}
                  <Link to="/participant-notice" target="_blank">{t("joinConsentNotice")}</Link>.
                </span>
              </label>
              {error && (
                <p role="alert" style={{ color: "var(--danger, #dc2626)", fontSize: "0.9rem", margin: "0 0 12px" }}>
                  {t("joinError")}
                </p>
              )}
              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", minHeight: 44 }}
                disabled={!canSubmit}
              >
                {submitting ? t("loading") : t("joinCta")}
              </button>
            </form>

            <p style={{ textAlign: "center", marginTop: 20, fontSize: "0.9rem" }}>
              {t("joinAlready")} <Link to="/panel">{t("joinAlreadyCta")}</Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
