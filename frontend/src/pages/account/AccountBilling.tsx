import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import client from "../../api/client";
import { useToast } from "../../components/Toast";
import { useAccount, type Plan } from "./accountContext";

type Interval = "monthly" | "annual";

export default function AccountBilling() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const { billing, plans, packs } = useAccount();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [buyingPackId, setBuyingPackId] = useState<string | null>(null);
  const [upgradingPlanId, setUpgradingPlanId] = useState<string | null>(null);
  const [portalBusy, setPortalBusy] = useState(false);
  // Annual is the default: it's the higher-value commitment and the −17%
  // framing does the persuading. Users who want monthly flip one toggle.
  const [interval, setInterval] = useState<Interval>("annual");

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

  // Who is this page for? A trial / legacy / un-provisioned account is here to
  // CONVERT — lead with subscription plans. An active paid credit-plan account
  // is here to OPERATE — lead with usage + top-ups, plans become "change plan".
  const plan = billing?.plan;
  const isTrial = billing?.display?.is_trial === true || plan?.is_trial === true;
  const onPaidPlan = Boolean(plan && !plan.is_legacy && !isTrial);
  const conversionMode = !onPaidPlan;

  const credits = billing?.credits;
  const includedTotal = credits
    ? credits.included_credits + credits.purchased_credits + credits.rollover_credits
    : 0;

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

  async function handleUpgrade(planId: string, billingInterval: Interval) {
    setUpgradingPlanId(planId);
    try {
      const { data } = await client.post("/billing/checkout", {
        plan_id: planId,
        billing_interval: billingInterval,
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

  // ── Plan chooser (the hero for conversion, "change plan" for paid) ──────────
  const planChooser = (
    <div className="settings-card billing-chooser">
      <div className="billing-chooser__head">
        <div>
          <h2 className="settings-section-title" style={{ marginBottom: 4 }}>
            {conversionMode
              ? t("billing.chooseTitle", { defaultValue: "Choose your plan" })
              : t("billing.changeTitle", { defaultValue: "Change plan" })}
          </h2>
          <p className="muted-text" style={{ fontSize: 14, margin: 0 }}>
            {t("billing.chooseSubtitle", {
              defaultValue: "One credit = one completed interview. Included credits refresh every period; overage is billed per credit.",
            })}
          </p>
        </div>
        <div className="billing-toggle" role="group" aria-label={t("billing.billingToggleLabel", { defaultValue: "Billing period" })}>
          <button
            type="button"
            aria-pressed={interval === "monthly"}
            className={interval === "monthly" ? "active" : ""}
            onClick={() => setInterval("monthly")}
          >
            {t("billing.billingMonthly", { defaultValue: "Monthly" })}
          </button>
          <button
            type="button"
            aria-pressed={interval === "annual"}
            className={interval === "annual" ? "active" : ""}
            onClick={() => setInterval("annual")}
          >
            {t("billing.billingAnnual", { defaultValue: "Annual" })}{" "}
            <span className="billing-toggle__save">{t("billing.billingAnnualSave", { defaultValue: "−17%" })}</span>
          </button>
        </div>
      </div>

      <div className="plans-grid billing-plans-grid">
        {plans.map((p) => (
          <PlanCard
            key={p.id}
            plan={p}
            interval={interval}
            isCurrent={billing?.plan?.id === p.id}
            recommended={p.id === "team"}
            busy={upgradingPlanId !== null}
            loadingThis={upgradingPlanId === p.id}
            onChoose={() => handleUpgrade(p.id, interval)}
            t={t}
          />
        ))}
      </div>

      <p className="billing-reassurance">
        {t("billing.reassurance", {
          defaultValue: "Cancel anytime · Purchased & rolled-over credits never expire · Secure checkout via Stripe",
        })}
      </p>
    </div>
  );

  // ── Usage card (shown for credit-based accounts: trial + paid) ──────────────
  const usageCard = plan && !plan.is_legacy && credits && (
    <div className="settings-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <h2 className="settings-section-title" style={{ marginBottom: 0 }}>
          {t("billing.usageThisPeriod", { defaultValue: "Usage this period" })}
        </h2>
        {onPaidPlan && (
          <button className="btn btn-ghost btn-sm" onClick={handleManageBilling} disabled={portalBusy}>
            {portalBusy ? t("common:loading", { defaultValue: "Loading…" }) : t("billing.manageBilling")}
          </button>
        )}
      </div>
      <div className="billing-current-plan">
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginTop: 4 }}>
          <span className={`plan-badge plan-badge--${plan.id}`}>
            {billing.display?.plan_name ?? plan.name}
          </span>
          <span className="billing-status-badge">
            {isTrial
              ? t("billing.freeTrial", { defaultValue: "Free trial" })
              : billing.display?.status ?? plan.subscription_status}
          </span>
          {billing.display?.show_trial_end && plan.trial_end && (
            <span className="muted-text" style={{ fontSize: 13 }}>
              {t("billing.trialEndsOn", { defaultValue: "Trial ends" })}{" "}
              {new Date(plan.trial_end).toLocaleDateString(i18n.language)}
            </span>
          )}
        </div>
        {isTrial && (
          <p className="muted-text" style={{ fontSize: 13, marginTop: 8 }}>
            {t("billing.trialCreditsHint", {
              defaultValue: "Your free interview credits don't expire. No credit card required.",
            })}
          </p>
        )}
        <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          <div className="billing-credit-stat">
            <div style={{ fontSize: 28, fontWeight: 700 }}>{credits.available_credits}</div>
            <div className="muted-text" style={{ fontSize: 13 }}>
              {t("billing.creditsRemaining", { defaultValue: "Credits remaining" })}
            </div>
          </div>
          <div className="billing-credit-stat">
            <div style={{ fontSize: 22, fontWeight: 600 }}>
              {credits.used_credits} / {includedTotal}
            </div>
            <div className="muted-text" style={{ fontSize: 13 }}>
              {t("billing.creditsUsed", { defaultValue: "Credits used" })}
            </div>
          </div>
          {credits.overage_credits > 0 && (
            <div className="billing-credit-stat">
              <div style={{ fontSize: 22, fontWeight: 600, color: "var(--warning-text)" }}>
                {credits.overage_credits}
              </div>
              <div className="muted-text" style={{ fontSize: 13 }}>
                {t("billing.overageCredits", { defaultValue: "Overage" })}
              </div>
            </div>
          )}
        </div>
        {credits.period_end && !isTrial && (
          <div className="muted-text" style={{ fontSize: 12, marginTop: 12 }}>
            {t("billing.periodEndsOn", { defaultValue: "Period ends" })}{" "}
            {new Date(credits.period_end).toLocaleDateString(i18n.language)}
            {plan.cancel_at_period_end && (
              <> · {t("billing.cancelAtPeriodEnd", { defaultValue: "subscription will cancel at period end" })}</>
            )}
          </div>
        )}
      </div>
    </div>
  );

  // ── Credit packs. Demoted to a collapsed <details> in conversion mode
  //    (top-ups are for people who already have a plan), open for paid users. ──
  const packsCard = plan && !plan.is_legacy && packs.length > 0 && (
    <details className="settings-card billing-packs" open={onPaidPlan}>
      <summary className="billing-packs__summary">
        <span className="settings-section-title" style={{ margin: 0 }}>
          {conversionMode
            ? t("billing.packsSecondaryTitle", { defaultValue: "Prefer to pay as you go?" })
            : t("billing.packsTitle", { defaultValue: "Buy extra credits" })}
        </span>
        <span className="muted-text" style={{ fontSize: 13 }}>
          {t("billing.packsSubtitle", { defaultValue: "One-off top-ups. Purchased credits roll over until used." })}
        </span>
      </summary>
      <div className="plans-grid" style={{ marginTop: 16 }}>
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
                className="btn btn-ghost btn-sm"
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
    </details>
  );

  // ── Legacy-tier fallback: limits table for accounts with no credit plan. ────
  const legacyCard = billing && (!plan || plan.is_legacy) && (
    <div className="settings-card">
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
          <button className="btn btn-ghost btn-sm" onClick={handleManageBilling} disabled={portalBusy} style={{ marginTop: 16 }}>
            {portalBusy ? t("common:loading", { defaultValue: "Loading…" }) : t("billing.manageBilling")}
          </button>
        )}
      </div>
    </div>
  );

  // Conversion mode → plans first. Paid mode → usage + packs first, then plans.
  return (
    <div className="settings-section" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {conversionMode ? (
        <>
          {planChooser}
          {usageCard}
          {packsCard}
          {legacyCard}
        </>
      ) : (
        <>
          {usageCard}
          {packsCard}
          {planChooser}
        </>
      )}
    </div>
  );
}

