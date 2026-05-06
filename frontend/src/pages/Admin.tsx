import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import AdminBlog from "./AdminBlog";

// ── Types ──────────────────────────────────────────────────────────────────

interface AdminProject {
  id: string;
  name: string;
  created_at: string;
  participant_count: number;
}

interface AdminUser {
  id: string;
  name: string;
  email: string;
  subscription_tier: string;
  subscription_status: string;
  trial_ends_at: string | null;
  email_verified: boolean;
  onboarding_completed: boolean;
  created_at: string;
  last_active: string | null;
  project_count: number;
  interview_count: number;
  business_summary?: string | null;
  projects?: AdminProject[];
}

interface AdminStats {
  total_users: number;
  users_by_tier: Record<string, number>;
  active_trials: number;
  total_projects: number;
  total_interviews_completed: number;
  signups_last_7_days: number;
  signups_last_30_days: number;
}

interface CostsByOperation {
  [op: string]: { cost_usd: number; count: number };
}

interface CompanyCost {
  company_id: string;
  name: string;
  email: string;
  total_cost_usd: number;
  this_month_usd: number;
  interview_count: number;
}

interface CostsReport {
  total_cost_usd: number;
  this_month_usd: number;
  by_operation: CostsByOperation;
  avg_cost_per_interview_usd: number;
  total_interviews: number;
  by_company: CompanyCost[];
}

// ── API helpers ────────────────────────────────────────────────────────────

function adminClient(key: string) {
  return axios.create({
    baseURL: "/api",
    headers: { Authorization: `Bearer ${key}` },
  });
}

// ── Tier badge ─────────────────────────────────────────────────────────────

const TIER_COLORS: Record<string, { bg: string; color: string }> = {
  solo:       { bg: "#f1f2f6", color: "#5a6076" },
  team:       { bg: "#e0e9ff", color: "#2d53e8" },
  lab:        { bg: "#f3e8ff", color: "#7c3aed" },
  enterprise: { bg: "#fef3c7", color: "#92400e" },
};

