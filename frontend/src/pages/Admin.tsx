import { Fragment, useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";
import AdminBlog from "./AdminBlog";
import { AdminGate, StepUpDialog, type AdminSession } from "./admin/AdminGate";
import AdminOverview from "./admin/AdminOverview";
import AdminCosts from "./admin/AdminCosts";
import "./admin/admin.css";
import { BarChart, Card, Kpi, WindowPicker } from "./admin/ui";

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
  plan_id?: string | null;
  plan_name?: string | null;
  plan_is_legacy?: boolean | null;
  credits_available?: number | null;
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

interface CompanyCost {
  company_id: string;
  total_cost_usd: number;
  window_cost_usd: number;
  window_cost_per_interview_usd: number | null;
}

interface TrafficBucket {
  label: string;
  count: number;
}

interface AdminTraffic {
  days: number;
  page_views: number;
  /** Visits, not people: the visitor hash rotates daily by design. */
  visits: number;
  cta_clicks: number;
  pricing_views: number;
  signups: number;
  signup_rate_pct: number;
  cta_by_location: TrafficBucket[];
  top_paths: TrafficBucket[];
  top_referrers: TrafficBucket[];
  top_sources: TrafficBucket[];
  signups_by_source: TrafficBucket[];
  paid_by_source: TrafficBucket[];
  daily: { date: string; page_views: number; signups: number }[];
}

interface CostsReport {
  by_company: CompanyCost[];
}

type AdminTab = "overview" | "costs" | "users" | "traffic" | "affiliates" | "blog" | "audit" | "panel";

// ── API helpers ────────────────────────────────────────────────────────────

function adminClient(session: AdminSession | null, stepUpCode?: string) {
  const headers: Record<string, string> = {};
  if (session) {
    headers.Authorization = `Bearer ${session.token}`;
    // Only meaningful on the legacy shared-key path; ignored by the server
    // for account sessions, whose identity is the verified email.
    if (session.via === "shared_key") headers["X-Admin-Identity"] = session.identity.replace(/^shared-key:/, "");
  }
  if (stepUpCode) headers["X-Admin-Step-Up"] = stepUpCode;
  return axios.create({ baseURL: "/api", headers });
}

/** Server signal that a destructive call needs (or got a bad) fresh code. */
function stepUpDetail(err: unknown): "required" | "invalid" | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 403) return null;
  const d = err.response?.data?.detail;
  return d === "admin_step_up_required" ? "required" : d === "admin_step_up_invalid" ? "invalid" : null;
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

