import { useState, useEffect, useCallback } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";
import type { CompanyResponse } from "../../api/auth";
import LanguageSwitcher from "../../components/LanguageSwitcher";
import { HubShell } from "../../components/HubShell";
import {
  BillingStatus,
  Plan,
  CreditPack,
  AccountOutletContext,
  SLACK_INTEGRATION_ENABLED,
} from "./accountContext";

/**
 * Account shell — fetches the data every sub-route needs once, renders a
 * compact identity header + section nav, and exposes the data to children
 * through the Outlet context. Replaces the old single 930-line tabbed
 * AccountSettings page; sections now live at real sub-routes
 * (/account, /account/profile, /account/security, /account/workspace,
 * /account/integrations, /account/billing).
 */
export default function AccountLayout() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [packs, setPacks] = useState<CreditPack[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      client.get("/auth/me").then((r) => r.data).catch(() => null),
      client.get("/billing/status").then((r) => r.data).catch(() => null),
      client.get("/billing/plans").then((r) => r.data).catch(() => []),
      client.get("/billing/credit-packs").then((r) => r.data).catch(() => []),
    ])
      .then(([meData, billingData, plansData, packsData]) => {
        // /auth/me is essential — without it every section renders empty.
        // Billing endpoints are optional (legacy accounts may lack data).
        if (!meData) {
          setLoadError(true);
          return;
        }
        setMe(meData);
        // Sync UI language with the user's stored preference.
        if (
          meData.preferred_language &&
          meData.preferred_language !== i18n.language?.slice(0, 2)
        ) {
          i18n.changeLanguage(meData.preferred_language);
          localStorage.setItem("qp_language", meData.preferred_language);
        }
        setBilling(billingData);
        setPlans(plansData);
        setPacks(packsData);
      })
      .catch((err) => {
        console.error("Account data load failed:", err);
        setLoadError(true);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <HubShell active="account">
        <div className="dashboard-page">
          <p className="muted-text">{t("common:loading")}</p>
        </div>
      </HubShell>
    );
  }

  if (loadError) {
    return (
      <HubShell active="account">
      <div className="dashboard-page">
        <div style={{ maxWidth: 480, margin: "var(--space-16) auto", textAlign: "center" }}>
          <h2 style={{ marginBottom: "var(--space-4)" }}>
            {t("settings:loadErrorTitle", { defaultValue: "Unable to load account settings" })}
          </h2>
          <p className="muted-text" style={{ marginBottom: "var(--space-6)" }}>
            {t("settings:loadErrorMessage", {
              defaultValue:
                "Something went wrong while loading your account data. Please try again.",
            })}
          </p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            {t("common:retry", { defaultValue: "Retry" })}
          </button>
        </div>
      </div>
      </HubShell>
    );
  }

  // Plan badge — prefer the canonical credit-native display block; a
  // non-time-based trial reads "Free trial" with no countdown.
  let badgeClass = "eyebrow-tag eyebrow-tag--info";
  let badgeText: string = billing?.tier_name ?? billing?.tier ?? "";
  if (billing?.display) {
    if (billing.display.is_trial) {
      badgeText = t("billing.freeTrial", { defaultValue: "Free trial" });
    } else {
      badgeText = billing.display.plan_name;
      badgeClass =
        billing.display.status === "active"
          ? "eyebrow-tag eyebrow-tag--success"
          : "eyebrow-tag eyebrow-tag--warning";
    }
  } else if (billing?.status === "active") {
    badgeClass = "eyebrow-tag eyebrow-tag--success";
  }

  const cleanedName = (me?.name || me?.email || "").replace(/\[.*?\]/g, "").trim();
  const initials =
    cleanedName
      .split(/\s+/)
      .map((p) => p.charAt(0))
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?";

  const sections: { to: string; label: string; end?: boolean }[] = [
    { to: "/account", label: t("nav.home", { defaultValue: "Account home" }), end: true },
    { to: "/account/profile", label: t("nav.profile", { defaultValue: "Profile" }) },
    { to: "/account/security", label: t("nav.security", { defaultValue: "Security" }) },
    { to: "/account/workspace", label: t("nav.workspace", { defaultValue: "Workspace" }) },
    ...(SLACK_INTEGRATION_ENABLED
      ? [{ to: "/account/integrations", label: t("nav.integrations", { defaultValue: "Integrations" }) }]
      : []),
    { to: "/account/billing", label: t("nav.billing", { defaultValue: "Billing" }) },
  ];

  const ctx: AccountOutletContext = { me, setMe, billing, plans, packs, reload: load };

  return (
    <HubShell active="account">
    <div className="dashboard-page">
      <div style={{ maxWidth: "960px", margin: "0 auto" }}>
        {/* Compact identity row — the HubShell rail carries the wordmark,
            nav and account menu; this row keeps who-am-I + plan badge and
            the language toggle. Detailed account state lives in the
            Account Home status cards. */}
        <section className="account-identity" aria-label={t("hubHeader.aria", "Account overview")}>
          <div className="account-identity__avatar" aria-hidden="true">{initials}</div>
          <div className="account-identity__text">
            <h1 className="account-identity__name">{me?.name || t("title")}</h1>
            <p className="account-identity__email">{me?.email}</p>
          </div>
          {billing && (
            <Link
              className={badgeClass}
              to="/account/billing"
              style={{ textDecoration: "none" }}
              aria-label={t("hubHeader.planBadgeAria", {
                defaultValue: "Current plan — open billing",
              })}
            >
              {badgeText}
            </Link>
          )}
          <span style={{ marginLeft: "auto" }}>
            <LanguageSwitcher variant="light" />
          </span>
        </section>

        <nav className="settings-tabs" aria-label={t("nav.aria", { defaultValue: "Account sections" })}>
          {sections.map((s) => (
            <NavLink
              key={s.to}
              to={s.to}
              end={s.end}
              className={({ isActive }) => `settings-tab ${isActive ? "active" : ""}`}
            >
              {s.label}
            </NavLink>
          ))}
        </nav>

        <Outlet context={ctx} />
      </div>
    </div>
    </HubShell>
  );
}
