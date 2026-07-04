import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { confirmPanelJoin } from "../api/panel";

/** Destination of the panel-join confirmation email (/panel/confirm#token=...).
 * Exchanges the one-shot join token for a durable panel session, stores it
 * under the same key PanelPortal reads, and drops the panelist straight into
 * the enrichment portal. */
const STORAGE_KEY = "qp_panel_token";

export default function PanelJoinConfirm() {
  const { t } = useTranslation("panel");
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const m = (window.location.hash || "").match(/token=([^&]+)/);
    if (!m) {
      setFailed(true);
      return;
    }
    window.history.replaceState(null, "", window.location.pathname);
    confirmPanelJoin(decodeURIComponent(m[1]))
      .then(({ token }) => {
        sessionStorage.setItem(STORAGE_KEY, token);
        navigate("/panel", { replace: true });
      })
      .catch(() => setFailed(true));
  }, [navigate]);

  return (
    <div className="interview-page">
      <div className="interview-container" style={{ maxWidth: 560 }}>
        <div className="panel-enrich__header" style={{ textAlign: "center" }}>
          {failed ? (
            <>
              <h2 className="panel-enrich__title">{t("confirmErrorTitle")}</h2>
              <p className="panel-enrich__subtitle">{t("confirmErrorBody")}</p>
              <Link to="/participants" className="btn btn-primary" style={{ display: "inline-block", minHeight: 44, marginTop: 8 }}>
                {t("confirmRetryCta")}
              </Link>
            </>
          ) : (
            <p className="panel-enrich__subtitle">{t("loading")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
