import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PanelEnrichment from "../components/PanelEnrichment";
import LanguagePicker from "../components/LanguagePicker";
import { requestPanelAccess } from "../api/panel";

/**
 * Durable panel portal — the destination of the emailed "manage your panel"
 * link. The panel_session JWT rides in the URL fragment (#token=...), never
 * hitting the server in logs. Persisted to sessionStorage so a refresh keeps
 * working. With no token, offers to re-send the access link by email.
 */
const STORAGE_KEY = "qp_panel_token";

export default function PanelPortal() {
  const { t, i18n } = useTranslation("panel");
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    // Pull token from the URL fragment, then clear it from the address bar.
    const hash = window.location.hash || "";
    const m = hash.match(/token=([^&]+)/);
    if (m) {
      const tok = decodeURIComponent(m[1]);
      sessionStorage.setItem(STORAGE_KEY, tok);
      setToken(tok);
      window.history.replaceState(null, "", window.location.pathname);
      return;
    }
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) setToken(saved);
  }, []);

  async function handleRequest() {
    if (!email.trim()) return;
    try {
      await requestPanelAccess(email.trim(), (i18n.language || "en").slice(0, 2));
    } catch { /* always-200 on the server; ignore */ }
    setRequested(true);
  }

  return (
    <div className="interview-page">
      <div className="interview-container" style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <LanguagePicker />
        </div>
        {token ? (
          <PanelEnrichment token={token} />
        ) : requested ? (
          <div className="panel-enrich__header" style={{ textAlign: "center" }}>
            <h2 className="panel-enrich__title">{t("requestSentTitle")}</h2>
            <p className="panel-enrich__subtitle">{t("requestSentBody")}</p>
          </div>
        ) : (
          <div className="panel-enrich__header">
            <h2 className="panel-enrich__title">{t("portalTitle")}</h2>
            <p className="panel-enrich__subtitle">{t("portalBody")}</p>
            <input
              type="email"
              className="field-input"
              style={{ width: "100%", margin: "12px 0" }}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("emailPlaceholder")}
            />
            <button className="btn btn-primary" style={{ width: "100%", minHeight: 44 }} onClick={handleRequest}>
              {t("requestCta")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
