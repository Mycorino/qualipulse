import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { panelOptOut } from "../api/recontact";

/**
 * /panel/optout — public landing for the opt-out link in invite emails.
 *
 * Deliberately requires one button click before firing the POST: email
 * security scanners prefetch links, and a GET-triggered opt-out would
 * silently unsubscribe people whose mail provider "clicked" for them.
 */
export default function PanelOptOut() {
  const { t } = useTranslation("panel");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"idle" | "working" | "done" | "error">(
    token ? "idle" : "error",
  );

  async function confirm() {
    setState("working");
    try {
      await panelOptOut(token);
      setState("done");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="auth-page" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ maxWidth: 440, width: "100%", background: "#fff", border: "1px solid var(--border-color, #e2e8f0)", borderRadius: 16, padding: 32, textAlign: "center" }}>
        <span style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--brand-600, #4f46e5)" }}>QualiPulse</span>

        {state === "done" ? (
          <>
            <h1 style={{ fontSize: 20, margin: "18px 0 8px" }}>{t("optout.doneTitle")}</h1>
            <p className="muted-text" style={{ fontSize: 14, lineHeight: 1.6 }}>{t("optout.doneBody")}</p>
          </>
        ) : state === "error" ? (
          <>
            <h1 style={{ fontSize: 20, margin: "18px 0 8px" }}>{t("optout.errorTitle")}</h1>
            <p className="muted-text" style={{ fontSize: 14, lineHeight: 1.6 }}>{t("optout.errorBody")}</p>
          </>
        ) : (
          <>
            <h1 style={{ fontSize: 20, margin: "18px 0 8px" }}>{t("optout.title")}</h1>
            <p className="muted-text" style={{ fontSize: 14, lineHeight: 1.6 }}>{t("optout.body")}</p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 16 }}
              disabled={state === "working"}
              onClick={() => void confirm()}
            >
              {state === "working" ? t("optout.working") : t("optout.cta")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