// ── Stat card ──────────────────────────────────────────────────────────────

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
  // Admin session lives in memory only (never storage): a refresh asks for a
  // new authenticator code, which is the point.
  const [session, setSession] = useState<AdminSession | null>(null);
  const [gateNotice, setGateNotice] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const authed = session !== null;
  const adminIdentity = session?.identity ?? "";

  // Step-up: destructive actions ask for a fresh code through this promise.
  const [stepUp, setStepUp] = useState<{ action: string; error: string | null; busy: boolean } | null>(null);
  const stepUpResolver = useRef<((code: string | null) => void) | null>(null);

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

  const [tab, setTab] = useState<AdminTab>("overview");
  const [costWorkspaceId, setCostWorkspaceId] = useState<string | null>(null);
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
      const res = await withStepUp("Deleting a panelist", (c) =>
        c.delete(`/admin/panel/${encodeURIComponent(email)}`, { params: { include_interviews: panelIncludeInterviews } }),
      );
      setStepUp(null);
      if (!res) return;
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

  const signOut = useCallback((notice?: string) => {
    setSession(null);
    setGateNotice(notice ?? null);
  }, []);

  const client = useCallback(() => {
    const c = adminClient(session);
    // A 401 means the admin token expired or was revoked: back to the gate.
    c.interceptors.response.use(undefined, (err) => {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        signOut(t("login.sessionExpired", "Your admin session expired. Enter a new code to continue."));
      }
      return Promise.reject(err);
    });
    return c;
  }, [session, signOut, t]);

  // Countdown for the header + auto sign-out at expiry.
  useEffect(() => {
    if (!session?.expiresAt) return;
    const id = setInterval(() => {
      setNow(Date.now());
      if (session.expiresAt && Date.now() >= session.expiresAt) {
        signOut(t("login.sessionExpired", "Your admin session expired. Enter a new code to continue."));
      }
    }, 15_000);
    return () => clearInterval(id);
  }, [session, signOut, t]);

  /** Run a destructive call, prompting for a fresh authenticator code when
   *  the server asks for one. Resolves to null if the admin cancels. */
  const withStepUp = useCallback(
    async <T,>(action: string, run: (c: ReturnType<typeof adminClient>) => Promise<T>): Promise<T | null> => {
      let code: string | undefined;
      for (;;) {
        try {
          return await run(adminClient(session, code));
        } catch (err) {
          const kind = stepUpDetail(err);
          if (!kind) throw err;
          const next = await new Promise<string | null>((resolve) => {
            stepUpResolver.current = resolve;
            setStepUp({ action, error: kind === "invalid" ? t("stepUp.invalid", "That code is not valid.") : null, busy: false });
          });
          if (next === null) {
            setStepUp(null);
            return null;
          }
          code = next;
          setStepUp((s) => (s ? { ...s, busy: true, error: null } : s));
        }
      }
    },
    [session, t],
  );

  const finishStepUp = (code: string | null) => {
    const resolve = stepUpResolver.current;
    stepUpResolver.current = null;
    if (code !== null) setStepUp((s) => (s ? { ...s, busy: true } : s));
    else setStepUp(null);
    resolve?.(code);
  };

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

  const [traffic, setTraffic] = useState<AdminTraffic | null>(null);
  const [trafficDays, setTrafficDays] = useState(30);
  const [trafficLoading, setTrafficLoading] = useState(false);

  const loadTraffic = useCallback(async () => {
    setTrafficLoading(true);
    try {
      const res = await client().get<AdminTraffic>("/admin/traffic", {
        params: { days: trafficDays },
      });
      setTraffic(res.data);
    } catch {
      setError("Failed to load traffic");
    } finally {
      setTrafficLoading(false);
    }
  }, [client, trafficDays]);

  const loadCosts = useCallback(async () => {
    try {
      const res = await client().get<CostsReport>("/admin/costs", { params: { days: 30 } });
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

  const loadAuditLog = useCallback(async (page = 1) => {
    setAuditLoading(true);
    try {
      const params: Record<string, string | number> = { page, limit: 50 };
      if (auditAction) params.action = auditAction;
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
        loadCosts();
      } else if (tab === "affiliates") {
        loadAffiliates();
      } else if (tab === "audit") {
        loadAuditLog(1);
      } else if (tab === "traffic") {
        loadTraffic();
      }
    }
  }, [authed, search, tierFilter, userPage, tab, trafficDays]); // eslint-disable-line react-hooks/exhaustive-deps

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

  async function handlePlanChange(user: AdminUser, planId: string) {
    setActionLoading(`plan-${user.id}`);
    try {
      const { data } = await client().patch<AdminUser>(
        `/admin/users/${user.id}/plan`,
        { plan_id: planId }
      );
      // The endpoint returns the fully re-resolved summary — use it so the
      // real plan name, credits, and synced tier all refresh together.
      setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, ...data } : u)));
      showSuccess(t("toasts.planUpdated"));
    } catch {
      setError(t("toasts.planUpdateFailed"));
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
      const done = await withStepUp(t("stepUp.actions.credits", "Adjusting credits"), (c) =>
        c.post(`/admin/workspaces/${creditDialog.id}/credits/adjust`, { credits_delta: delta, reason: creditReason.trim() }),
      );
      setStepUp(null);
      if (!done) return;
      showSuccess(
        t(delta > 0 ? "toasts.creditsGranted" : "toasts.creditsClawedBack", {
          count: Math.abs(delta),
        })
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
      const done = await withStepUp(t("stepUp.actions.delete", "Deleting an account"), (c) => c.delete(`/admin/users/${user.id}`));
      setStepUp(null);
      if (!done) return;
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
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
      const res = await withStepUp(t("stepUp.actions.suspend", "Suspending an account"), (c) =>
        c.post<AdminUser>(`/admin/users/${suspendDialog.id}/suspend`, { reason: suspendReason.trim() }),
      );
      setStepUp(null);
      if (!res) return;
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
      const res = await withStepUp(t("stepUp.actions.impersonate", "Impersonating a customer"), (c) =>
        c.post<{ access_token: string; company_name: string; company_email: string }>(`/admin/users/${user.id}/impersonate`),
      );
      setStepUp(null);
      if (!res) return;
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

  if (!session) {
    return <AdminGate notice={gateNotice} onSession={(sess) => { setGateNotice(null); setSession(sess); }} />;
  }

  // ── Main admin UI ─────────────────────────────────────────────────────────

  const tabs: { id: AdminTab; label: string; count?: number }[] = [
    { id: "overview", label: t("tabs.overview", "Overview") },
    { id: "costs", label: t("tabs.costs", "AI spend") },
    { id: "users", label: t("tabs.users") },
    { id: "traffic", label: t("tabs.traffic", "Traffic") },
    { id: "affiliates", label: t("tabs.affiliates"), count: pendingAffiliateCount },
    { id: "blog", label: t("tabs.blog") },
    { id: "audit", label: t("tabs.audit") },
    { id: "panel", label: t("tabs.panel") },
  ];

  const openWorkspaceCosts = (companyId: string) => {
    setTab("costs");
    setCostWorkspaceId(companyId);
  };

  return (
    <div className="adm-page">
      <header className="adm-header">
        <div className="adm-header__brand">
          <span>{t("header.title")}</span>
          <span className="adm-header__badge">{t("header.internalBadge")}</span>
        </div>
        <div className="adm-header__meta">
          <span className="adm-session" title={session.via === "shared_key" ? t("header.sharedKeySession", "Shared-key session (legacy)") : undefined}>
            <i className={`adm-session__dot${session.expiresAt && session.expiresAt - now < 5 * 60_000 ? " adm-session__dot--warn" : ""}`} />
            {session.via === "shared_key" ? adminIdentity.replace(/^shared-key:/, "") : adminIdentity}
            {session.expiresAt && (
              <span>
                · {t("header.expiresIn", "{{minutes}} min left", { minutes: Math.max(0, Math.ceil((session.expiresAt - now) / 60_000)) })}
              </span>
            )}
          </span>
          <button type="button" onClick={() => signOut()}>
            {t("header.signOut")}
          </button>
        </div>
      </header>

      <nav className="adm-tabs" role="tablist">
        {tabs.map((tb) => (
          <button key={tb.id} type="button" role="tab" className="adm-tab" aria-selected={tab === tb.id} onClick={() => setTab(tb.id)}>
            {tb.label}
            {tb.count ? (
              <span className="adm-tab__count" title={t("affiliates.pendingBadgeTitle", { count: tb.count })}>{tb.count}</span>
            ) : null}
          </button>
        ))}
      </nav>

      <div className="adm-main">
        {tab === "overview" && <AdminOverview client={client} onOpenWorkspace={openWorkspaceCosts} />}
        {tab === "costs" && (
          <AdminCosts
            client={client}
            openWorkspaceId={costWorkspaceId}
            onOpenWorkspace={setCostWorkspaceId}
            onCloseWorkspace={() => setCostWorkspaceId(null)}
          />
        )}

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
              gridTemplateColumns: "2fr 2fr 1.4fr 0.8fr 1.2fr 1.6fr",
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
                  gridTemplateColumns: "2fr 2fr 1.4fr 0.8fr 1.2fr 1.6fr",
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

                {/* Plan / Tier */}
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {user.plan_id && !user.plan_is_legacy ? (
                    <>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                        {user.plan_name}
                      </span>
                      {user.credits_available != null && (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          {t("users.creditsLabel", { count: user.credits_available })}
                        </span>
                      )}
                    </>
                  ) : (
                    <TierBadge tier={user.subscription_tier} />
                  )}
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
                  {/* Plan selector (credits-based — the real subscription) */}
                  <select
                    value={user.plan_is_legacy ? "" : user.plan_id ?? ""}
                    disabled={actionLoading === `plan-${user.id}`}
                    onChange={(e) => {
                      if (e.target.value) handlePlanChange(user, e.target.value);
                    }}
                    title={t("users.planSelectTitle")}
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
                    <option value="" disabled>
                      {t("users.planOption")}
                    </option>
                    <option value="trial">{t("users.planTrial")}</option>
                    <option value="exploration">{t("users.planExploration")}</option>
                    <option value="team">{t("users.planTeam")}</option>
                    <option value="agency">{t("users.planAgency")}</option>
                    <option value="enterprise">{t("users.planEnterprise")}</option>
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
                          ${co.total_cost_usd.toFixed(2)}
                        </span>{" "}
                        {t("users.aiSpendTotal")} ·{" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                          ${co.window_cost_usd.toFixed(2)}
                        </span>{" "}
                        {t("users.aiSpend30d", "last 30 days")}
                        {co.window_cost_per_interview_usd != null && (
                          <> · <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>${co.window_cost_per_interview_usd.toFixed(3)}</span> {t("users.aiSpendPerInterview", "per interview")}</>
                        )}
                        {" "}
                        <button type="button" className="adm-link" onClick={() => openWorkspaceCosts(user.id)} style={{ marginLeft: 6, fontSize: 12 }}>
                          {t("users.costBreakdown", "Cost breakdown →")}
                        </button>
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
        {tab === "blog" && <AdminBlog adminKey={session.token} />}

        {/* Audit log tab */}
        {tab === "audit" && (
          <div>
            <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "center" }}>
              <select
                value={auditAction}
                onChange={(e) => { setAuditAction(e.target.value); loadAuditLog(1); }}
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
                <option value="trial_update">{t("audit.actionTrialUpdate")}</option>
                <option value="credit_adjustment">{t("audit.actionCreditAdjustment")}</option>
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

        {/* Traffic tab */}
        {tab === "traffic" && (
          <div>
            <div className="adm-toolbar">
              <div>
                <h2>{t("traffic.title", "Marketing funnel")}</h2>
                <div className="adm-toolbar__hint">
                  {t("traffic.hint", "First-party events from the marketing site, stitched to signups by first-touch attribution.")}
                  {trafficLoading && <> · {t("traffic.loading", "Loading…")}</>}
                </div>
              </div>
              <WindowPicker value={trafficDays} onChange={setTrafficDays} options={[7, 30, 90]} labels={(d) => t("overview.windowDays", "{{n}}d", { n: d })} />
            </div>

            {traffic && traffic.page_views === 0 && (
              <p
                style={{
                  fontSize: 13,
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                  marginBottom: 20,
                  padding: "10px 12px",
                  background: "var(--bg-subtle, #f8fafc)",
                  borderRadius: "var(--radius-xs)",
                }}
              >
                {t(
                  "traffic.empty",
                  "No pageviews recorded yet. Events start landing once the analytics build is deployed and someone visits the marketing site."
                )}
              </p>
            )}

            {traffic && (
              <>
                <div className="adm-grid adm-grid--kpi">
                  <Kpi label={t("traffic.pageViews", "Pageviews")} value={traffic.page_views.toLocaleString()} />
                  <Kpi label={t("traffic.visits", "Visits")} value={traffic.visits.toLocaleString()} hint={t("traffic.visitsHint", "Not unique people: the visitor hash rotates daily.")} />
                  <Kpi label={t("traffic.pricingViews", "Pricing viewed")} value={traffic.pricing_views.toLocaleString()} />
                  <Kpi label={t("traffic.ctaClicks", "Signup CTA clicks")} value={traffic.cta_clicks.toLocaleString()} />
                  <Kpi label={t("traffic.signups", "Signups")} value={traffic.signups.toLocaleString()} />
                  <Kpi label={t("traffic.conversion", "Signup rate")} value={`${traffic.signup_rate_pct}%`} accent />
                </div>

                {traffic.daily.length > 0 && (
                  <Card title={t("traffic.dailyTitle", "Pageviews and signups per day")} className="adm-grid">
                    <BarChart
                      data={traffic.daily}
                      mode="overlay"
                      series={[
                        { key: "page_views", label: t("traffic.pageViews", "Pageviews"), tone: "muted" },
                        { key: "signups", label: t("traffic.signups", "Signups"), tone: "primary" },
                      ]}
                    />
                  </Card>
                )}

                <div className="adm-grid adm-grid--3">
                  <BucketTable
                    title={t("traffic.byCta", "Which CTA earns the click")}
                    rows={traffic.cta_by_location}
                  />
                  <BucketTable
                    title={t("traffic.bySource", "Visits by channel")}
                    rows={traffic.top_sources}
                  />
                  <BucketTable
                    title={t("traffic.signupsBySource", "Signups by channel")}
                    rows={traffic.signups_by_source}
                  />
                  <BucketTable
                    title={t("traffic.paidBySource", "Paying customers by channel")}
                    rows={traffic.paid_by_source}
                    note={t("traffic.paidNote", "All time, not windowed: first touch keeps its credit however long the deal takes.")}
                  />
                  <BucketTable
                    title={t("traffic.topReferrers", "Top referrers")}
                    rows={traffic.top_referrers}
                  />
                  <BucketTable title={t("traffic.topPaths", "Top pages")} rows={traffic.top_paths} />
                </div>
              </>
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

      {stepUp && (
        <StepUpDialog
          action={stepUp.action}
          error={stepUp.error}
          busy={stepUp.busy}
          onSubmit={(code) => finishStepUp(code)}
          onCancel={() => finishStepUp(null)}
        />
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

/* ---- Traffic tab presentation ---- */

function BucketTable({
  title,
  rows,
  note,
}: {
  title: string;
  rows: { label: string; count: number }[];
  note?: string;
}) {
  const total = rows.reduce((sum, r) => sum + r.count, 0);
  const max = Math.max(0, ...rows.map((r) => r.count));
  return (
    <Card title={title} sub={note}>
      {rows.length === 0 ? (
        <div className="adm-empty">-</div>
      ) : (
        <div className="adm-table-wrap">
          <table className="adm-table">
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className="bar-cell" style={{ wordBreak: "break-all" }}>
                    <i style={{ width: `${max ? (100 * r.count) / max : 0}%` }} />
                    <span>{r.label}</span>
                  </td>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>
                    <span className="primary">{r.count.toLocaleString()}</span>
                    {total > 0 && <span className="dim" style={{ marginLeft: 6 }}>{Math.round((r.count / total) * 100)}%</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
