import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import client from "../api/client";

/**
 * SurveyQuotaBanner — Sprint 12 upgrade-nudge surface.
 *
 * Renders inline above the survey list and Study Overview tabs. Three
 * states, three appearances:
 *
 *   - Under 80% capacity: hidden entirely (silent).
 *   - 80-99%: yellow "nearing limit" nudge with the count + upgrade CTA.
 *   - At or over cap: red "quota reached" — collection paused, upgrade CTA.
 *
 * Why three states: the consultant audit said don't pollute the insight
 * flow with billing chrome. Silent until it's actually relevant.
 */

interface SurveyQuotaSnapshot {
  responses_used: number;
  responses_cap: number | null;
  surveys_active: number;
  surveys_cap: number | null;
  questions_per_survey_cap: number | null;
  period_start: string;
  period_end: string | null;
  is_over_response_cap: boolean;
  is_near_response_cap: boolean;
  is_over_surveys_cap: boolean;
}

export function SurveyQuotaBanner() {
  const [quota, setQuota] = useState<SurveyQuotaSnapshot | null>(null);
  const navigate = useNavigate();
  const { t } = useTranslation("survey");

  useEffect(() => {
    client
      .get<SurveyQuotaSnapshot>("/billing/survey-quota")
      .then((r) => setQuota(r.data))
      .catch(() => setQuota(null));
  }, []);

  // Silent below the noise threshold. This is the *response*-quota nudge —
  // its copy talks only about responses, so it must key off the response
  // flags alone. The surveys-active cap is a different quota; surfacing it
  // here rendered a misleading "2 of 100 responses (2%)" message whenever a
  // workspace had one survey too many, firing far below the 80% response
  // threshold. The surveys cap is already enforced at survey-creation time.
  if (!quota) return null;
  if (!quota.is_over_response_cap && !quota.is_near_response_cap) {
    return null;
  }

  const cap = quota.responses_cap;
  const pct = cap ? Math.min(100, Math.round((quota.responses_used / cap) * 100)) : null;
  const tone: "warn" | "danger" = quota.is_over_response_cap ? "danger" : "warn";

  const headline = quota.is_over_response_cap
    ? t("quotaBanner.capReached")
    : t("quotaBanner.nearingCap");

  const detail = cap
    ? pct !== null
      ? t("quotaBanner.detailWithCap", { used: quota.responses_used, cap, pct })
      : t("quotaBanner.detailWithCapNoPct", { used: quota.responses_used, cap })
    : t("quotaBanner.detailNoCap", { used: quota.responses_used });

  return (
    <div
      role="status"
      style={{
        background:
          tone === "danger" ? "var(--danger-bg)" : "var(--warning-bg)",
        border: `1px solid ${
          tone === "danger" ? "var(--danger-border)" : "var(--warning-border)"
        }`,
        color: tone === "danger" ? "var(--danger-text)" : "var(--warning-text)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-3) var(--space-4)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        marginBottom: "var(--space-4)",
      }}
    >
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
          ⚠ {headline}
        </div>
        <div style={{ fontSize: "var(--text-xs)", marginTop: 2 }} className="tabular">
          {detail}
          {quota.is_over_response_cap && cap !== null && (
            <>
              {" "}{t("quotaBanner.pausedSuffix")}
            </>
          )}
        </div>
      </div>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => navigate("/account/billing")}
      >
        {t("quotaBanner.viewPlans")}
      </button>
    </div>
  );
}
