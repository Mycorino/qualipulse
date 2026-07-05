import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import { useToast } from "../../components/Toast";
import { useAccount } from "./accountContext";

export default function AccountBilling() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const { billing, plans, packs } = useAccount();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [buyingPackId, setBuyingPackId] = useState<string | null>(null);
  const [upgradingPlanId, setUpgradingPlanId] = useState<string | null>(null);
  const [portalBusy, setPortalBusy] = useState(false);

  // Returning from Stripe Checkout — confirm the outcome, then clean the URL
  // so a refresh doesn't repeat the toast.
  useEffect(() => {
    if (searchParams.get("credits") === "purchased") {
      toast(
        t("billing.creditsPurchased", {
          defaultValue: "Payment received — your credits will appear in a moment.",
        }),
        "success"
      );
    } else if (searchParams.get("upgraded") === "true") {
      toast(
        t("billing.upgradeSuccess", { defaultValue: "Your plan has been upgraded. Welcome aboard!" }),
        "success"
      );
    } else {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("credits");
    next.delete("upgraded");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function checkoutError() {
    toast(
      t("billing.checkoutError", {
        defaultValue: "Could not open checkout — please try again or contact support.",
      }),
      "error"
    );
  }

  async function handleBuyPack(packId: string) {
    setBuyingPackId(packId);
    try {
      const { data } = await client.post("/billing/checkout/credits", {
        pack_id: packId,
        success_url: window.location.origin + "/account/billing?credits=purchased",
        cancel_url: window.location.origin + "/account/billing",
      });
      window.location.href = data.checkout_url;
    } catch {
      setBuyingPackId(null);
      checkoutError();
    }
  }

  async function handleUpgrade(planId: string) {
    setUpgradingPlanId(planId);
    try {
      const { data } = await client.post("/billing/checkout", {
        plan_id: planId,
        billing_interval: "monthly",
        success_url: window.location.origin + "/account/billing?upgraded=true",
        cancel_url: window.location.origin + "/account/billing",
      });
      window.location.href = data.checkout_url;
    } catch {
      setUpgradingPlanId(null);
      checkoutError();
    }
  }

  async function handleManageBilling() {
    setPortalBusy(true);
    try {
      const { data } = await client.post("/billing/portal", { return_url: window.location.href });
      window.location.href = data.portal_url;
    } catch {
      setPortalBusy(false);
      checkoutError();
    }
  }

  return (
    <div className="settings-section">
      {/* Credits-aware usage card. Only for non-legacy plans with a balance. */}
      {billing?.plan && !billing.plan.is_legacy && billing.credits && (
        <div className="settings-card">
          <h2 className="settings-section-title">
            {t("billing.usageThisPeriod", { defaultValue: "Usage this period" })}
          </h2>
          <div className="billing-current-plan">
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
              <span className={`plan-badge plan-badge--${billing.plan.id}`}>
                {billing.display?.plan_name ?? billing.plan.name}
              </span>
              {/* Canonical status — a (non-time-based) trial reads "Free trial"
                  rather than the internal "trialing", and no expiry shows. */}
              <span className="billing-status-badge">
                {billing.display?.is_trial
                  ? t("billing.freeTrial", { defaultValue: "Free trial" })
                  : billing.display?.status ?? billing.plan.subscription_status}
              </span>
              {billing.display?.show_trial_end && billing.plan.trial_end && (
                <span className="muted-text" style={{ fontSize: 13 }}>
                  {t("billing.trialEndsOn", { defaultValue: "Trial ends" })}{" "}
                  {new Date(billing.plan.trial_end).toLocaleDateString(i18n.language)}
                </span>
              )}
            </div>
            {billing.display?.is_trial && (
              <p className="muted-text" style={{ fontSize: 13, marginTop: 8 }}>
                {t("billing.trialCreditsHint", {
                  defaultValue: "Your free interview credits don't expire. No credit card required.",
                })}
              </p>
            )}
            <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
              <div className="billing-credit-stat">
                <div style={{ fontSize: 28, fontWeight: 700 }}>{billing.credits.available_credits}</div>
                <div className="muted-text" style={{ fontSize: 13 }}>
                  {t("billing.creditsRemaining", { defaultValue: "Credits remaining" })}
                </div>
              </div>
              <div className="billing-credit-stat">
                <div style={{ fontSize: 22, fontWeight: 600 }}>
                  {billing.credits.used_credits} /{" "}
                  {billing.credits.included_credits + billing.credits.purchased_credits + billing.credits.rollover_credits}
                </div>
                <div className="muted-text" style={{ fontSize: 13 }}>
                  {t("billing.creditsUsed", { defaultValue: "Credits used" })}
                </div>
              </div>
              {billing.credits.overage_credits > 0 && (
                <div className="billing-credit-stat">
                  <div style={{ fontSize: 22, fontWeight: 600, color: "var(--warning-text)" }}>
                    {billing.credits.overage_credits}
                  </div>
                  <div className="muted-text" style={{ fontSize: 13 }}>
                    {t("billing.overageCredits", { defaultValue: "Overage" })}
                  </div>
                </div>
              )}
            </div>
            {billing.credits.period_end && (
              <div className="muted-text" style={{ fontSize: 12, marginTop: 12 }}>
                {t("billing.periodEndsOn", { defaultValue: "Period ends" })}{" "}
                {new Date(billing.credits.period_end).toLocaleDateString(i18n.language)}
                {billing.plan.cancel_at_period_end && (
                  <> · {t("billing.cancelAtPeriodEnd", { defaultValue: "subscription will cancel at period end" })}</>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Credit packs — non-legacy plans only. */}
      {billing?.plan && !billing.plan.is_legacy && packs.length > 0 && (
        <div className="settings-card" style={{ marginTop: 20 }}>
          <h2 className="settings-section-title">{t("billing.packsTitle", { defaultValue: "Buy extra credits" })}</h2>
          <p className="muted-text" style={{ fontSize: 14, marginTop: -4, marginBottom: 16 }}>
            {t("billing.packsSubtitle", { defaultValue: "One-off top-ups. Purchased credits roll over until used." })}
          </p>
          <div className="plans-grid">
            {packs.map((pack) => {
              const priceEur = (pack.price_cents / 100).toFixed(0);
              const perCredit = (pack.price_cents / pack.credits / 100).toFixed(2);
              const isBuying = buyingPackId === pack.id;
              return (
                <div key={pack.id} className="plan-card">
                  <div className="plan-card-header">
                    <h3 className="plan-name">{t("billing.packName", { count: pack.credits })}</h3>
                    <p className="plan-price">€{priceEur}</p>
                  </div>
                  <ul className="plan-features">
                    <li>
                      <strong>{pack.credits}</strong> {t("billing.creditsLabel", { defaultValue: "credits" })}
                    </li>
                    <li className="muted-text">
                      {t("billing.perCreditPrice", { defaultValue: "€{{price}} per credit", price: perCredit })}
                    </li>
                  </ul>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={!pack.available || isBuying}
                    onClick={() => handleBuyPack(pack.id)}
                  >
                    {isBuying
                      ? t("common:loading", { defaultValue: "Loading…" })
                      : !pack.available
                      ? t("billing.packUnavailable", { defaultValue: "Unavailable" })
                      : t("billing.buyPack", { defaultValue: "Buy pack" })}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {billing && (
        <div className="settings-card" style={{ marginTop: 20 }}>
          <h2 className="settings-section-title">{t("billing.currentPlan")}</h2>
          <div className="billing-current-plan">
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
              <span className={`plan-badge plan-badge--${billing.tier}`}>
                {billing.display?.plan_name ?? billing.tier_name}
              </span>
              <span className="billing-status-badge">
                {billing.display?.is_trial
                  ? t("billing.freeTrial", { defaultValue: "Free trial" })
                  : billing.display?.status ?? billing.status}
              </span>
            </div>
            <div className="billing-limits">
              <div className="billing-limit-row">
                <span>{t("billing.limits.projects")}</span>
                <span>{billing.limits.max_projects === -1 ? t("common:unlimited") : billing.limits.max_projects}</span>
              </div>
              <div className="billing-limit-row">
                <span>{t("billing.limits.participants")}</span>
                <span>{billing.limits.max_participants_per_project === -1 ? t("common:unlimited") : billing.limits.max_participants_per_project}</span>
              </div>
              <div className="billing-limit-row">
                <span>{t("billing.limits.aiAnalysis")}</span>
                <span style={{ color: billing.limits.ai_analysis ? "var(--success)" : "var(--text-tertiary)" }}>
                  {billing.limits.ai_analysis ? t("billing.limits.included") : t("billing.limits.upgrade")}
                </span>
              </div>
              <div className="billing-limit-row">
                <span>{t("billing.limits.csvExport")}</span>
                <span style={{ color: billing.limits.export_csv ? "var(--success)" : "var(--text-tertiary)" }}>
                  {billing.limits.export_csv ? t("billing.limits.included") : t("billing.limits.upgrade")}
                </span>
              </div>
              <div className="billing-limit-row">
                <span>{t("billing.limits.teamMembers")}</span>
                <span>{billing.limits.team_members === -1 ? t("common:unlimited") : billing.limits.team_members}</span>
              </div>
            </div>
            {billing.tier !== "starter" && billing.tier !== "free" && billing.tier !== "solo" && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleManageBilling}
                disabled={portalBusy}
                style={{ marginTop: 16 }}
              >
                {portalBusy ? t("common:loading", { defaultValue: "Loading…" }) : t("billing.manageBilling")}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="settings-card" style={{ marginTop: 20 }}>
        <h2 className="settings-section-title">{t("billing.upgradePlan")}</h2>
        <div className="plans-grid">
          {plans.map((plan) => {
            const currentPlanId = billing?.plan?.id;
            const isCurrent = currentPlanId === plan.id;
            const priceMonthly = plan.monthly_price_cents ? Math.round(plan.monthly_price_cents / 100) : null;
            return (
              <div key={plan.id} className={`plan-card ${isCurrent ? "plan-card--current" : ""}`}>
                <div className="plan-card-header">
                  <h3 className="plan-name">{plan.name}</h3>
                  <p className="plan-price">
                    {plan.is_custom
                      ? t("common:custom")
                      : priceMonthly != null
                      ? t("billing.priceMonthly", { price: priceMonthly })
                      : ""}
                  </p>
                </div>
                <ul className="plan-features">
                  {plan.included_credits != null && (
                    <li>
                      {t("billing.planFeatures.creditsLine", {
                        count: plan.included_credits,
                        unit:
                          plan.credit_period === "monthly"
                            ? t("billing.planFeatures.perMonthUnit")
                            : plan.credit_period,
                      })}
                    </li>
                  )}
                  <li>
                    {plan.max_active_projects == null
                      ? t("billing.planFeatures.projectsUnlimited")
                      : t("billing.planFeatures.projects", { count: plan.max_active_projects })}
                  </li>
                  <li>
                    {plan.max_editors == null
                      ? t("billing.planFeatures.editorsUnlimited")
                      : t("billing.planFeatures.editors", { count: plan.max_editors })}
                  </li>
                  {Boolean(plan.entitlements?.csv_export) && <li>{t("billing.planFeatures.csvExport")}</li>}
                  {Boolean(plan.entitlements?.custom_branding) && <li>{t("billing.planFeatures.customBranding")}</li>}
                  {Boolean(plan.entitlements?.team_workspace) && <li>{t("billing.planFeatures.teamWorkspace")}</li>}
                  {plan.overage_price_cents != null && (
                    <li>
                      {t("billing.planFeatures.overage", {
                        price: (plan.overage_price_cents / 100).toFixed(0),
                      })}
                    </li>
                  )}
                </ul>
                {isCurrent ? (
                  <button className="btn btn-ghost btn-sm" disabled>{t("common:active")}</button>
                ) : plan.is_custom ? (
                  <a href="mailto:hello@qualipulse.com" className="btn btn-ghost btn-sm">{t("billing.contactUs")}</a>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={upgradingPlanId !== null}
                    onClick={() => handleUpgrade(plan.id)}
                  >
                    {upgradingPlanId === plan.id
                      ? t("common:loading", { defaultValue: "Loading…" })
                      : t("billing.upgradeToLabel", { name: plan.name })}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
