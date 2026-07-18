import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import { listTeamMembers } from "../../api/team";
import { useAccount, SLACK_INTEGRATION_ENABLED } from "./accountContext";

/**
 * Account Home — status-card overview. Leads with the account state that
 * actually matters (email verification, plan & credits, workspace seats,
 * security, integrations) instead of a settings form. Cards report *usage*,
 * not just plan limits, and the one actionable card carries the page's
 * single primary CTA.
 */
export default function AccountHome() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const { me, billing } = useAccount();
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendError, setResendError] = useState(false);
  // Seats actually occupied (owner included). Null until the fetch lands —
  // the card falls back to showing the plan limit alone.
  const [memberCount, setMemberCount] = useState<number | null>(null);

  useEffect(() => {
    listTeamMembers()
      .then((members) => setMemberCount(members.length))
      .catch(() => {});
  }, []);

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
  const extraCredits = credits ? credits.purchased_credits + credits.rollover_credits : 0;
  const usedPct = totalGranted > 0 ? Math.min(100, (credits!.used_credits / totalGranted) * 100) : 0;
  const slackConnected = Boolean(me?.slack_webhook_url);
  const seatLimit = billing?.limits.team_members ?? 1;
  const totpEnabled = me?.totp_enabled ?? false;

  const formatDate = (iso: string, opts: Intl.DateTimeFormatOptions) =>
    new Date(iso).toLocaleDateString(i18n.language, opts);

  const emailCard = (
    <div key="email" className={`account-card ${verified ? "" : "account-card--action"}`}>
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
      {verified ? (
        me?.created_at && (
          <p className="account-card__hint">
            {t("home.emailCard.memberSince", {
              defaultValue: "Member since {{date}}",
              date: formatDate(me.created_at, { month: "long", year: "numeric" }),
            })}
          </p>
        )
      ) : (
        <div className="account-card__foot">
          {resent ? (
            <p className="account-card__hint">
              {t("home.emailCard.resent", {
                defaultValue: "Verification email sent — check your inbox.",
              })}
            </p>
          ) : (
            <>
              <p className="account-card__hint account-card__hint--gap">
                {t("home.emailCard.body", {
                  defaultValue:
                    "Verify your email to secure your account and unlock interview credits.",
                })}
              </p>
              {resendError && (
                <p className="error-text account-card__hint account-card__hint--gap">
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
  );

  const planCard = (
    <div key="plan" className="account-card">
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
            <strong className="account-card__metric">{credits.available_credits}</strong>{" "}
            <span className="account-card__metric-unit">
              {t("home.planCard.creditsRemaining", { defaultValue: "credits remaining" })}
            </span>
          </p>
          <div
            className="account-meter"
            role="img"
            aria-label={t("home.planCard.creditsUsed", {
              defaultValue: "{{used}} of {{total}} used",
              used: credits.used_credits,
              total: totalGranted,
            })}
          >
            <i style={{ width: `${usedPct}%` }} />
          </div>
          <p className="account-card__hint">
            {t("home.planCard.creditsUsed", {
              defaultValue: "{{used}} of {{total}} used",
              used: credits.used_credits,
              total: totalGranted,
            })}
            {extraCredits > 0 && (
              <>
                {" · "}
                {t("home.planCard.breakdown", {
                  defaultValue: "{{included}} plan + {{extra}} extra",
                  included: credits.included_credits,
                  extra: extraCredits,
                })}
              </>
            )}
            {isTrial && <> · {t("home.planCard.noExpiry", { defaultValue: "never expire" })}</>}
            {!isTrial && credits.period_end && (
              <>
                {" · "}
                {t("home.planCard.renews", {
                  defaultValue: "renews {{date}}",
                  date: formatDate(credits.period_end, { day: "numeric", month: "short" }),
                })}
              </>
            )}
          </p>
        </>
      ) : (
        <p className="account-card__value">{planName}</p>
      )}
      <div className="account-card__foot">
        {/* Trial accounts get a real CTA — upgrading is the one action this
            card exists for. While the email is unverified, the email card
            owns the page's single primary button. */}
        <Link
          className={`btn ${isTrial && verified ? "btn-primary" : "btn-ghost"} btn-sm`}
          to="/account/billing"
        >
          {isTrial
            ? t("home.planCard.upgradeCta", { defaultValue: "View plans & upgrade →" })
            : t("home.planCard.manageCta", { defaultValue: "Manage billing →" })}
        </Link>
      </div>
    </div>
  );

  const soloTrial = isTrial && seatLimit !== -1 && seatLimit <= 1;
  const workspaceCard = (
    <div key="workspace" className="account-card">
      <div className="account-card__head">
        <span className="account-card__label">
          {t("home.workspaceCard.label", { defaultValue: "Workspace" })}
        </span>
      </div>
      {memberCount !== null && seatLimit !== -1 ? (
        <p className="account-card__value">
          <strong className="account-card__metric">{memberCount}</strong>{" "}
          <span className="account-card__metric-unit">
            {t("home.workspaceCard.seatsUsed", {
              defaultValue: "of {{total}} seats used",
              total: seatLimit,
              count: seatLimit,
            })}
          </span>
        </p>
      ) : (
        <p className="account-card__value">
          <strong className="account-card__metric">
            {seatLimit === -1 ? "∞" : seatLimit}
          </strong>{" "}
          <span className="account-card__metric-unit">
            {t("home.workspaceCard.seats", {
              defaultValue: "team seats",
              count: seatLimit === -1 ? 2 : seatLimit,
            })}
          </span>
        </p>
      )}
      {soloTrial && (
        <p className="account-card__hint">
          {t("home.workspaceCard.soloHint", {
            defaultValue: "Working with a team? Paid plans include multiple seats.",
          })}
        </p>
      )}
      <div className="account-card__foot">
        {/* A 1-seat trial can't invite anyone — point the CTA at the plans
            that can instead of at a dead-end members page. */}
        {soloTrial ? (
          <Link className="btn btn-ghost btn-sm" to="/account/billing">
            {t("home.workspaceCard.addSeatsCta", { defaultValue: "Add team seats →" })}
          </Link>
        ) : (
          <Link className="btn btn-ghost btn-sm" to="/account/workspace">
            {t("home.workspaceCard.cta", { defaultValue: "Manage members →" })}
          </Link>
        )}
      </div>
    </div>
  );

  const securityCard = (
    <div key="security" className="account-card">
      <div className="account-card__head">
        <span className="account-card__label">
          {t("home.securityCard.label", { defaultValue: "Security" })}
        </span>
        <span className={`account-card__status ${totpEnabled ? "is-ok" : "is-neutral"}`}>
          {totpEnabled
            ? t("home.securityCard.enabled", { defaultValue: "2FA enabled" })
            : t("home.securityCard.disabled", { defaultValue: "2FA off" })}
        </span>
      </div>
      <p className="account-card__hint">
        {totpEnabled
          ? t("home.securityCard.enabledBody", {
              defaultValue: "Your account is protected with two-factor authentication.",
            })
          : t("home.securityCard.body", {
              defaultValue: "Add two-factor authentication to protect your research data.",
            })}
      </p>
      <div className="account-card__foot">
        <Link className="btn btn-ghost btn-sm" to="/account/security">
          {totpEnabled
            ? t("home.securityCard.manageCta", { defaultValue: "Manage security →" })
            : t("home.securityCard.enableCta", { defaultValue: "Enable 2FA →" })}
        </Link>
      </div>
    </div>
  );

  const slackCard = SLACK_INTEGRATION_ENABLED ? (
    <div key="slack" className="account-card">
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
      <p className="account-card__hint">
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
  ) : null;

  // Unverified: the email action card leads. Verified: the slim email card
  // drops to the second row next to the equally-slim security card, so tall
  // cards pair with tall and the grid stays balanced.
  const cards = verified
    ? [planCard, workspaceCard, securityCard, emailCard, slackCard]
    : [emailCard, planCard, workspaceCard, securityCard, slackCard];

  return (
    <div className="settings-section">
      <div className="account-home-grid">{cards}</div>
    </div>
  );
}
