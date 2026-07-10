import { Fragment, useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
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
  suspended_at?: string | null;
  suspension_reason?: string | null;
}

interface AuditEntry {
  id: string;
  admin_identity: string;
  action: string;
  target_company_id: string | null;
  target_company_email: string;
  details: Record<string, unknown> | null;
  is_impersonation: boolean;
  created_at: string;
}

interface AdminAffiliate {
  id: string;
  name: string;
  email: string;
  code: string;
  status: string;
  commission_pct: number;
  total_earned: number;
  total_paid: number;
  pending_earnings: number;
  payout_threshold: number;
  signups: number;
  conversions: number;
  website: string | null;
  how_they_found_us: string | null;
  notes: string | null;
  created_at: string;
  approved_at: string | null;
}

interface AffiliatePayout {
  id: string;
  amount: number;
  paid_at: string;
  notes: string | null;
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

function adminClient(key: string, identity?: string) {
  const headers: Record<string, string> = { Authorization: `Bearer ${key}` };
  if (identity) headers["X-Admin-Identity"] = identity;
  return axios.create({ baseURL: "/api", headers });
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

function trialLabel(
  trial_ends_at: string | null,
  t: (key: string, opts?: Record<string, unknown>) => string
): string {
  if (!trial_ends_at) return t("users.trialNone");
  const end = new Date(trial_ends_at);
  const now = new Date();
  if (end <= now) return t("users.trialExpired");
  const days = Math.ceil((end.getTime() - now.getTime()) / 86400000);
  return t("users.trialDaysLeft", { count: days });
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
  const { t } = useTranslation("admin");
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
            {t("deleteDialog.cancel")}
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
            {t("deleteDialog.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function Admin() {
  const { t } = useTranslation("admin");
  const [adminKey, setAdminKey] = useState<string>(
    () => sessionStorage.getItem("admin_key") ?? ""
  );
  const [adminIdentity, setAdminIdentity] = useState<string>(
    () => sessionStorage.getItem("admin_identity") ?? ""
  );
  const [keyInput, setKeyInput] = useState("");
  const [identityInput, setIdentityInput] = useState("");
  const [keyError, setKeyError] = useState("");
  const [authed, setAuthed] = useState(false);

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [userPage, setUserPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const USERS_PAGE_SIZE = 50;

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

  const [tab, setTab] = useState<"users" | "affiliates" | "blog" | "audit" | "panel">("users");
  // Panel / consumer-account deletion (GDPR erasure + testing reset).
  const [panelEmail, setPanelEmail] = useState("");
  const [panelIncludeInterviews, setPanelIncludeInterviews] = useState(false);
  const [panelDeleting, setPanelDeleting] = useState(false);
  const [panelResult, setPanelResult] = useState<string | null>(null);

  async function handleDeletePanelist() {
    const email = panelEmail.trim();
    if (!email) return;
    if (!window.confirm(`Delete panel/consumer account for ${email}? This removes their panel profile, enrichment answers, and magic tokens${panelIncludeInterviews ? ", plus their interview records" : ""}.`)) return;
    setPanelDeleting(true);
    setPanelResult(null);
    try {
      const res = await client().delete(`/admin/panel/${encodeURIComponent(email)}`, {
        params: { include_interviews: panelIncludeInterviews },
      });
      const d = res.data;
      setPanelResult(`Deleted ${email} — profile: ${d.panel_profile}, answers: ${d.panel_answers}, magic tokens: ${d.magic_tokens}, participants: ${d.participants}, turns: ${d.interview_turns}`);
      setPanelEmail("");
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setPanelResult(`Failed: ${typeof detail === "string" ? detail : "see console"}`);
    } finally {
      setPanelDeleting(false);
    }
  }
  const [affiliates, setAffiliates] = useState<AdminAffiliate[]>([]);
  const [affiliatesLoading, setAffiliatesLoading] = useState(false);
  const [affStatusFilter, setAffStatusFilter] = useState("");
  const [affExpandedId, setAffExpandedId] = useState<string | null>(null);
  const [affPayouts, setAffPayouts] = useState<AffiliatePayout[]>([]);
  const [affPayoutsLoading, setAffPayoutsLoading] = useState(false);
  const [commissionEditId, setCommissionEditId] = useState<string | null>(null);
  const [commissionValue, setCommissionValue] = useState("");

  const [payoutDialog, setPayoutDialog] = useState<AdminAffiliate | null>(null);
  const [payoutAmount, setPayoutAmount] = useState("");
  const [payoutNotes, setPayoutNotes] = useState("");
  const [payoutError, setPayoutError] = useState<string | null>(null);
  const [payoutSubmitting, setPayoutSubmitting] = useState(false);

  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditAction, setAuditAction] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  const [auditPage, setAuditPage] = useState(1);

  const [suspendDialog, setSuspendDialog] = useState<AdminUser | null>(null);
  const [suspendReason, setSuspendReason] = useState("");
  const [suspendSubmitting, setSuspendSubmitting] = useState(false);

  const client = useCallback(
    () => adminClient(adminKey, adminIdentity),
    [adminKey, adminIdentity]
  );

  // Verify key and load data
  const login = useCallback(async (key: string, identity: string) => {
    setKeyError("");
    if (!identity.trim()) {
      setKeyError(t("login.errorIdentityRequired"));
      return;
    }
    try {
      const res = await adminClient(key, identity).get<AdminStats>("/admin/stats");
      setStats(res.data);
      sessionStorage.setItem("admin_key", key);
      sessionStorage.setItem("admin_identity", identity.trim());
      setAdminKey(key);
      setAdminIdentity(identity.trim());
      setAuthed(true);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        setKeyError(t("login.errorInvalidKey"));
      } else {
        setKeyError(t("login.errorConnect"));
      }
    }
  }, [t]);

  // Auto-login if key already in sessionStorage
  useEffect(() => {
    if (adminKey && adminIdentity) {
      login(adminKey, adminIdentity);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string | number> = {
        page: userPage,
        limit: USERS_PAGE_SIZE,
      };
      if (search) params.search = search;
      if (tierFilter) params.tier = tierFilter;
      const res = await client().get<AdminUser[]>("/admin/users", { params });
      setUsers(res.data);
    } catch {
      setError(t("toasts.loadUsersFailed"));
    } finally {
      setLoading(false);
    }
  }, [client, search, tierFilter, userPage, t]);

  // Debounce the search input so we don't fire a request per keystroke
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(searchInput.trim());
      setUserPage(1);
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

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

  const loadAffiliates = useCallback(async (silent = false) => {
    if (!silent) setAffiliatesLoading(true);
    try {
      const res = await client().get<{ affiliates: AdminAffiliate[] }>("/affiliates/admin/list");
      setAffiliates(res.data.affiliates || []);
    } catch {
      if (!silent) setError(t("toasts.loadAffiliatesFailed"));
    } finally {
      if (!silent) setAffiliatesLoading(false);
    }
  }, [client, t]);

  const loadAuditLog = useCallback(async (page = 1, action = auditAction) => {
    setAuditLoading(true);
    try {
      const params: Record<string, string | number> = { page, limit: 50 };
      if (action) params.action = action;
      if (auditSearch) params.search = auditSearch;
      const res = await client().get<AuditEntry[]>("/admin/audit-log", { params });
      setAuditLog(res.data);
      setAuditPage(page);
    } catch {
      setError(t("toasts.loadAuditFailed"));
    } finally {
      setAuditLoading(false);
    }
  }, [client, auditAction, auditSearch, t]);

  useEffect(() => {
    if (authed) {
      if (tab === "users") {
        loadUsers();
      } else if (tab === "affiliates") {
        loadAffiliates();
      } else if (tab === "audit") {
        loadAuditLog(1);
      }
    }
  }, [authed, search, tierFilter, userPage, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  // Stats + cost report aggregate the whole AIUsageLog table — load them once
  // per session, not on every search keystroke / page / tab flip. Mutations
  // that change them (deletion, tier change) refresh explicitly.
  useEffect(() => {
    if (authed) {
      loadStats();
      loadCosts();
    }
  }, [authed]); // eslint-disable-line react-hooks/exhaustive-deps

  // Silent affiliate fetch on auth so the pending-application badge shows
  // without opening the tab
  useEffect(() => {
    if (authed) loadAffiliates(true);
  }, [authed]); // eslint-disable-line react-hooks/exhaustive-deps

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
      showSuccess(t("toasts.tierUpdated"));
    } catch {
      setError(t("toasts.tierUpdateFailed"));
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
      showSuccess(t("toasts.trialUpdated"));
    } catch {
      setError(t("toasts.trialUpdateFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleAdjustCredits() {
    if (!creditDialog) return;
    const delta = parseInt(creditDelta, 10);
    if (Number.isNaN(delta) || delta === 0) {
      setCreditDialogError(t("creditsDialog.errorNonZero"));
      return;
    }
    if (!creditReason.trim()) {
      setCreditDialogError(t("creditsDialog.errorReasonRequired"));
      return;
    }
    setCreditDialogSubmitting(true);
    setCreditDialogError(null);
    try {
      const res = await client().post<{ balance?: { available_credits?: number } }>(
        `/admin/workspaces/${creditDialog.id}/credits/adjust`,
        {
          credits_delta: delta,
          reason: creditReason.trim(),
        }
      );
      const available = res.data?.balance?.available_credits;
      showSuccess(
        t(delta > 0 ? "toasts.creditsGranted" : "toasts.creditsClawedBack", {
          count: Math.abs(delta),
        }) + (typeof available === "number" ? ` (${t("creditsDialog.nowAvailable", { count: available })})` : "")
      );
      setCreditDialog(null);
      setCreditDelta("");
      setCreditReason("");
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setCreditDialogError(detail ?? t("toasts.creditsAdjustFailed"));
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
      await Promise.all([loadStats(), loadCosts()]);
      showSuccess(t("toasts.userDeleted"));
    } catch {
      setError(t("toasts.userDeleteFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleSuspend() {
    if (!suspendDialog) return;
    if (!suspendReason.trim()) return;
    setSuspendSubmitting(true);
    try {
      const res = await client().post<AdminUser>(
        `/admin/users/${suspendDialog.id}/suspend`,
        { reason: suspendReason.trim() }
      );
      setUsers((prev) =>
        prev.map((u) =>
          u.id === suspendDialog.id
            ? { ...u, suspended_at: res.data.suspended_at, suspension_reason: res.data.suspension_reason }
            : u
        )
      );
      showSuccess(t("toasts.accountSuspended"));
      setSuspendDialog(null);
      setSuspendReason("");
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? t("toasts.suspendFailed"));
    } finally {
      setSuspendSubmitting(false);
    }
  }

  async function handleUnsuspend(user: AdminUser) {
    setActionLoading(`unsuspend-${user.id}`);
    try {
      const res = await client().post<AdminUser>(`/admin/users/${user.id}/unsuspend`);
      setUsers((prev) =>
        prev.map((u) =>
          u.id === user.id
            ? { ...u, suspended_at: res.data.suspended_at, suspension_reason: res.data.suspension_reason }
            : u
        )
      );
      showSuccess(t("toasts.accountUnsuspended"));
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? t("toasts.unsuspendFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleImpersonate(user: AdminUser) {
    setActionLoading(`impersonate-${user.id}`);
    try {
      const res = await client().post<{ access_token: string; company_name: string; company_email: string }>(
        `/admin/users/${user.id}/impersonate`
      );
      const params = new URLSearchParams({
        access_token: res.data.access_token,
        name: res.data.company_name,
        email: res.data.company_email,
      });
      window.open(`/auth/impersonate-finish#${params.toString()}`, "_blank");
      showSuccess(t("toasts.impersonationOpened"));
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? t("toasts.impersonateFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  function showSuccess(msg: string) {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(""), 2500);
  }

  function applyAffiliateUpdate(updated: AdminAffiliate) {
    setAffiliates((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  }

  async function handleAffiliateStatus(aff: AdminAffiliate, newStatus: "active" | "rejected") {
    setActionLoading(`aff-status-${aff.id}`);
    try {
      const res = await client().patch<{ affiliate: AdminAffiliate }>(
        `/affiliates/admin/${aff.id}`,
        { status: newStatus }
      );
      applyAffiliateUpdate(res.data.affiliate);
      showSuccess(
        newStatus === "active" ? t("affiliates.approved") : t("affiliates.rejected")
      );
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : t("toasts.affiliateUpdateFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCommissionSave(aff: AdminAffiliate) {
    const pct = parseFloat(commissionValue);
    if (Number.isNaN(pct) || pct <= 0 || pct > 100) {
      setError(t("affiliates.commissionInvalid"));
      return;
    }
    setActionLoading(`aff-commission-${aff.id}`);
    try {
      const res = await client().patch<{ affiliate: AdminAffiliate }>(
        `/affiliates/admin/${aff.id}`,
        { commission_pct: pct }
      );
      applyAffiliateUpdate(res.data.affiliate);
      setCommissionEditId(null);
      showSuccess(t("affiliates.commissionUpdated"));
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : t("toasts.affiliateUpdateFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleAffiliateExpand(aff: AdminAffiliate) {
    if (affExpandedId === aff.id) {
      setAffExpandedId(null);
      return;
    }
    setAffExpandedId(aff.id);
    setAffPayouts([]);
    setAffPayoutsLoading(true);
    try {
      const res = await client().get<{ payouts: AffiliatePayout[] }>(
        `/affiliates/admin/${aff.id}/payouts`
      );
      setAffPayouts(res.data.payouts);
    } catch {
      setAffPayouts([]);
    } finally {
      setAffPayoutsLoading(false);
    }
  }

  async function handleRecordPayout() {
    if (!payoutDialog) return;
    const amount = parseFloat(payoutAmount);
    if (Number.isNaN(amount) || amount <= 0) {
      setPayoutError(t("payoutDialog.errorAmount"));
      return;
    }
    setPayoutSubmitting(true);
    setPayoutError(null);
    try {
      const res = await client().post<{ total_paid: number; pending_earnings: number }>(
        `/affiliates/admin/${payoutDialog.id}/payout`,
        { amount, notes: payoutNotes.trim() || null }
      );
      setAffiliates((prev) =>
        prev.map((a) =>
          a.id === payoutDialog.id
            ? { ...a, total_paid: res.data.total_paid, pending_earnings: res.data.pending_earnings }
            : a
        )
      );
      showSuccess(t("affiliates.payoutRecorded", { amount: amount.toFixed(2) }));
      setPayoutDialog(null);
      setPayoutAmount("");
      setPayoutNotes("");
      if (affExpandedId === payoutDialog.id) {
        const payoutsRes = await client()
          .get<{ payouts: AffiliatePayout[] }>(`/affiliates/admin/${payoutDialog.id}/payouts`)
          .catch(() => null);
        if (payoutsRes) setAffPayouts(payoutsRes.data.payouts);
      }
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setPayoutError(typeof detail === "string" ? detail : t("toasts.payoutFailed"));
    } finally {
      setPayoutSubmitting(false);
    }
  }

  const pendingAffiliateCount = affiliates.filter((a) => a.status === "pending").length;
  const visibleAffiliates = affStatusFilter
    ? affiliates.filter((a) => a.status === affStatusFilter)
    : affiliates;

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
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{t("login.title")}</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 24 }}>
            {t("login.subtitle")}
          </p>
          <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
            {t("login.yourName")}
          </label>
          <input
            type="text"
            value={identityInput}
            onChange={(e) => setIdentityInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && login(keyInput, identityInput)}
            placeholder={t("login.namePlaceholder")}
            style={{
              display: "block",
              width: "100%",
              marginTop: 6,
              marginBottom: 16,
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              fontSize: 14,
              outline: "none",
            }}
          />
          <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
            {t("login.adminKey")}
          </label>
          <input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && login(keyInput, identityInput)}
            placeholder={t("login.adminKeyPlaceholder")}
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
            onClick={() => login(keyInput, identityInput)}
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
            {t("login.signIn")}
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
            {t("header.title")}
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
            {t("header.internalBadge")}
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
            sessionStorage.removeItem("admin_identity");
            setAuthed(false);
            setAdminKey("");
            setAdminIdentity("");
          }}
        >
          {t("header.signOut")}
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
            <StatCard label={t("stats.totalUsers")} value={stats.total_users} />
            <StatCard label={t("stats.totalProjects")} value={stats.total_projects} />
            <StatCard label={t("stats.completedInterviews")} value={stats.total_interviews_completed} />
            <StatCard label={t("stats.activeTrials")} value={stats.active_trials} />
            <StatCard label={t("stats.signups7d")} value={stats.signups_last_7_days} />
            <StatCard label={t("stats.signups30d")} value={stats.signups_last_30_days} />
            {Object.entries(stats.users_by_tier).map(([tier, count]) => (
              <StatCard key={tier} label={t("stats.tierUsers", { tier })} value={count} />
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
              {t("costs.title")}
            </div>

            {/* Top-line numbers */}
            <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.total_cost_usd.toFixed(2)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  {t("costs.allTime")}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.this_month_usd.toFixed(2)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  {t("costs.thisMonth")}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)" }}>
                  ${costs.avg_cost_per_interview_usd.toFixed(3)}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  {t("costs.avgPerInterview", { count: costs.total_interviews })}
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
                    {["costs.colOperation", "costs.colCalls", "costs.colTotalCost"].map((h) => (
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
                        {t(h)}
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
            {t("tabs.users")}
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
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {t("tabs.affiliates")}
            {pendingAffiliateCount > 0 && (
              <span
                style={{
                  background: "var(--warning-bg, #fffbeb)",
                  color: "var(--warning-text, #92400e)",
                  border: "1px solid var(--warning-border, #fcd34d)",
                  borderRadius: 10,
                  padding: "0 7px",
                  fontSize: 11,
                  fontWeight: 700,
                  lineHeight: "18px",
                }}
                title={t("affiliates.pendingBadgeTitle", { count: pendingAffiliateCount })}
              >
                {pendingAffiliateCount}
              </span>
            )}
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
            {t("tabs.blog")}
          </button>
          <button
            onClick={() => setTab("audit")}
            style={{
              padding: "12px 0",
              border: "none",
              background: "none",
              borderBottom: tab === "audit" ? "2px solid var(--primary)" : "none",
              color: tab === "audit" ? "var(--primary)" : "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === "audit" ? 600 : 500,
            }}
          >
            {t("tabs.audit")}
          </button>
          <button
            onClick={() => setTab("panel")}
            style={{
              padding: "12px 0",
              border: "none",
              background: "none",
              borderBottom: tab === "panel" ? "2px solid var(--primary)" : "none",
              color: tab === "panel" ? "var(--primary)" : "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === "panel" ? 600 : 500,
            }}
          >
            {t("tabs.panel", "Panel")}
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
              placeholder={t("users.searchPlaceholder")}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
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
              onChange={(e) => { setTierFilter(e.target.value); setUserPage(1); }}
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
              <option value="">{t("users.allTiers")}</option>
              <option value="free">{t("users.tierFree", "Free")}</option>
              <option value="starter">{t("users.tierStarter", "Starter")}</option>
              <option value="solo">{t("users.tierSolo")}</option>
              <option value="team">{t("users.tierTeam")}</option>
              <option value="lab">{t("users.tierLab")}</option>
              <option value="enterprise">{t("users.tierEnterprise")}</option>
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
              {t("users.refresh")}
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
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>{t("affiliates.title")}</h2>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {["", "pending", "active", "rejected"].map((s) => (
                    <button
                      key={s || "all"}
                      onClick={() => setAffStatusFilter(s)}
                      style={{
                        background: affStatusFilter === s ? "var(--primary)" : "var(--bg-surface)",
                        color: affStatusFilter === s ? "#fff" : "var(--text-secondary)",
                        border: `1px solid ${affStatusFilter === s ? "var(--primary)" : "var(--border)"}`,
                        borderRadius: 999,
                        padding: "5px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      {s === "" ? t("affiliates.filterAll") : t(`affiliates.status_${s}`)}
                      {s === "pending" && pendingAffiliateCount > 0 && ` (${pendingAffiliateCount})`}
                    </button>
                  ))}
                  <button
                    onClick={() => loadAffiliates()}
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      padding: "6px 14px",
                      fontSize: 13,
                      cursor: "pointer",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {t("affiliates.refresh")}
                  </button>
                </div>
              </div>
            </div>
            {affiliatesLoading && <div style={{ padding: "24px", textAlign: "center" }}>{t("affiliates.loading")}</div>}
            {!affiliatesLoading && visibleAffiliates.length === 0 && (
              <div style={{ padding: "24px", textAlign: "center", color: "var(--text-secondary)" }}>
                {affStatusFilter ? t("affiliates.noneForFilter") : t("affiliates.none")}
              </div>
            )}
            {!affiliatesLoading && visibleAffiliates.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border)" }}>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colName")}</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colCode")}</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colStatus")}</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colCommission")}</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colSignups")}</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colConversions")}</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colEarned")}</th>
                      <th style={{ padding: "12px", textAlign: "right", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colPending")}</th>
                      <th style={{ padding: "12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{t("affiliates.colActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleAffiliates.map((aff) => (
                      <Fragment key={aff.id}>
                        <tr
                          style={{ borderBottom: "1px solid var(--border)", cursor: "pointer", background: affExpandedId === aff.id ? "var(--bg-overlay)" : undefined }}
                          onClick={() => handleAffiliateExpand(aff)}
                        >
                          <td style={{ padding: "12px", fontSize: 13 }}>
                            <div style={{ fontWeight: 500 }}>{aff.name}</div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{aff.email}</div>
                          </td>
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
                              {t(`affiliates.status_${aff.status}`, aff.status)}
                            </span>
                          </td>
                          <td
                            style={{ padding: "12px", textAlign: "right", fontSize: 13 }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {commissionEditId === aff.id ? (
                              <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                                <input
                                  type="number"
                                  value={commissionValue}
                                  min={1}
                                  max={100}
                                  step={0.5}
                                  autoFocus
                                  onChange={(e) => setCommissionValue(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") handleCommissionSave(aff);
                                    if (e.key === "Escape") setCommissionEditId(null);
                                  }}
                                  style={{ width: 64, padding: "4px 6px", fontSize: 12, border: "1px solid var(--border)", borderRadius: "var(--radius-xs)" }}
                                  aria-label={t("affiliates.colCommission")}
                                />
                                <button
                                  disabled={actionLoading === `aff-commission-${aff.id}`}
                                  onClick={() => handleCommissionSave(aff)}
                                  style={{ background: "var(--primary)", color: "#fff", border: "none", borderRadius: "var(--radius-xs)", padding: "4px 8px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                                >
                                  {actionLoading === `aff-commission-${aff.id}` ? "…" : t("affiliates.save")}
                                </button>
                              </span>
                            ) : (
                              <button
                                onClick={() => { setCommissionEditId(aff.id); setCommissionValue(String(aff.commission_pct)); }}
                                title={t("affiliates.editCommission")}
                                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: "var(--text-primary)", textDecoration: "underline dotted", padding: 0 }}
                              >
                                {aff.commission_pct.toFixed(1)}%
                              </button>
                            )}
                          </td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: 13 }}>{aff.signups}</td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: 13 }}>{aff.conversions}</td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: 13, fontWeight: 600 }}>${aff.total_earned.toFixed(2)}</td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: aff.pending_earnings >= aff.payout_threshold ? "var(--warning-text, #92400e)" : undefined }}>
                            ${aff.pending_earnings.toFixed(2)}
                          </td>
                          <td style={{ padding: "12px", fontSize: 12 }} onClick={(e) => e.stopPropagation()}>
                            {aff.status === "pending" ? (
                              <span style={{ display: "inline-flex", gap: 6 }}>
                                <button
                                  disabled={actionLoading === `aff-status-${aff.id}`}
                                  onClick={() => handleAffiliateStatus(aff, "active")}
                                  style={{ background: "var(--success)", color: "#fff", border: "none", borderRadius: "var(--radius-xs)", padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                                >
                                  {actionLoading === `aff-status-${aff.id}` ? "…" : t("affiliates.approve")}
                                </button>
                                <button
                                  disabled={actionLoading === `aff-status-${aff.id}`}
                                  onClick={() => handleAffiliateStatus(aff, "rejected")}
                                  style={{ background: "none", border: "1px solid var(--danger-border)", color: "var(--danger)", borderRadius: "var(--radius-xs)", padding: "4px 10px", fontSize: 12, fontWeight: 500, cursor: "pointer" }}
                                >
                                  {t("affiliates.reject")}
                                </button>
                              </span>
                            ) : aff.status === "active" ? (
                              <button
                                disabled={aff.pending_earnings <= 0}
                                onClick={() => {
                                  setPayoutDialog(aff);
                                  setPayoutAmount(aff.pending_earnings > 0 ? aff.pending_earnings.toFixed(2) : "");
                                  setPayoutNotes("");
                                  setPayoutError(null);
                                }}
                                title={aff.pending_earnings <= 0 ? t("affiliates.nothingToPayOut") : undefined}
                                style={{
                                  background: "none",
                                  border: "1px solid var(--border)",
                                  color: "var(--text-primary)",
                                  borderRadius: "var(--radius-xs)",
                                  padding: "4px 10px",
                                  fontSize: 12,
                                  fontWeight: 500,
                                  cursor: aff.pending_earnings <= 0 ? "default" : "pointer",
                                  opacity: aff.pending_earnings <= 0 ? 0.4 : 1,
                                }}
                              >
                                {t("affiliates.recordPayout")}
                              </button>
                            ) : (
                              <span style={{ color: "var(--text-muted)" }}>—</span>
                            )}
                          </td>
                        </tr>
                        {affExpandedId === aff.id && (
                          <tr style={{ borderBottom: "1px solid var(--border)" }}>
                            <td colSpan={9} style={{ padding: "14px 24px", background: "var(--bg-sunken)" }}>
                              <div style={{ display: "flex", gap: 40, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
                                <span>
                                  <strong style={{ color: "var(--text-muted)", fontWeight: 600 }}>{t("affiliates.applied")}</strong>{" "}
                                  {new Date(aff.created_at).toLocaleDateString()}
                                </span>
                                {aff.approved_at && (
                                  <span>
                                    <strong style={{ color: "var(--text-muted)", fontWeight: 600 }}>{t("affiliates.approvedOn")}</strong>{" "}
                                    {new Date(aff.approved_at).toLocaleDateString()}
                                  </span>
                                )}
                                {aff.website && (
                                  <span>
                                    <strong style={{ color: "var(--text-muted)", fontWeight: 600 }}>{t("affiliates.website")}</strong>{" "}
                                    <a href={aff.website} target="_blank" rel="noopener noreferrer" style={{ color: "var(--primary)" }}>{aff.website}</a>
                                  </span>
                                )}
                                <span>
                                  <strong style={{ color: "var(--text-muted)", fontWeight: 600 }}>{t("affiliates.paidOut")}</strong>{" "}
                                  ${aff.total_paid.toFixed(2)}
                                </span>
                              </div>
                              {aff.how_they_found_us && (
                                <p style={{ fontSize: 12, color: "var(--text-secondary)", fontStyle: "italic", margin: "0 0 12px", lineHeight: 1.5 }}>
                                  “{aff.how_they_found_us}”
                                </p>
                              )}
                              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                                {t("affiliates.payoutHistory")}
                              </div>
                              {affPayoutsLoading && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("affiliates.loading")}</div>}
                              {!affPayoutsLoading && affPayouts.length === 0 && (
                                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("affiliates.noPayouts")}</div>
                              )}
                              {!affPayoutsLoading &&
                                affPayouts.map((p) => (
                                  <div key={p.id} style={{ display: "flex", gap: 16, fontSize: 12, padding: "5px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                                    <span style={{ color: "var(--text-muted)", minWidth: 90 }}>{new Date(p.paid_at).toLocaleDateString()}</span>
                                    <span style={{ fontWeight: 600 }}>${p.amount.toFixed(2)}</span>
                                    {p.notes && <span style={{ color: "var(--text-secondary)" }}>{p.notes}</span>}
                                  </div>
                                ))}
                            </td>
                          </tr>
                        )}
                      </Fragment>
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
            <span>{t("users.colName")}</span>
            <span>{t("users.colEmail")}</span>
            <span>{t("users.colTier")}</span>
            <span>{t("users.colTrial")}</span>
            <span>{t("users.colProjects")}</span>
            <span>{t("users.colSignedUp")}</span>
            <span>{t("users.colActions")}</span>
          </div>

          {loading && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
              {t("users.loading")}
            </div>
          )}
          {!loading && users.length === 0 && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
              {t("users.noUsers")}
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
                    {user.email_verified ? t("users.verified") : t("users.unverified")}
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
                  {trialLabel(user.trial_ends_at, t)}
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
                    <option value="free">{t("users.tierFree", "Free")}</option>
                    <option value="starter">{t("users.tierStarter", "Starter")}</option>
                    <option value="solo">{t("users.tierSolo")}</option>
                    <option value="team">{t("users.tierTeam")}</option>
                    <option value="lab">{t("users.tierLab")}</option>
                    <option value="enterprise">{t("users.tierEnterprise")}</option>
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
                      {t("users.trialOption")}
                    </option>
                    <option value="extend_7">{t("users.trialExtend7")}</option>
                    <option value="extend_14">{t("users.trialExtend14")}</option>
                    <option value="extend_30">{t("users.trialExtend30")}</option>
                    <option value="reset">{t("users.trialReset")}</option>
                    <option value="expire">{t("users.trialExpire")}</option>
                  </select>
                  {/* Trial is calendar-based for LEGACY accounts only. New
                      accounts are credits-based — use "Adjust credits" to
                      grant/claw back interview credits instead of touching a
                      trial date that doesn't gate their access. */}

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
                    {actionLoading === `delete-${user.id}` ? "…" : t("users.delete")}
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
                        {t("users.aiSpendLabel")}{" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                          ${co.total_cost_usd.toFixed(4)}
                        </span>{" "}
                        {t("users.aiSpendTotal")} ·{" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                          ${co.this_month_usd.toFixed(4)}
                        </span>{" "}
                        {t("users.aiSpendThisMonth")}
                      </div>
                    );
                  })()}

                  <div style={{ marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
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
                      {t("users.adjustCredits")}
                    </button>
                    <button
                      disabled={actionLoading === `impersonate-${user.id}`}
                      onClick={() => handleImpersonate(user)}
                      style={{
                        background: "none",
                        border: "1px solid var(--border)",
                        color: "var(--text-primary)",
                        borderRadius: "var(--radius-xs)",
                        padding: "4px 10px",
                        fontSize: 12,
                        cursor: "pointer",
                        fontWeight: 500,
                        opacity: actionLoading === `impersonate-${user.id}` ? 0.5 : 1,
                      }}
                    >
                      {actionLoading === `impersonate-${user.id}` ? "…" : t("users.loginAs")}
                    </button>
                    {user.suspended_at ? (
                      <button
                        disabled={actionLoading === `unsuspend-${user.id}`}
                        onClick={() => handleUnsuspend(user)}
                        style={{
                          background: "none",
                          border: "1px solid var(--success-border)",
                          color: "var(--success)",
                          borderRadius: "var(--radius-xs)",
                          padding: "4px 10px",
                          fontSize: 12,
                          cursor: "pointer",
                          fontWeight: 500,
                          opacity: actionLoading === `unsuspend-${user.id}` ? 0.5 : 1,
                        }}
                      >
                        {actionLoading === `unsuspend-${user.id}` ? "…" : t("users.unsuspend")}
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setSuspendDialog(user);
                          setSuspendReason("");
                        }}
                        style={{
                          background: "none",
                          border: "1px solid var(--warning-border, var(--border))",
                          color: "var(--warning-text, #92400e)",
                          borderRadius: "var(--radius-xs)",
                          padding: "4px 10px",
                          fontSize: 12,
                          cursor: "pointer",
                          fontWeight: 500,
                        }}
                      >
                        {t("users.suspend")}
                      </button>
                    )}
                  </div>

                  {user.suspended_at && (
                    <div style={{
                      marginBottom: 12,
                      padding: "8px 12px",
                      background: "var(--warning-bg, #fffbeb)",
                      border: "1px solid var(--warning-border, #fcd34d)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: 12,
                      color: "var(--warning-text, #92400e)",
                    }}>
                      <strong>{t("users.suspendedBadge")}</strong>
                      {user.suspension_reason && <> — {user.suspension_reason}</>}
                      <span style={{ marginLeft: 8, opacity: 0.7 }}>
                        ({new Date(user.suspended_at).toLocaleDateString()})
                      </span>
                    </div>
                  )}

                  {users.find((u) => u.id === expandedId)?.business_summary && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                        {t("users.businessSummary")}
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
                    {expandLoading
                      ? `${t("users.colProjects")} (${t("users.projectsLoading")})`
                      : t("users.projectsCount", { count: expandedProjects.length })}
                  </div>
                  {expandLoading && (
                    <div style={{ color: "var(--text-muted)", fontSize: 13 }}>{t("users.loadingShort")}</div>
                  )}
                  {!expandLoading && expandedProjects.length === 0 && (
                    <div style={{ color: "var(--text-muted)", fontSize: 13 }}>{t("users.noProjects")}</div>
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
                          {t("users.participants", { count: p.participant_count })}{" "}
                          · {new Date(p.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}

          {/* Users pagination */}
          {!loading && (userPage > 1 || users.length === USERS_PAGE_SIZE) && (
            <div style={{ display: "flex", gap: 8, padding: "12px 16px", justifyContent: "flex-end", borderTop: "1px solid var(--border)" }}>
              <button
                disabled={userPage <= 1}
                onClick={() => setUserPage((p) => Math.max(1, p - 1))}
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-xs)",
                  padding: "4px 12px",
                  fontSize: 12,
                  cursor: userPage <= 1 ? "default" : "pointer",
                  opacity: userPage <= 1 ? 0.4 : 1,
                }}
              >
                {t("users.prev")}
              </button>
              <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
                {t("users.page", { page: userPage })}
              </span>
              <button
                disabled={users.length < USERS_PAGE_SIZE}
                onClick={() => setUserPage((p) => p + 1)}
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-xs)",
                  padding: "4px 12px",
                  fontSize: 12,
                  cursor: users.length < USERS_PAGE_SIZE ? "default" : "pointer",
                  opacity: users.length < USERS_PAGE_SIZE ? 0.4 : 1,
                }}
              >
                {t("users.next")}
              </button>
            </div>
          )}
        </div>
        )}

        {/* Blog management tab */}
        {tab === "blog" && <AdminBlog adminKey={adminKey} />}

        {/* Audit log tab */}
        {tab === "audit" && (
          <div>
            <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "center" }}>
              <select
                value={auditAction}
                onChange={(e) => { setAuditAction(e.target.value); loadAuditLog(1, e.target.value); }}
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
                <option value="">{t("audit.allActions")}</option>
                <option value="tier_change">{t("audit.actionTierChange")}</option>
                <option value="trial_change">{t("audit.actionTrialUpdate")}</option>
                <option value="credit_adjust">{t("audit.actionCreditAdjustment")}</option>
                <option value="user_delete">{t("audit.actionUserDelete")}</option>
                <option value="suspend">{t("audit.actionSuspend")}</option>
                <option value="unsuspend">{t("audit.actionUnsuspend")}</option>
                <option value="impersonation_start">{t("audit.actionImpersonation")}</option>
              </select>
              <input
                type="search"
                placeholder={t("audit.searchPlaceholder")}
                value={auditSearch}
                onChange={(e) => setAuditSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadAuditLog(1)}
                style={{
                  flex: 1,
                  maxWidth: 300,
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border)",
                  fontSize: 14,
                  outline: "none",
                }}
              />
              <button
                onClick={() => loadAuditLog(1)}
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
                {t("audit.search")}
              </button>
            </div>

            <div
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                overflow: "hidden",
              }}
            >
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border)" }}>
                    {["audit.colWhen", "audit.colAdmin", "audit.colAction", "audit.colTarget", "audit.colDetails"].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: "10px 12px",
                          textAlign: "left",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "var(--text-muted)",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                        }}
                      >
                        {t(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {auditLoading && (
                    <tr>
                      <td colSpan={5} style={{ padding: 24, textAlign: "center", color: "var(--text-muted)" }}>
                        {t("audit.loading")}
                      </td>
                    </tr>
                  )}
                  {!auditLoading && auditLog.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ padding: 24, textAlign: "center", color: "var(--text-muted)" }}>
                        {t("audit.noEntries")}
                      </td>
                    </tr>
                  )}
                  {!auditLoading &&
                    auditLog.map((entry) => (
                      <tr key={entry.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                        <td style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                          {new Date(entry.created_at).toLocaleString()}
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>
                          {entry.admin_identity}
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 12 }}>
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 600,
                              background: entry.action === "user_delete" ? "var(--danger-bg)"
                                : entry.action === "suspend" ? "var(--warning-bg, #fffbeb)"
                                : entry.action === "impersonation_start" ? "#fef3c7"
                                : "var(--bg-sunken)",
                              color: entry.action === "user_delete" ? "var(--danger)"
                                : entry.action === "suspend" ? "var(--warning-text, #92400e)"
                                : entry.action === "impersonation_start" ? "#92400e"
                                : "var(--text-secondary)",
                            }}
                          >
                            {entry.action.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
                          {entry.target_company_email}
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                          {entry.details ? JSON.stringify(entry.details) : "—"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>

              {/* Pagination */}
              {!auditLoading && auditLog.length > 0 && (
                <div style={{ display: "flex", gap: 8, padding: "12px 16px", justifyContent: "flex-end", borderTop: "1px solid var(--border)" }}>
                  <button
                    disabled={auditPage <= 1}
                    onClick={() => loadAuditLog(auditPage - 1)}
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-xs)",
                      padding: "4px 12px",
                      fontSize: 12,
                      cursor: auditPage <= 1 ? "default" : "pointer",
                      opacity: auditPage <= 1 ? 0.4 : 1,
                    }}
                  >
                    {t("audit.prev")}
                  </button>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
                    {t("audit.page", { page: auditPage })}
                  </span>
                  <button
                    disabled={auditLog.length < 50}
                    onClick={() => loadAuditLog(auditPage + 1)}
                    style={{
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-xs)",
                      padding: "4px 12px",
                      fontSize: 12,
                      cursor: auditLog.length < 50 ? "default" : "pointer",
                      opacity: auditLog.length < 50 ? 0.4 : 1,
                    }}
                  >
                    {t("audit.next")}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Panel / consumer accounts tab */}
        {tab === "panel" && (
          <div style={{ maxWidth: 560 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>
              {t("panel.title", "Delete a consumer / panelist account")}
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.5, marginBottom: 16 }}>
              {t("panel.help", "Removes their panel profile, all enrichment answers, and outstanding magic tokens. GDPR right-to-erasure — also resets re-testing with the same email (the profiling questionnaire shows again).")}
            </p>
            <input
              type="email"
              value={panelEmail}
              onChange={(e) => setPanelEmail(e.target.value)}
              placeholder="participant@example.com"
              style={{
                width: "100%", padding: "10px 12px", borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)", fontSize: 14, marginBottom: 12,
                background: "var(--bg-surface)", outline: "none",
              }}
            />
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)", marginBottom: 16, cursor: "pointer" }}>
              <input type="checkbox" checked={panelIncludeInterviews} onChange={(e) => setPanelIncludeInterviews(e.target.checked)} />
              {t("panel.includeInterviews", "Also delete their interview records (across all studies)")}
            </label>
            <button
              className="btn btn-danger"
              disabled={!panelEmail.trim() || panelDeleting}
              onClick={handleDeletePanelist}
              style={{ minHeight: 44 }}
            >
              {panelDeleting ? t("panel.deleting", "Deleting…") : t("panel.deleteCta", "Delete panelist")}
            </button>
            {panelResult && (
              <p style={{ marginTop: 14, fontSize: 13, color: panelResult.startsWith("Failed") ? "var(--danger, #dc2626)" : "var(--text-secondary)", lineHeight: 1.5 }}>
                {panelResult}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Suspend dialog */}
      {suspendDialog && (
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
          onClick={() => !suspendSubmitting && setSuspendDialog(null)}
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
              {t("suspendDialog.title")}
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
              {suspendDialog.name} · {suspendDialog.email}
            </p>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12, lineHeight: 1.5 }}>
              {t("suspendDialog.warning")}
            </p>
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              {t("suspendDialog.reasonLabel")}
            </label>
            <textarea
              value={suspendReason}
              onChange={(e) => setSuspendReason(e.target.value)}
              placeholder={t("suspendDialog.reasonPlaceholder")}
              disabled={suspendSubmitting}
              rows={2}
              style={{
                width: "100%",
                padding: "8px 10px",
                fontSize: 13,
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-xs)",
                marginBottom: 16,
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setSuspendDialog(null)}
                disabled={suspendSubmitting}
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
                {t("suspendDialog.cancel")}
              </button>
              <button
                onClick={handleSuspend}
                disabled={suspendSubmitting || !suspendReason.trim()}
                style={{
                  background: "var(--danger)",
                  border: "none",
                  color: "white",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 14px",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  opacity: suspendSubmitting || !suspendReason.trim() ? 0.6 : 1,
                }}
              >
                {suspendSubmitting ? t("suspendDialog.submitting") : t("suspendDialog.submit")}
              </button>
            </div>
          </div>
        </div>
      )}

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
              {t("creditsDialog.title")}
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
              {creditDialog.name} · {creditDialog.email}
            </p>
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              {t("creditsDialog.deltaLabel")}
            </label>
            <input
              type="number"
              value={creditDelta}
              onChange={(e) => setCreditDelta(e.target.value)}
              placeholder={t("creditsDialog.deltaPlaceholder")}
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
              {t("creditsDialog.reasonLabel")}
            </label>
            <textarea
              value={creditReason}
              onChange={(e) => setCreditReason(e.target.value)}
              placeholder={t("creditsDialog.reasonPlaceholder")}
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
                {t("creditsDialog.cancel")}
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
                {creditDialogSubmitting ? t("creditsDialog.submitting") : t("creditsDialog.submit")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Record payout dialog */}
      {payoutDialog && (
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
          onClick={() => !payoutSubmitting && setPayoutDialog(null)}
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
              {t("payoutDialog.title")}
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
              {payoutDialog.name} · {payoutDialog.email}
            </p>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
              {t("payoutDialog.pendingInfo", { amount: payoutDialog.pending_earnings.toFixed(2) })}
            </p>
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>
              {t("payoutDialog.amountLabel")}
            </label>
            <input
              type="number"
              value={payoutAmount}
              min={0.01}
              step={0.01}
              onChange={(e) => setPayoutAmount(e.target.value)}
              disabled={payoutSubmitting}
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
              {t("payoutDialog.notesLabel")}
            </label>
            <textarea
              value={payoutNotes}
              onChange={(e) => setPayoutNotes(e.target.value)}
              placeholder={t("payoutDialog.notesPlaceholder")}
              disabled={payoutSubmitting}
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
            {payoutError && (
              <div style={{ fontSize: 12, color: "var(--danger)", marginBottom: 12 }}>
                {payoutError}
              </div>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setPayoutDialog(null)}
                disabled={payoutSubmitting}
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
                {t("payoutDialog.cancel")}
              </button>
              <button
                onClick={handleRecordPayout}
                disabled={payoutSubmitting}
                style={{
                  background: "var(--primary)",
                  border: "none",
                  color: "white",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 14px",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  opacity: payoutSubmitting ? 0.6 : 1,
                }}
              >
                {payoutSubmitting ? t("payoutDialog.submitting") : t("payoutDialog.submit")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm delete dialog */}
      {confirmDelete && (
        <ConfirmDialog
          message={t("deleteDialog.message", { name: confirmDelete.name, email: confirmDelete.email })}
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
