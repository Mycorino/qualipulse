import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../api/client";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { updateSlackWebhook, testSlackWebhook } from "../api/auth";
import {
  listTeamMembers,
  listTeamInvitations,
  inviteTeamMember,
  revokeTeamInvitation,
  removeTeamMember,
  TeamMember,
  TeamInvitation,
  TeamRole,
} from "../api/team";

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
  const [me, setMe] = useState<{ name: string; email: string; preferred_language?: string; slack_webhook_url?: string | null } | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"profile" | "team" | "integrations" | "billing">("profile");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [name, setName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Slack integration
  const [slackUrl, setSlackUrl] = useState("");
  const [slackSaving, setSlackSaving] = useState(false);
  const [slackTesting, setSlackTesting] = useState(false);
  const [slackMessage, setSlackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Team
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [teamInvites, setTeamInvites] = useState<TeamInvitation[]>([]);
  const [teamLoading, setTeamLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TeamRole>("editor");
  const [inviting, setInviting] = useState(false);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [teamSuccess, setTeamSuccess] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      client.get("/auth/me").then(r => r.data),
      client.get("/billing/status").then(r => r.data).catch(() => null),
      client.get("/billing/plans").then(r => r.data).catch(() => []),
    ]).then(([meData, billingData, plansData]) => {
      setMe(meData);
      setName(meData.name);
      setSlackUrl(meData.slack_webhook_url ?? "");
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

  async function loadTeam() {
    setTeamLoading(true);
    try {
      const [members, invites] = await Promise.all([
        listTeamMembers(),
        listTeamInvitations().catch(() => []),
      ]);
      setTeamMembers(members);
      setTeamInvites(invites);
    } catch {
      // handled by interceptor
    } finally {
      setTeamLoading(false);
    }
  }

  useEffect(() => {
    if (tab === "team" && teamMembers.length === 0 && !teamLoading) {
      loadTeam();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function handleInviteMember(e: React.FormEvent) {
    e.preventDefault();
    setTeamError(null);
    setTeamSuccess(null);
    const email = inviteEmail.trim();
    if (!email) return;
    setInviting(true);
    try {
      const invite = await inviteTeamMember(email, inviteRole);
      setTeamInvites((prev) => [invite, ...prev.filter((p) => p.email !== email)]);
      setInviteEmail("");
      setTeamSuccess(t("team.inviteSent", { email }));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("team.inviteError");
      setTeamError(msg);
    } finally {
      setInviting(false);
    }
  }

  async function handleRevokeInvite(id: string) {
    try {
      await revokeTeamInvitation(id);
      setTeamInvites((prev) => prev.filter((i) => i.id !== id));
    } catch {
      // handled by interceptor
    }
  }

  async function handleRemoveMember(memberRowId: string) {
    if (memberRowId === "owner") return;
    if (!confirm(t("team.removeConfirm"))) return;
    try {
      await removeTeamMember(memberRowId);
      setTeamMembers((prev) => prev.filter((m) => m.id !== memberRowId));
    } catch {
      // handled by interceptor
    }
  }

  async function handleSaveSlack(e: React.FormEvent) {
    e.preventDefault();
    setSlackMessage(null);
    setSlackSaving(true);
    try {
      const trimmed = slackUrl.trim();
      await updateSlackWebhook(trimmed || null);
      setMe((m) => (m ? { ...m, slack_webhook_url: trimmed || null } : m));
      setSlackMessage({
        type: "success",
        text: trimmed ? t("integrations.slack.saved") : t("integrations.slack.cleared"),
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("integrations.slack.saveError");
      setSlackMessage({ type: "error", text: msg });
    } finally {
      setSlackSaving(false);
    }
  }

  async function handleTestSlack() {
    setSlackMessage(null);
    setSlackTesting(true);
    try {
      await testSlackWebhook(slackUrl.trim() || null);
      setSlackMessage({ type: "success", text: t("integrations.slack.testSent") });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("integrations.slack.testFailed");
      setSlackMessage({ type: "error", text: msg });
    } finally {
      setSlackTesting(false);
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
        <button className={`settings-tab ${tab === "team" ? "active" : ""}`} onClick={() => setTab("team")}>{t("tabs.team")}</button>
        <button className={`settings-tab ${tab === "integrations" ? "active" : ""}`} onClick={() => setTab("integrations")}>{t("tabs.integrations")}</button>
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
                <label className="field-label">{t("profile.emailLabel")} <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-tertiary)" }}>({t("profile.emailReadOnly")})</span></label>
                <input className="field-input" value={me?.email ?? ""} disabled style={{ opacity: 0.6, cursor: "not-allowed" }} />
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

      {tab === "team" && (
        <div className="settings-section">
          <div className="settings-card">
            <h2 className="settings-section-title">{t("team.inviteTitle")}</h2>
            <p className="muted-text" style={{ marginTop: -4, marginBottom: 16 }}>
              {t("team.inviteDescription")}
            </p>
            <form
              className="auth-form"
              style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 12 }}
              onSubmit={handleInviteMember}
            >
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input
                  className="field-input"
                  type="email"
                  placeholder={t("team.emailPlaceholder")}
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  style={{ flex: 1, minWidth: 220 }}
                />
                <select
                  className="field-input"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as TeamRole)}
                  style={{ width: 140 }}
                >
                  <option value="admin">{t("team.roles.admin")}</option>
                  <option value="editor">{t("team.roles.editor")}</option>
                  <option value="viewer">{t("team.roles.viewer")}</option>
                </select>
                <button className="btn btn-primary" type="submit" disabled={inviting}>
                  {inviting ? t("team.inviting") : t("team.sendInvite")}
                </button>
              </div>
              {teamError && <p className="error-text" style={{ margin: 0 }}>{teamError}</p>}
              {teamSuccess && (
                <p style={{ color: "var(--success)", fontSize: 14, margin: 0 }}>{teamSuccess}</p>
              )}
            </form>
          </div>

          <div className="settings-card" style={{ marginTop: 20 }}>
            <h2 className="settings-section-title">{t("team.membersTitle")}</h2>
            {teamLoading ? (
              <p className="muted-text">{t("common:loading")}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {teamMembers.map((m) => (
                  <div
                    key={m.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{m.name}</div>
                      <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>{m.email}</div>
                    </div>
                    <span
                      className="badge"
                      style={{ textTransform: "capitalize" }}
                    >
                      {t(`team.roles.${m.role}`)}
                    </span>
                    {m.id !== "owner" && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleRemoveMember(m.id)}
                      >
                        {t("team.remove")}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {teamInvites.length > 0 && (
            <div className="settings-card" style={{ marginTop: 20 }}>
              <h2 className="settings-section-title">{t("team.pendingTitle")}</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {teamInvites.map((i) => (
                  <div
                    key={i.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      border: "1px dashed var(--border)",
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{i.email}</div>
                      <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
                        {t("team.invitedAs", { role: t(`team.roles.${i.role}`) })} ·{" "}
                        {t("team.expiresOn", {
                          date: new Date(i.expires_at).toLocaleDateString(),
                        })}
                      </div>
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleRevokeInvite(i.id)}
                    >
                      {t("team.revoke")}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "integrations" && (
        <div className="settings-section">
          <div className="settings-card">
            <h2 className="settings-section-title">
              {t("integrations.slack.title")}
            </h2>
            <p className="muted-text" style={{ marginTop: -4, marginBottom: 16 }}>
              {t("integrations.slack.description")}
            </p>

            <ol style={{ fontSize: 14, color: "var(--text-secondary)", paddingLeft: 20, marginBottom: 16, lineHeight: 1.7 }}>
              <li>
                {t("integrations.slack.step1")}{" "}
                <a
                  href="https://api.slack.com/messaging/webhooks"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "var(--brand-500)" }}
                >
                  api.slack.com/messaging/webhooks
                </a>
              </li>
              <li>{t("integrations.slack.step2")}</li>
              <li>{t("integrations.slack.step3")}</li>
            </ol>

            <form className="auth-form" style={{ maxWidth: 560 }} onSubmit={handleSaveSlack}>
              <div>
                <label className="field-label">{t("integrations.slack.urlLabel")}</label>
                <input
                  className="field-input"
                  type="url"
                  value={slackUrl}
                  onChange={(e) => setSlackUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/T.../B.../..."
                  autoComplete="off"
                />
                <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 6 }}>
                  {t("integrations.slack.urlHint")}
                </p>
              </div>

              {slackMessage && (
                <p
                  style={{
                    fontSize: 14,
                    color: slackMessage.type === "success" ? "var(--success)" : "var(--danger)",
                    margin: 0,
                  }}
                >
                  {slackMessage.text}
                </p>
              )}

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn btn-primary" type="submit" disabled={slackSaving}>
                  {slackSaving ? t("profile.saving") : t("integrations.slack.save")}
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={slackTesting || !slackUrl.trim()}
                  onClick={handleTestSlack}
                >
                  {slackTesting ? t("integrations.slack.testing") : t("integrations.slack.test")}
                </button>
              </div>
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