// ── Single plan card ──────────────────────────────────────────────────────────
function PlanCard({
  plan,
  interval,
  isCurrent,
  recommended,
  busy,
  loadingThis,
  onChoose,
  t,
}: {
  plan: Plan;
  interval: Interval;
  isCurrent: boolean;
  recommended: boolean;
  busy: boolean;
  loadingThis: boolean;
  onChoose: () => void;
  t: TFunction<["settings", "common"]>;
}) {
  const price = useMemo(() => {
    if (plan.is_custom || plan.monthly_price_cents == null) return null;
    const monthly = Math.round(plan.monthly_price_cents / 100);
    const annual = plan.annual_price_cents != null ? Math.round(plan.annual_price_cents / 100) : null;
    const useAnnual = interval === "annual" && annual != null;
    return { perMonth: useAnnual ? Math.floor(annual / 12) : monthly, annual, useAnnual };
  }, [plan, interval]);

  const ent = (plan.entitlements ?? {}) as Record<string, unknown>;

  return (
    <div
      className={
        "plan-card" +
        (isCurrent ? " plan-card--current" : "") +
        (recommended && !isCurrent ? " plan-card--recommended" : "")
      }
    >
      {recommended && !isCurrent && (
        <span className="plan-flag">{t("billing.recommended", { defaultValue: "Most popular" })}</span>
      )}
      {isCurrent && (
        <span className="plan-flag plan-flag--current">{t("common:active", { defaultValue: "Active" })}</span>
      )}

      <div className="plan-card-header">
        <h3 className="plan-name">{plan.name}</h3>
        {plan.is_custom ? (
          <p className="plan-price">{t("common:custom", { defaultValue: "Custom" })}</p>
        ) : price ? (
          <>
            <p className="plan-price">
              €{price.perMonth}
              <span className="plan-price__unit">{t("billing.perMonthUnit", { defaultValue: "/mo" })}</span>
            </p>
            <p className="plan-price__sub">
              {price.useAnnual && price.annual != null
                ? t("billing.billedAnnually", { defaultValue: "€{{price}} billed annually", price: price.annual })
                : t("billing.billedMonthly", { defaultValue: "billed monthly" })}
            </p>
          </>
        ) : null}
      </div>

      <ul className="plan-features">
        {plan.included_credits != null && (
          <li>
            <strong>
              {t("billing.planFeatures.creditsLine", {
                count: plan.included_credits,
                unit:
                  plan.credit_period === "monthly"
                    ? t("billing.planFeatures.perMonthUnit", { defaultValue: "mo" })
                    : plan.credit_period,
              })}
            </strong>
          </li>
        )}
        <li>
          {plan.max_editors == null
            ? t("billing.planFeatures.editorsUnlimited", { defaultValue: "Unlimited editors" })
            : t("billing.planFeatures.editors", { count: plan.max_editors })}
        </li>
        {Boolean(ent.csv_export) && <li>{t("billing.planFeatures.csvExport", { defaultValue: "CSV export" })}</li>}
        {Boolean(ent.custom_branding) && <li>{t("billing.planFeatures.customBranding", { defaultValue: "Custom branding" })}</li>}
        {Boolean(ent.team_workspace) && <li>{t("billing.planFeatures.teamWorkspace", { defaultValue: "Team workspace" })}</li>}
        {plan.overage_price_cents != null && (
          <li className="muted-text">
            {t("billing.planFeatures.overage", { price: (plan.overage_price_cents / 100).toFixed(0) })}
          </li>
        )}
      </ul>

      {isCurrent ? (
        <button className="btn btn-ghost btn-sm" disabled>
          {t("common:active", { defaultValue: "Active" })}
        </button>
      ) : plan.is_custom ? (
        <a href="mailto:hello@qualipulse.com" className="btn btn-ghost btn-sm">
          {t("billing.contactUs")}
        </a>
      ) : (
        <button
          className={"btn btn-sm " + (recommended ? "btn-primary" : "btn-secondary")}
          disabled={busy}
          onClick={onChoose}
        >
          {loadingThis
            ? t("common:loading", { defaultValue: "Loading…" })
            : t("billing.choosePlan", { defaultValue: "Choose {{name}}", name: plan.name })}
        </button>
      )}
    </div>
  );
}