function TierBadge({ tier }: { tier: string }) {
  const style = TIER_COLORS[tier] ?? { bg: "#f1f2f6", color: "#5a6076" };
  return (
    <span
      style={{
        background: style.bg,
        color: style.color,
        padding: "2px 10px",
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {tier}
    </span>
  );
}

// ── Trial status ───────────────────────────────────────────────────────────

function trialLabel(trial_ends_at: string | null): string {
  if (!trial_ends_at) return "—";
  const end = new Date(trial_ends_at);
  const now = new Date();
  if (end <= now) return "Expired";
  const days = Math.ceil((end.getTime() - now.getTime()) / 86400000);
  return `${days}d left`;
}

function trialColor(trial_ends_at: string | null): string {
  if (!trial_ends_at) return "var(--text-muted)";
  const end = new Date(trial_ends_at);
  const now = new Date();
  if (end <= now) return "var(--danger)";
  const days = Math.ceil((end.getTime() - now.getTime()) / 86400000);
  if (days <= 3) return "var(--warning)";
  return "var(--success)";
}

// ── Stat card ──────────────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: "16px 20px",
        minWidth: 140,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)" }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

// ── Confirm dialog ─────────────────────────────────────────────────────────

function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(13,15,26,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: 28,
          maxWidth: 380,
          width: "90%",
          boxShadow: "var(--shadow-xl)",
        }}
      >
        <p style={{ marginBottom: 20, color: "var(--text-primary)", lineHeight: 1.5 }}>
          {message}
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            style={{
              background: "var(--danger)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius-sm)",
              padding: "8px 16px",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 14,
            }}
            onClick={onConfirm}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function Admin() {
  const [adminKey, setAdminKey] = useState<string>(
    () => sessionStorage.getItem("admin_key") ?? ""
  );
  const [keyInput, setKeyInput] = useState("");
  const [keyError, setKeyError] = useState("");
  const [authed, setAuthed] = useState(false);

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<AdminProject[]>([]);
  const [expandLoading, setExpandLoading] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState<AdminUser | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState("");

  const [creditDialog, setCreditDialog] = useState<AdminUser | null>(null);
  const [creditDelta, setCreditDelta] = useState("");
  const [creditReason, setCreditReason] = useState("");
  const [creditDialogError, setCreditDialogError] = useState<string | null>(null);
  const [creditDialogSubmitting, setCreditDialogSubmitting] = useState(false);

  const [costs, setCosts] = useState<CostsReport | null>(null);

  // Affiliates management
  const [tab, setTab] = useState<"users" | "affiliates" | "blog">("users");
  const [affiliates, setAffiliates] = useState<any[]>([]);
  const [affiliatesLoading, setAffiliatesLoading] = useState(false);

  const client = useCallback(
    () => adminClient(adminKey),
    [adminKey]
  );

  // Verify key and load data
  const login = useCallback(async (key: string) => {
    setKeyError("");
    try {
      const res = await adminClient(key).get<AdminStats>("/admin/stats");
      setStats(res.data);
      sessionStorage.setItem("admin_key", key);
      setAdminKey(key);
      setAuthed(true);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        setKeyError("Invalid admin key");
      } else {
        setKeyError("Could not connect to backend");
      }
    }
  }, []);

  // Auto-login if key already in sessionStorage
  useEffect(() => {
    if (adminKey) {
      login(adminKey);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      if (tierFilter) params.tier = tierFilter;
      const res = await client().get<AdminUser[]>("/admin/users", { params });
      setUsers(res.data);
    } catch {
      setError("Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [client, search, tierFilter]);

  const loadStats = useCallback(async () => {
    try {
      const res = await client().get<AdminStats>("/admin/stats");
      setStats(res.data);
    } catch {
      // non-critical
    }
  }, [client]);

  const loadCosts = useCallback(async () => {
    try {
      const res = await client().get<CostsReport>("/admin/costs");
      setCosts(res.data);
    } catch {
      // non-critical
    }
  }, [client]);

  const loadAffiliates = useCallback(async () => {
    setAffiliatesLoading(true);
    try {
      const res = await client().get("/affiliates/admin/list");
      setAffiliates(res.data.affiliates || []);
    } catch {
      setError("Failed to load affiliates");
    } finally {
      setAffiliatesLoading(false);
    }
  }, [client]);

  useEffect(() => {
    if (authed) {
      if (tab === "users") {
        loadUsers();
        loadCosts();
      } else if (tab === "affiliates") {
        loadAffiliates();
      }
      loadStats();
    }
  }, [authed, search, tierFilter, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleExpand(user: AdminUser) {
    if (expandedId === user.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(user.id);
    setExpandLoading(true);
    try {
      const res = await client().get<AdminUser>(`/admin/users/${user.id}`);
      setExpandedProjects(res.data.projects ?? []);
    } catch {
      setExpandedProjects([]);
    } finally {
      setExpandLoading(false);
    }
  }

  async function handleTierChange(user: AdminUser, tier: string) {
    setActionLoading(`tier-${user.id}`);
    try {
      await client().patch(`/admin/users/${user.id}/tier`, { tier });
      setUsers((prev) =>
        prev.map((u) =>
          u.id === user.id
            ? { ...u, subscription_tier: tier, subscription_status: "active" }
            : u
        )
      );
      showSuccess("Tier updated");
    } catch {
      setError("Failed to update tier");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleTrialAction(user: AdminUser, action: string) {
    setActionLoading(`trial-${user.id}`);
    try {
      const res = await client().patch<AdminUser>(`/admin/users/${user.id}/trial`, {
        action,
      });
      setUsers((prev) =>
        prev.map((u) =>
          u.id === user.id ? { ...u, trial_ends_at: res.data.trial_ends_at } : u
        )
      );
      showSuccess("Trial updated");
    } catch {
      setError("Failed to update trial");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleAdjustCredits() {
    if (!creditDialog) return;
    const delta = parseInt(creditDelta, 10);
    if (Number.isNaN(delta) || delta === 0) {
      setCreditDialogError("Enter a non-zero integer");
      return;
    }
    if (!creditReason.trim()) {
      setCreditDialogError("Reason is required");
      return;
    }
    setCreditDialogSubmitting(true);
    setCreditDialogError(null);
    try {
      await client().post(`/admin/workspaces/${creditDialog.id}/credits/adjust`, {
        credits_delta: delta,
        reason: creditReason.trim(),
      });
      showSuccess(`${delta > 0 ? "Granted" : "Clawed back"} ${Math.abs(delta)} credit${Math.abs(delta) !== 1 ? "s" : ""}`);
      setCreditDialog(null);
      setCreditDelta("");
      setCreditReason("");
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setCreditDialogError(detail ?? "Failed to adjust credits");
    } finally {
      setCreditDialogSubmitting(false);
    }
  }

  async function handleDelete(user: AdminUser) {
    setConfirmDelete(null);
    setActionLoading(`delete-${user.id}`);
    try {
      await client().delete(`/admin/users/${user.id}`);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
      await loadStats();
      showSuccess("User deleted");
    } catch {
      setError("Failed to delete user");
    } finally {
      setActionLoading(null);
    }
  }

  function showSuccess(msg: string) {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(""), 2500);
  }

  // ── Login gate ────────────────────────────────────────────────────────────

  if (!authed) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg-base)",
        }}
      >
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            padding: 40,
            width: 360,
            boxShadow: "var(--shadow-md)",
          }}
        >
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Admin Panel</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 24 }}>
            QualiPulse internal
          </p>
          <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
            Admin key
          </label>
          <input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && login(keyInput)}
            placeholder="Enter admin secret key"
            style={{
              display: "block",
              width: "100%",
              marginTop: 6,
              marginBottom: 16,
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              border: `1px solid ${keyError ? "var(--danger)" : "var(--border)"}`,
              fontSize: 14,
              outline: "none",
            }}
          />
          {keyError && (
            <p style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>
              {keyError}
            </p>
          )}
          <button
            onClick={() => login(keyInput)}
            style={{
              width: "100%",
              background: "var(--primary)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius-sm)",
              padding: "10px 0",
              fontWeight: 600,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  // ── Main admin UI ─────────────────────────────────────────────────────────

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        padding: "0 0 60px",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border)",
          padding: "0 32px",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>
            QualiPulse Admin
          </span>
          <span
            style={{
              fontSize: 11,
              background: "var(--danger-bg)",
              color: "var(--danger)",
              border: "1px solid var(--danger-border)",
              borderRadius: 4,
              padding: "2px 8px",
              fontWeight: 600,
            }}
          >
            INTERNAL
          </span>
        </div>
        <button
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            fontSize: 13,
          }}
          onClick={() => {
            sessionStorage.removeItem("admin_key");
            setAuthed(false);
            setAdminKey("");
          }}
        >
          Sign out
        </button>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px 0" }}>

        {/* Stats bar */}
        {stats && (
          <div
            style={{
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
              marginBottom: 28,
            }}
          >
            <StatCard label="Total users" value={stats.total_users} />
            <StatCard label="Total projects" value={stats.total_projects} />
            <StatCard label="Completed interviews" value={stats.total_interviews_completed} />
            <StatCard label="Active trials" value={stats.active_trials} />
            <StatCard label="Signups (7d)" value={stats.signups_last_7_days} />
            <StatCard label="Signups (30d)" value={stats.signups_last_30_days} />
            {Object.entries(stats.users_by_tier).map(([tier, count]) => (
              <StatCard key={tier} label={`${tier} users`} value={count} />
            ))}
          </div>
        )}

        {/* AI Costs card */}
        {costs && (
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-lg)",
              padding: "20px 24px",
              marginBottom: 24,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: 16,
              }}
            >
              AI Spend
            </div>

            {/* Top-line numbers */}
            <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.total_cost_usd.toFixed(2)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  All time
                </div>
              </div>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.this_month_usd.toFixed(2)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  This month
                </div>
              </div>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.avg_cost_per_interview_usd.toFixed(3)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  Avg / interview ({costs.total_interviews} total)
                </div>
              </div>
            </div>

            {/* By-operation table */}
            {Object.keys(costs.by_operation).length > 0 && (
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr>
                    {["Operation", "Calls", "Total cost"].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: "left",
                          padding: "4px 12px 8px 0",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "var(--text-muted)",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                          borderBottom: "1px solid var(--border-subtle)",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(costs.by_operation)
                    .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
                    .map(([op, data]) => (
                      <tr key={op}>
                        <td
                          style={{
                            padding: "6px 12px 6px 0",
                            color: "var(--text-secondary)",
                            fontFamily: "monospace",
                            fontSize: 12,
                          }}
                        >
                          {op}
                        </td>
                        <td style={{ padding: "6px 12px 6px 0", color: "var(--text-secondary)" }}>
                          {data.count.toLocaleString()}
                        </td>
                        <td style={{ padding: "6px 0", color: "var(--text-primary)", fontWeight: 500 }}>
                          ${data.cost_usd.toFixed(4)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: "flex", gap: 16, marginBottom: 24, borderBottom: "1px solid var(--border)" }}>
          <button
            onClick={() => setTab("users")}
            style={{
              padding: "12px 0",
              border: "none",
              background: "none",
              borderBottom: tab === "users" ? "2px solid var(--primary)" : "none",
              color: tab === "users" ? "var(--primary)" : "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === "users" ? 600 : 500,
            }}
          >
            Users
          </button>
          <button
            onClick={() => setTab("affiliates")}
            style={{
              padding: "12px 0",
              border: "none",
              background: "none",
              borderBottom: tab === "affiliates" ? "2px solid var(--primary)" : "none",
              color: tab === "affiliates" ? "var(--primary)" : "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === "affiliates" ? 600 : 500,
            }}
          >
            Affiliates
          </button>
          <button
            onClick={() => setTab("blog")}
            style={{
              padding: "12px 0",
              border: "none",
              background: "none",
              borderBottom: tab === "blog" ? "2px solid var(--primary)" : "none",
              color: tab === "blog" ? "var(--primary)" : "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === "blog" ? 600 : 500,
            }}
          >
            Blog
          </button>
        </div>

        {/* Toolbar - Users only */}
        {tab === "users" && (
          <div
            style={{
              display: "flex",
              gap: 10,
              marginBottom: 16,
              alignItems: "center",
            }}
          >
            <input
              type="search"
              placeholder="Search by name or email…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                flex: 1,
                maxWidth: 340,
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                fontSize: 14,
                outline: "none",
              }}
            />
            <select
              value={tierFilter}
              onChange={(e) => setTierFilter(e.target.value)}
              style={{
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                fontSize: 13,
                background: "var(--bg-surface)",
                cursor: "pointer",
                outline: "none",
              }}
            >
              <option value="">All tiers</option>
              <option value="solo">Solo</option>
              <option value="team">Team</option>
              <option value="lab">Lab</option>
              <option value="enterprise">Enterprise</option>
            </select>
            <button
              onClick={loadUsers}
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 14px",
                fontSize: 13,
                cursor: "pointer",
                color: "var(--text-secondary)",
              }}
            >
              Refresh
            </button>
          </div>
        )}

        {/* Messages */}
        {error && (
          <div
            style={{
              background: "var(--danger-bg)",
              border: "1px solid var(--danger-border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--danger)",
              padding: "10px 14px",
              marginBottom: 12,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}
        {successMsg && (
          <div
            style={{
              background: "var(--success-bg)",
              border: "1px solid var(--success-border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--success)",
              padding: "10px 14px",
              marginBottom: 12,
              fontSize: 13,
            }}
          >
            {successMsg}
          </div>
        )}

        {/* Affiliates table */}
        {tab === "affiliates" && (
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
            }}
          >
            <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Affiliate Program</h2>
                <button
                  onClick={loadAffiliates}
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "8px 14px",
                    fontSize: 13,
                    cursor: "pointer",
                    color: "var(--text-secondary)",
                  }}
                >
                  Refresh
                </button>
              </div>
            </div>
            {affiliatesLoading && <div style={{ padding: "24px", textAlign: "center" }}>Loading...</div>}
            {!affiliatesLoading && affiliates.length === 0 && (
              <div style={{ padding: "24px", textAlign: "center", color: "var(--text-secondary)" }}>
                No affiliates yet.
              </div>
            )}
            {!affiliatesLoading && affiliates.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border)" }}>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Name</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Email</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Code</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Status</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Commission %</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Signups</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Conversions</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Earned</th>
                    </tr>
                  </thead>
                  <tbody>
                    {affiliates.map((aff: any) => (
                      <tr key={aff.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "12px", fontSize: 13 }}>{aff.name}</td>
                        <td style={{ padding: "12px", fontSize: 13 }}>{aff.email}</td>
                        <td style={{ padding: "12px", fontSize: 13, fontFamily: "monospace" }}>{aff.code}</td>
                        <td style={{ padding: "12px", fontSize: 12 }}>
                          <span
                            style={{
                              background: aff.status === "active" ? "var(--success-bg)" : aff.status === "pending" ? "var(--warning-bg)" : "var(--danger-bg)",
                              color: aff.status === "active" ? "var(--success)" : aff.status === "pending" ? "var(--warning)" : "var(--danger)",
                              padding: "4px 8px",
                              borderRadius: 4,
                              fontWeight: 600,
                            }}
                          >
                            {aff.status}
                          </span>
                        </td>
                        <td style={{ padding: "12px", textAlign: "right", fontSize: 13 }}>{aff.commission_pct.toFixed(1)}%</td>
                        <td style={{ padding: "12px", textAlign: "right", fontSize: 13 }}>{aff.signups}</td>
                        <td style={{ padding: "12px", textAlign: "right", fontSize: 13 }}>{aff.conversions}</td>
                        <td style={{ padding: "12px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>${aff.total_earned.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Users table */}
        {tab === "users" && (
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
          }}
        >
          {/* Table header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "2fr 2fr 1fr 1fr 1fr 1fr 2fr",
              padding: "10px 16px",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-sunken)",
              fontSize: 11,
              fontWeight: 600,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            <span>Name</span>
            <span>Email</span>
            <span>Tier</span>
            <span>Trial</span>
            <span>Projects</span>
            <span>Signed up</span>
            <span>Actions</span>
          </div>

          {loading && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
              Loading…
            </div>
          )}
          {!loading && users.length === 0 && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
              No users found
            </div>
          )}

          {users.map((user) => (
            <div key={user.id}>
              {/* Row */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 2fr 1fr 1fr 1fr 1fr 2fr",
                  padding: "12px 16px",
                  borderBottom: "1px solid var(--border-subtle)",
                  alignItems: "center",
                  cursor: "pointer",
                  background: expandedId === user.id ? "var(--bg-overlay)" : undefined,
                  transition: "background 0.1s",
                }}
                onClick={() => handleExpand(user)}
              >
                {/* Name */}
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                    {user.name}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                    {user.email_verified ? "✓ verified" : "unverified"}
                  </div>
                </div>

                {/* Email */}
                <div
                  style={{ fontSize: 12, color: "var(--text-secondary)", wordBreak: "break-all" }}
                >
                  {user.email}
                </div>

                {/* Tier */}
                <div>
                  <TierBadge tier={user.subscription_tier} />
                </div>

                {/* Trial */}
                <div
                  style={{
                    fontSize: 12,
                    color: trialColor(user.trial_ends_at),
                    fontWeight: 500,
                  }}
                >
                  {trialLabel(user.trial_ends_at)}
                </div>

                {/* Projects */}
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  {user.project_count}
                </div>

                {/* Signed up */}
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {new Date(user.created_at).toLocaleDateString()}
                </div>

                {/* Actions */}
                <div
                  style={{ display: "flex", gap: 6, alignItems: "center" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Tier selector */}
                  <select
                    value={user.subscription_tier}
                    disabled={actionLoading === `tier-${user.id}`}
                    onChange={(e) => handleTierChange(user, e.target.value)}
                    style={{
                      fontSize: 12,
                      padding: "4px 6px",
                      borderRadius: "var(--radius-xs)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      cursor: "pointer",
                      outline: "none",
                    }}
                  >
                    <option value="solo">Solo</option>
                    <option value="team">Team</option>
                    <option value="lab">Lab</option>
                    <option value="enterprise">Enterprise</option>
                  </select>

                  {/* Trial selector */}
                  <select
                    value=""
                    disabled={actionLoading === `trial-${user.id}`}
                    onChange={(e) => {
                      if (e.target.value) handleTrialAction(user, e.target.value);
                    }}
                    style={{
                      fontSize: 12,
                      padding: "4px 6px",
                      borderRadius: "var(--radius-xs)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      cursor: "pointer",
                      outline: "none",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <option value="" disabled>
                      Trial…
                    </option>
                    <option value="extend_7">+7 days</option>
                    <option value="extend_14">+14 days</option>
                    <option value="extend_30">+30 days</option>
                    <option value="reset">Reset (14d)</option>
                    <option value="expire">Expire now</option>
                  </select>

                  {/* Delete */}
                  <button
                    disabled={actionLoading === `delete-${user.id}`}
                    onClick={() => setConfirmDelete(user)}
                    style={{
                      background: "none",
                      border: "1px solid var(--danger-border)",
                      color: "var(--danger)",
                      borderRadius: "var(--radius-xs)",
                      padding: "4px 8px",
                      fontSize: 12,
                      cursor: "pointer",
                      fontWeight: 500,
                      opacity: actionLoading === `delete-${user.id}` ? 0.5 : 1,
                    }}
                  >
                    {actionLoading === `delete-${user.id}` ? "…" : "Delete"}
                  </button>
                </div>
              </div>

              {/* Expanded projects */}
              {expandedId === user.id && (
                <div
                  style={{
                    background: "var(--bg-sunken)",
                    borderBottom: "1px solid var(--border-subtle)",
                    padding: "12px 32px 16px",
                  }}
                >
                  {/* AI spend for this user */}
                  {costs?.by_company && (() => {
                    const co = costs.by_company.find((c) => c.company_id === user.id);
                    if (!co) return null;
                    return (
                      <div style={{ marginBottom: 12, fontSize: 12, color: "var(--text-muted)" }}>
                        AI spend:{" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                          ${co.total_cost_usd.toFixed(4)}
                        </span>{" "}
                        total ·{" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                          ${co.this_month_usd.toFixed(4)}
                        </span>{" "}
                        this month
                      </div>
                    );
                  })()}

                  {/* Manual credit adjust — only meaningful for non-legacy plans, but
                      we show it always; the endpoint refuses with a 400 for legacy. */}
                  <div style={{ marginBottom: 12 }}>
                    <button
                      onClick={() => {
                        setCreditDialog(user);
                        setCreditDelta("");
                        setCreditReason("");
                        setCreditDialogError(null);
                      }}
                      style={{
                        background: "none",
                        border: "1px solid var(--border)",
                        color: "var(--text-primary)",
                        borderRadius: "var(--radius-xs)",
                        padding: "4px 10px",
                        fontSize: 12,
                        cursor: "pointer",
                        fontWeight: 500,
                      }}
                    >
                      Adjust credits
                    </button>
                  </div>

                  {users.find((u) => u.id === expandedId)?.business_summary && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                        Business summary
                      </div>
                      <p style={{ fontSize: 12, color: "var(--text-secondary)", fontStyle: "italic", margin: 0, lineHeight: 1.5 }}>
                        {users.find((u) => u.id === expandedId)?.business_summary}
                      </p>
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      marginBottom: 10,
                    }}
                  >
                    Projects ({expandLoading ? "…" : expandedProjects.length})
                  </div>
                  {expandLoading && (
                    <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading…</div>
                  )}
                  {!expandLoading && expandedProjects.length === 0 && (
                    <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No projects</div>
                  )}
                  {!expandLoading &&
                    expandedProjects.map((p) => (
                      <div
                        key={p.id}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          padding: "7px 12px",
                          background: "var(--bg-surface)",
                          borderRadius: "var(--radius-sm)",
                          marginBottom: 6,
                          border: "1px solid var(--border-subtle)",
                          fontSize: 13,
                        }}
                      >
                        <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                          {p.name}
                        </span>
                        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                          {p.participant_count} participant{p.participant_count !== 1 ? "s" : ""}{" "}
                          · {new Date(p.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
        )}
      </div>

        {/* Blog management tab */}
        {tab === "blog" && <AdminBlog adminKey={adminKey} />}

      {/* Credit adjustment dialog */}
      {creditDialog && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 16,
          }}
          onClick={() => !creditDialogSubmitting && setCreditDialog(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-lg)",
              padding: 24,
              width: 420,
              maxWidth: "100%",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
              Adjust credits
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
              {creditDialog.name} · {creditDialog.email}
            </p>
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Credits delta (positive = grant, negative = claw back)
            </label>
            <input
              type="number"
              value={creditDelta}
              onChange={(e) => setCreditDelta(e.target.value)}
              placeholder="e.g. 10 or -5"
              disabled={creditDialogSubmitting}
              style={{
                width: "100%",
                padding: "8px 10px",
                fontSize: 13,
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-xs)",
                marginBottom: 12,
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
              }}
            />
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              Reason (logged for audit)
            </label>
            <textarea
              value={creditReason}
              onChange={(e) => setCreditReason(e.target.value)}
              placeholder="e.g. Goodwill grant after failed interview"
              disabled={creditDialogSubmitting}
              rows={2}
              style={{
                width: "100%",
                padding: "8px 10px",
                fontSize: 13,
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-xs)",
                marginBottom: 12,
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
            {creditDialogError && (
              <div style={{ fontSize: 12, color: "var(--danger)", marginBottom: 12 }}>
                {creditDialogError}
              </div>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setCreditDialog(null)}
                disabled={creditDialogSubmitting}
                style={{
                  background: "none",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 12px",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleAdjustCredits}
                disabled={creditDialogSubmitting}
                style={{
                  background: "var(--primary)",
                  border: "none",
                  color: "white",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 14px",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  opacity: creditDialogSubmitting ? 0.6 : 1,
                }}
              >
                {creditDialogSubmitting ? "Applying…" : "Apply"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm delete dialog */}
      {confirmDelete && (
        <ConfirmDialog
          message={`Delete account for "${confirmDelete.name}" (${confirmDelete.email})? This permanently removes all their data and cannot be undone.`}
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
