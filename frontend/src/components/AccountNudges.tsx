import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getMe, resendVerification } from "../api/auth";

/**
 * AccountNudges — the trial + email-verification banners.
 *
 * Sprint 17 folds the dashboard into the Studies list. The trial banner
 * and verification nudge were furniture on the old project-grid
 * dashboard; this component carries them onto the Studies-list home so
 * the conversion + verification prompts don't get lost in the IA move.
 *
 * Self-contained: fetches `me` on mount, owns its own dismissal state.
 * The markup + i18n keys + CSS classes are lifted verbatim from the old
 * Dashboard so the banners look and behave identically.
 */
export function AccountNudges() {
  const { t } = useTranslation(["dashboard", "common"]);
  const navigate = useNavigate();
  const [me, setMe] = useState<Awaited<ReturnType<typeof getMe>> | null>(null);
  const [trialDismissed, setTrialDismissed] = useState(false);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (!me) return null;

  const handleResend = async () => {
    setResending(true);
    try {
      await resendVerification();
      setResent(true);
    } catch {
      /* swallow — the nudge is non-critical */
    } finally {
      setResending(false);
    }
  };

  const trialBanner = (() => {
    if (!me.trial_ends_at) return null;
    const trialEnd = new Date(me.trial_ends_at);
    if (trialEnd <= new Date()) return null;
    const msLeft = trialEnd.getTime() - Date.now();
    const daysLeft = Math.max(1, Math.ceil(msLeft / (1000 * 60 * 60 * 24)));
    const endingSoon = daysLeft <= 3;
    const dismissKey = `trial-banner-dismissed-${trialEnd.toISOString().slice(0, 10)}`;
    const wasDismissed = trialDismissed || localStorage.getItem(dismissKey) === "true";
    if (wasDismissed && !endingSoon) return null;
    const formattedDate = trialEnd.toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    return (
      <div
        className={`gs-trial-banner${endingSoon ? " gs-trial-banner--urgent" : ""}`}
        style={{ marginBottom: 16 }}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-flex",
            alignItems: "center",
            color: endingSoon ? "var(--danger-text, #b91c1c)" : "var(--primary, #4369f5)",
          }}
        >
          {endingSoon ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/></svg>
          )}
        </span>
        <div style={{ flex: 1 }}>
          <strong>
            {endingSoon
              ? t("dashboard:trialBanner.endingSoonTitle", { count: daysLeft })
              : t("dashboard:trialBanner.title")}
          </strong>{" "}
          <span className="gs-trial-badge">
            {t("dashboard:trialBanner.daysLeft", { count: daysLeft })}
          </span>
          <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.5 }}>
            {endingSoon
              ? t("dashboard:trialBanner.endingSoonDesc", { date: formattedDate })
              : t("dashboard:trialBanner.desc", { date: formattedDate })}
          </div>
        </div>
        <button
          className={endingSoon ? "btn btn-primary btn-sm" : "btn-inline"}
          onClick={() => navigate("/account")}
          style={{ whiteSpace: "nowrap", flexShrink: 0 }}
        >
          {endingSoon
            ? t("dashboard:trialBanner.upgradeCta")
            : t("dashboard:trialBanner.viewPlans")}
        </button>
        {!endingSoon && (
          <button
            type="button"
            className="gs-trial-banner-dismiss"
            aria-label={t("dashboard:trialBanner.dismissAria")}
            onClick={() => {
              localStorage.setItem(dismissKey, "true");
              setTrialDismissed(true);
            }}
          >
            ✕
          </button>
        )}
      </div>
    );
  })();

  const verifyBanner =
    !me.email_verified ? (
      <div className="gs-verify-banner" style={{ marginBottom: 16 }}>
        <span>&#128231;</span>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span>
            <strong>{t("common:verifyEmail")}</strong> — {t("common:verifyEmailDesc")}
          </span>
          {resent ? (
            <span style={{ fontSize: 13, color: "#16a34a" }}>{t("common:emailSent")}</span>
          ) : (
            <button className="btn-inline" disabled={resending} onClick={handleResend}>
              {resending ? t("common:resending") : t("common:resendEmail")}
            </button>
          )}
        </div>
      </div>
    ) : null;

  if (!trialBanner && !verifyBanner) return null;
  return (
    <>
      {verifyBanner}
      {trialBanner}
    </>
  );
}
