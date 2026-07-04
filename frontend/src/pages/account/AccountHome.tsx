import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import { useAccount, SLACK_INTEGRATION_ENABLED } from "./accountContext";

/**
 * Account Home — status-card overview. Leads with the account state that
 * actually matters (email verification, plan & credits, workspace seats,
 * integrations, billing action) instead of a settings form.
 */
export default function AccountHome() {
  const { t } = useTranslation(["settings", "common"]);
  const { me, billing } = useAccount();
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendError, setResendError] = useState(false);

  const verified = me?.email_verified ?? true;

  async function handleResend() {
    setResending(true);
    setResendError(false);
    try {
      await client.post("/auth/resend-verification");
      setResent(true);
    } catch {
      // Rate-limited (3/min) or transient failure — tell the user instead
      // of silently doing nothing.
      setResendError(true);
    } finally {
      setResending(false);
    }
  }

  const credits = billing?.credits;
  const isTrial = billing?.display?.is_trial ?? false;
  const planName = billing?.display?.plan_name ?? billing?.plan?.name ?? billing?.tier_name;
  const totalGranted = credits
    ? credits.included_credits + credits.purchased_credits + credits.rollover_credits
    : 0;
  const slackConnected = Boolean(me?.slack_webhook_url);
  const seatLimit = billing?.limits.team_members ?? 1;

  return (
    <div className="settings-section">
      <div className="account-home-grid">
        {/* Email verification — first-class action when unverified. */}
        <div className={`account-card ${verified ? "" : "account-card--action"}`}>
          <div className="account-card__head">
            <span className="account-card__label">
              {t("home.emailCard.label", { defaultValue: "Email verification" })}
            </span>
            <span className={`account-card__status ${verified ? "is-ok" : "is-warn"}`}>
              {verified
                ? t("home.emailCard.verified", { defaultValue: "Verified" })
                : t("home.emailCard.unverified", { defaultValue: "Not verified" })}
            </span>
          </div>
          <p className="account-card__value">{me?.email}</p>
          {!verified && (
            <div className="account-card__foot">
              {resent ? (
                <p className="muted-text" style={{ fontSize: 13, margin: 0 }}>
                  {t("home.emailCard.resent", {
                    defaultValue: "Verification email sent — check your inbox.",
                  })}
                </p>
              ) : (
                <>
                  <p className="muted-text" style={{ fontSize: 13, margin: "0 0 10px" }}>
                    {t("home.emailCard.body", {
                      defaultValue:
                        "Verify your email to secure your account and unlock interview credits.",
                    })}
                  </p>
                  {resendError && (
                    <p className="error-text" style={{ fontSize: 13, margin: "0 0 10px" }}>
                      {t("home.emailCard.resendError", {
                        defaultValue: "Could not send the email — please try again in a minute.",
                      })}
                    </p>
                  )}
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleResend}
                    disabled={resending}
                  >
                    {resending
                      ? t("common:loading", { defaultValue: "Loading…" })
                      : t("home.emailCard.resend", { defaultValue: "Resend verification email" })}
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        {/* Plan & credits. */}
        <div className="account-card">
          <div className="account-card__head">
            <span className="account-card__label">
              {t("home.planCard.label", { defaultValue: "Plan & credits" })}
            </span>
            <span className="account-card__status is-neutral">
              {isTrial ? t("billing.freeTrial", { defaultValue: "Free trial" }) : planName}
            </span>
          </div>
          {credits ? (
            <>
              <p className="account-card__value">
                <strong style={{ fontSize: 28 }}>{credits.available_credits}</strong>{" "}
                <span className="muted-text" style={{ fontSize: 14 }}>
                  {t("home.planCard.creditsRemaining", { defaultValue: "credits remaining" })}
                </span>
              </p>
              <p className="muted-text" style={{ fontSize: 13, margin: "2px 0 0" }}>
                {t("home.planCard.creditsUsed", {
                  defaultValue: "{{used}} of {{total}} used",
                  used: credits.used_credits,
                  total: totalGranted,
                })}
                {isTrial && (
                  <> · {t("home.planCard.noExpiry", { defaultValue: "never expire" })}</>
                )}
              </p>
            </>
          ) : (
            <p className="account-card__value">{planName}</p>
          )}
          <div className="account-card__foot">
            <Link className="btn btn-ghost btn-sm" to="/account/billing">
              {isTrial
                ? t("home.planCard.upgradeCta", { defaultValue: "View plans & upgrade →" })
                : t("home.planCard.manageCta", { defaultValue: "Manage billing →" })}
            </Link>
          </div>
        </div>

        {/* Workspace / team seats. */}
        <div className="account-card">
          <div className="account-card__head">
            <span className="account-card__label">
              {t("home.workspaceCard.label", { defaultValue: "Workspace" })}
            </span>
          </div>
          <p className="account-card__value">
            <strong style={{ fontSize: 28 }}>{seatLimit === -1 ? "∞" : seatLimit}</strong>{" "}
            <span className="muted-text" style={{ fontSize: 14 }}>
              {t("home.workspaceCard.seats", { defaultValue: "team seats" })}
            </span>
          </p>
          <div className="account-card__foot">
            <Link className="btn btn-ghost btn-sm" to="/account/workspace">
              {t("home.workspaceCard.cta", { defaultValue: "Manage members →" })}
            </Link>
          </div>
        </div>

        {/* Slack integration — hidden while the integration is paused. */}
        {SLACK_INTEGRATION_ENABLED && (
        <div className="account-card">
          <div className="account-card__head">
            <span className="account-card__label">
              {t("home.slackCard.label", { defaultValue: "Slack notifications" })}
            </span>
            <span className={`account-card__status ${slackConnected ? "is-ok" : "is-neutral"}`}>
              {slackConnected
                ? t("home.slackCard.connected", { defaultValue: "Connected" })
                : t("home.slackCard.notConnected", { defaultValue: "Not connected" })}
            </span>
          </div>
          <p className="muted-text" style={{ fontSize: 13, margin: "4px 0 0" }}>
            {slackConnected
              ? t("home.slackCard.connectedBody", {
                  defaultValue: "Completed-interview alerts are delivered to your channel.",
                })
              : t("home.slackCard.body", {
                  defaultValue: "Get a ping in Slack when an interview completes.",
                })}
          </p>
          <div className="account-card__foot">
            <Link className="btn btn-ghost btn-sm" to="/account/integrations">
              {slackConnected
                ? t("home.slackCard.manageCta", { defaultValue: "Manage →" })
                : t("home.slackCard.connectCta", { defaultValue: "Connect Slack →" })}
            </Link>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
