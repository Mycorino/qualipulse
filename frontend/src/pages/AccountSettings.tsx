import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";

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
  const navigate = useNavigate();
  const [me, setMe] = useState<{ name: string; email: string } | null>(null);
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
      alert("Billing is not configured yet. Contact support.");
    }
  }

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    setProfileSuccess(false);
    try {
      await client.patch("/auth/me", { name: name.trim() });
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
    if (newPassword.length < 8) { setPasswordError("New password must be at least 8 characters"); return; }
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
      setPasswordError(msg ?? "Failed to update password. Check your current password.");
    }
  }

  async function handleManageBilling() {
    try {
      const { data } = await client.post("/billing/portal", {
        return_url: window.location.href,
      });
      window.location.href = data.portal_url;
    } catch {
      alert("Billing portal not available. Contact support.");
    }
  }

  if (loading) return <div className="dashboard-page"><p className="muted-text">Loading...</p></div>;

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Account Settings</h1>
          <p className="dashboard-subtitle">{me?.email}</p>
        </div>
        <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
      </div>

      <div className="settings-tabs">
        <button className={`settings-tab ${tab === "profile" ? "active" : ""}`} onClick={() => setTab("profile")}>Profile</button>
        <button className={`settings-tab ${tab === "billing" ? "active" : ""}`} onClick={() => setTab("billing")}>Plan & Billing</button>
      </div>

      {tab === "profile" && (
        <div className="settings-section">
          <div className="settings-card">
            <h2 className="settings-section-title">Profile</h2>
            <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleSaveProfile}>
              <div>
                <label className="field-label">Name</label>
                <input className="field-input" value={name} onChange={e => setName(e.target.value)} required />
              </div>
              <div>
                <label className="field-label">Email</label>
                <input className="field-input" value={me?.email ?? ""} disabled style={{ opacity: 0.6 }} />
              </div>
              {profileSuccess && <p style={{ color: "#16a34a", fontSize: 14 }}>✓ Profile updated</p>}
              <button className="btn btn-primary" type="submit" disabled={savingProfile} style={{ width: "fit-content" }}>
                {savingProfile ? "Saving..." : "Save changes"}
              </button>
            </form>
          </div>

          <div className="settings-card" style={{ marginTop: 20 }}>
            <h2 className="settings-section-title">Change Password</h2>
            <form className="auth-form" style={{ maxWidth: 400 }} onSubmit={handleChangePassword}>
              <div>
                <label className="field-label">Current password</label>
                <input type="password" className="field-input" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required />
              </div>
              <div>
                <label className="field-label">New password</label>
                <input type="password" className="field-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8} />
              </div>
              {passwordError && <p className="error-text">{passwordError}</p>}
              {passwordSuccess && <p style={{ color: "#16a34a", fontSize: 14 }}>✓ Password updated</p>}
              <button className="btn btn-primary" type="submit" style={{ width: "fit-content" }}>Update password</button>
            </form>
          </div>
        </div>
      )}

      {tab === "billing" && (
        <div className="settings-section">
          {billing && (
            <div className="settings-card">
              <h2 className="settings-section-title">Current plan</h2>
              <div className="billing-current-plan">
                <div>
                  <span className={`plan-badge plan-badge--${billing.tier}`}>{billing.tier_name}</span>
                  <span className="billing-status-badge" style={{ marginLeft: 8 }}>{billing.status}</span>
                </div>
                <div className="billing-limits">
                  <div className="billing-limit-row">
                    <span>Projects</span>
                    <span>{billing.limits.max_projects === -1 ? "Unlimited" : billing.limits.max_projects}</span>
                  </div>
                  <div className="billing-limit-row">
                    <span>Participants per project</span>
                    <span>{billing.limits.max_participants_per_project === -1 ? "Unlimited" : billing.limits.max_participants_per_project}</span>
                  </div>
                  <div className="billing-limit-row">
                    <span>AI analysis</span>
                    <span style={{ color: billing.limits.ai_analysis ? "var(--success)" : "var(--text-tertiary)" }}>{billing.limits.ai_analysis ? "✓ Included" : "— Upgrade to unlock"}</span>
                  </div>
                  <div className="billing-limit-row">
                    <span>CSV export</span>
                    <span style={{ color: billing.limits.export_csv ? "var(--success)" : "var(--text-tertiary)" }}>{billing.limits.export_csv ? "✓ Included" : "— Upgrade to unlock"}</span>
                  </div>
                  <div className="billing-limit-row">
                    <span>Team members</span>
                    <span>{billing.limits.team_members === -1 ? "Unlimited" : billing.limits.team_members}</span>
                  </div>
                </div>
                {billing.tier !== "free" && (
                  <button className="btn btn-ghost btn-sm" onClick={handleManageBilling} style={{ marginTop: 16 }}>
                    Manage billing →
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="settings-card" style={{ marginTop: 20 }}>
            <h2 className="settings-section-title">Upgrade plan</h2>
            <div className="plans-grid">
              {plans.filter(p => p.id !== "free").map(plan => (
                <div key={plan.id} className={`plan-card ${billing?.tier === plan.id ? "plan-card--current" : ""}`}>
                  <div className="plan-card-header">
                    <h3 className="plan-name">{plan.name}</h3>
                    <p className="plan-price">
                      {plan.price_monthly_usd === 0 ? "Custom" : `$${plan.price_monthly_usd}/mo`}
                    </p>
                  </div>
                  <ul className="plan-features">
                    <li>{plan.max_projects === -1 ? "Unlimited projects" : `${plan.max_projects} projects`}</li>
                    <li>{plan.max_participants_per_project === -1 ? "Unlimited participants" : `${plan.max_participants_per_project} participants/project`}</li>
                    <li>{plan.ai_analysis ? "✓ AI analysis" : "✗ AI analysis"}</li>
                    <li>{plan.export_csv ? "✓ CSV export" : "✗ CSV export"}</li>
                    <li>{plan.team_members === -1 ? "Unlimited team members" : `${plan.team_members} team members`}</li>
                  </ul>
                  {billing?.tier === plan.id ? (
                    <button className="btn btn-ghost btn-sm" disabled>Current plan</button>
                  ) : plan.id === "enterprise" ? (
                    <a href="mailto:hello@autointerview.com" className="btn btn-ghost btn-sm">Contact us</a>
                  ) : (
                    <button className="btn btn-primary btn-sm" onClick={() => handleUpgrade(plan.id)}>
                      Upgrade to {plan.name}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
