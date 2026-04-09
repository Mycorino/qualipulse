import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../api/client";
import LanguageSwitcher from "../components/LanguageSwitcher";

interface BillingStatus {
  tier: string;
  tier_name: string;
  status: string;
  limits: {
    max_projects: number;
    max_participants_per_project: number;
    ai_analysis: boolean;
    export_csv: boolean;
    team_members: number;
  };
  usage: {
    interview_count: number;
    storage_bytes: number;
  };
}

interface Plan {
  id: string;
  name: string;
  price_monthly_usd: number;
  max_projects: number;
  max_participants_per_project: number;
  ai_analysis: boolean;
  export_csv: boolean;
  team_members: number;
}

export default function AccountSettings() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const navigate = useNavigate();
  const [me, setMe] = useState<{ name: string; email: string; preferred_language?: string } | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"profile" | "billing">("profile");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [name, setName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  useEffect(() => {
    Promise.all([
      client.get("/auth/me").then(r => r.data),
      client.get("/billing/status").then(r => r.data).catch(() => null),
      client.get("/billing/plans").then(r => r.data).catch(() => []),
    ]).then(([meData, billingData, plansData]) => {
      setMe(meData);
      setName(meData.name);
      setBilling(billingData);
      setPlans(plansData);
      // Sync UI language with user's stored preference
      if (meData.preferred_language && meData.preferred_language !== i18n.language?.slice(0, 2)) {
        i18n.changeLanguage(meData.preferred_language);
      }
    }).finally(() => setLoading(false));
  }, []);

  async function handleUpgrade(tierId: string) {
    try {
      const { data } = await client.post("/billing/checkout", {
        tier: tierId,
        success_url: window.location.origin + "/account?upgraded=true",
        cancel_url: window.location.origin + "/account",
      });
      window.location.href = data.checkout_url;
    } catch {
      alert(t("common:contactSupport"));
    }
  }

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    setProfileSuccess(false);
    try {
      await client.patch("/auth/me", {
        name: name.trim(),
        preferred_language: i18n.language?.startsWith("fr") ? "fr" : "en",
      });
      setProfileSuccess(true);
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch {
      // silently fail for now
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordError("");
    setPasswordSuccess(false);
    if (newPassword.length < 8) { setPasswordError(t("profile.passwordError")); return; }
    try {
      await client.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setTimeout(() => setPasswordSuccess(false), 3000);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPasswordError(msg ?? t("profile.passwordError"));
    }
  }

  async function handleManageBilling() {
    try {
      const { data } = await client.post("/billing/portal", {
        return_url: window.location.href,
      });
      window.location.href = data.portal_url;
    } catch {
      alert(t("common:contactSupport"));
    }
  }

  if (loading) return <div className="dashboard-page"><p className="muted-text">{t("common:loading")}</p></div>;

  return (
    <div className="dashboard-page">
      <div style={{ maxWidth: "960px", margin: "0 auto" }}>
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">{t("title")}</h1>
          <p className="dashboard-subtitle">{me?.email}</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <LanguageSwitcher />
          <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>← {t("common:dashboard")}</button>
        </div>
      </div>

      <div className="settings-tabs">
        <button className={`settings-tab ${tab === "profile" ? "active" : ""}`} onClick={() => setTab("profile")}>{t("tabs.profile")}</button>
        <button className={`settings-tab ${tab === "billing" ? "active" : ""}`} onClick={() => setTab("billing")}>{t("tabs.billing")}</button>
      </div>

      {tab === "profile" && (
        <div className="settings-section">
          <div className="settings-card">
            <h2 className="settings-section-title">{t("profile.title")}</h2>
            <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleSaveProfile}>
              <div>
                <label className="field-label">{t("profile.nameLabel")}</label>
                <input className="field-input" value={name} onChange={e => setName(e.target.value)} required />
              </div>
              <div>
                <label className="field-label">{t("profile.emailLabel")}</label>
                <input className="field-input" value={me?.email ?? ""} disabled style={{ opacity: 0.6 }} />
              </div>
              <p style={{ color: "var(--success)", fontSize: 14, minHeight: 20, visibility: profileSuccess ? "visible" : "hidden" }}>{t("profile.saved")}</p>
              <button className="btn btn-primary" type="submit" disabled={savingProfile} style={{ width: "fit-content" }}>
                {savingProfile ? t("profile.saving") : t("profile.saveChanges")}
              </button>
            </form>
          </div>

          <div className="settings-card" style={{ marginTop: 20 }}>
            <h2 className="settings-section-title">{t("profile.changePassword")}</h2>
            <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleChangePassword}>
              <div>
                <label className="field-label">{t("profile.currentPasswordLabel")}</label>
                <input type="password" className="field-input" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required />
              </div>
              <div>
                <label className="field-label">{t("profile.newPasswordLabel")}</label>
                <input type="password" className="field-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder={t("profile.newPasswordPlaceholder")} required minLength={8} />
              </div>
              {passwordError && <p className="error-text">{passwordError}</p>}
              <p style={{ color: "var(--success)", fontSize: 14, minHeight: 20, visibility: passwordSuccess ? "visible" : "hidden" }}>{t("profile.passwordUpdated")}</p>
              <button className="btn btn-primary" type="submit" style={{ width: "fit-content" }}>{t("profile.updatePassword")}</button>
            </form>
          </div>
        </div>
      )}

      {tab === "billing" && (
        <div className="settings-section">
          {billing && (
            <div className="settings-card">
              <h2 className="settings-section-title">{t("billing.currentPlan")}</h2>
              <div className="billing-current-plan">
                <div>
                  <span className={`plan-badge plan-badge--${billing.tier}`}>{billing.tier_name}</span>
                  <span
                    className="billing-status-badge"
                    style={{
                      marginLeft: 8,
                      ...(billing.status === "trialing" ? {
                        background: "var(--brand-50)",
                        color: "var(--brand-500)",
                      } : {}),
                    }}
                  >{billing.status}</span>
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
                  <button className="btn btn-ghost btn-sm" onClick={handleManageBilling} style={{ marginTop: 16 }}>
                    {t("billing.manageBilling")}
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="settings-card" style={{ marginTop: 20 }}>
            <h2 className="settings-section-title">{t("billing.upgradePlan")}</h2>
            <div className="plans-grid">
              {plans.map(plan => {
                const effectiveTier = billing?.tier === "free" ? "starter" : billing?.tier === "solo" ? "starter" : billing?.tier === "pro" ? "lab" : billing?.tier;
                const isCurrent = effectiveTier === plan.id;
                return (
                <div key={plan.id} className={`plan-card ${isCurrent ? "plan-card--current" : ""}`}>
                  <div className="plan-card-header">
                    <h3 className="plan-name">{plan.name}</h3>
                    <p className="plan-price">
                      {plan.price_monthly_usd === 0 ? t("common:custom") : `€${plan.price_monthly_usd}/mo`}
                    </p>
                  </div>
                  <ul className="plan-features">
                    <li>{plan.max_projects === -1 ? t("common:unlimited") + " projects" : `${plan.max_projects} projects`}</li>
                    <li>{plan.max_participants_per_project === -1 ? t("common:unlimited") + " participants" : `${plan.max_participants_per_project} participants/project`}</li>
                    <li>{plan.ai_analysis ? "✓ AI analysis" : "✗ AI analysis"}</li>
                    <li>{plan.export_csv ? "✓ CSV export" : "✗ CSV export"}</li>
                    <li>{plan.team_members === -1 ? t("common:unlimited") + " team members" : `${plan.team_members} team members`}</li>
                  </ul>
                  {isCurrent ? (
                    <button className="btn btn-ghost btn-sm" disabled>{t("common:active")}</button>
                  ) : plan.id === "enterprise" ? (
                    <a href="mailto:hello@qualipulse.com" className="btn btn-ghost btn-sm">{t("billing.contactUs")}</a>
                  ) : (
                    <button className="btn btn-primary btn-sm" onClick={() => handleUpgrade(plan.id)}>
                      {t("billing.upgradeToLabel", { name: plan.name })}
                    </button>
                  )}
                </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
