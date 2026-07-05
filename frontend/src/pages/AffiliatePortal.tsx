import { useState, useEffect, FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";

interface AffiliateStats {
  id: string;
  name: string;
  email: string;
  code: string;
  status: string;
  commission_pct: number;
  total_earned: number;
  total_paid: number;
  payout_threshold: number;
  signups: number;
  conversions: number;
  pending_earnings: number;
  referral_link: string;
}

interface Referral {
  id: string;
  referred_company_email: string;
  status: string;
  commission_amount: number | null;
  signed_up_at: string;
  converted_at: string | null;
}

interface Payout {
  id: string;
  amount: number;
  paid_at: string;
  notes: string | null;
}

// ── Apply View ─────────────────────────────────────────────────────────────

function AffiliateApply() {
  const { t } = useTranslation("affiliate");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [website, setWebsite] = useState("");
  const [howTheyFoundUs, setHowTheyFoundUs] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const navigate = useNavigate();

  // Auto-generate code from name
  useEffect(() => {
    if (name) {
      const generated = name
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
      setCode(generated);
    }
  }, [name]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await axios.post("/api/affiliates/apply", {
        name: name.trim(),
        email: email.toLowerCase().trim(),
        code,
        website: website.trim() || null,
        how_they_found_us: howTheyFoundUs.trim() || null,
      });

      setSubmitted(true);
      setTimeout(() => {
        navigate("/affiliate/login");
      }, 3000);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("apply.failedSubmit")));
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "48px", marginBottom: "16px" }}>✅</div>
          <h1 className="auth-title">{t("apply.successTitle")}</h1>
          <p className="auth-subtitle">{t("apply.successSubtitle")}</p>
          <p style={{ marginTop: "16px", fontSize: "14px", color: "var(--text-secondary)" }}>
            {t("apply.successRedirect")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">{t("apply.title")}</h1>
        <p className="auth-subtitle">{t("apply.subtitle")}</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label className="field-label">
            {t("apply.nameLabel")} {t("apply.required")}
          </label>
          <input
            type="text"
            className="field-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("apply.namePlaceholder")}
            required
            disabled={loading}
            aria-label={t("apply.nameLabel")}
          />

          <label className="field-label">
            {t("apply.emailLabel")} {t("apply.required")}
          </label>
          <input
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("apply.emailPlaceholder")}
            required
            disabled={loading}
            aria-label={t("apply.emailLabel")}
          />

          <label className="field-label">
            {t("apply.codeLabel")} {t("apply.required")}
          </label>
          <input
            type="text"
            className="field-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toLowerCase())}
            placeholder={t("apply.codePlaceholder")}
            required
            disabled={loading}
            aria-label={t("apply.codeLabel")}
          />
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
            {t("apply.codeHint")}
          </p>

          <label className="field-label">
            {t("apply.websiteLabel")} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>{t("apply.optional")}</span>
          </label>
          <input
            type="url"
            className="field-input"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder={t("apply.websitePlaceholder")}
            disabled={loading}
            aria-label={t("apply.websiteLabel")}
          />

          <label className="field-label">
            {t("apply.howFoundLabel")} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>{t("apply.optional")}</span>
          </label>
          <textarea
            className="field-input"
            value={howTheyFoundUs}
            onChange={(e) => setHowTheyFoundUs(e.target.value)}
            placeholder={t("apply.howFoundPlaceholder")}
            style={{ minHeight: "80px", fontFamily: "inherit" }}
            disabled={loading}
            aria-label={t("apply.howFoundLabel")}
          />

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", marginTop: "16px" }}
            disabled={loading}
          >
            {loading ? t("apply.submitting") : t("apply.submit")}
          </button>
        </form>

        <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "16px", textAlign: "center" }}>
          {t("apply.alreadyApplied")}{" "}
          <a href="/affiliate/login" style={{ color: "var(--primary)", textDecoration: "none" }}>
            {t("apply.signInHere")}
          </a>
        </p>
      </div>
    </div>
  );
}

// ── Login View ─────────────────────────────────────────────────────────────

function AffiliateLogin() {
  const { t } = useTranslation("affiliate");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { saveToken } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await axios.post("/api/affiliates/login", {
        email: email.toLowerCase().trim(),
        code: code.toLowerCase().trim(),
      });

      saveToken(res.data.access_token, undefined);
      navigate("/affiliate/dashboard");
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.failedLogin")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">{t("login.title")}</h1>
        <p className="auth-subtitle">{t("login.subtitle")}</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label className="field-label">{t("login.emailLabel")}</label>
          <input
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("apply.emailPlaceholder")}
            required
            disabled={loading}
            aria-label={t("login.emailLabel")}
          />

          <label className="field-label">{t("login.codeLabel")}</label>
          <input
            type="text"
            className="field-input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t("apply.codePlaceholder")}
            required
            disabled={loading}
            aria-label={t("login.codeLabel")}
          />

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", marginTop: "16px" }}
            disabled={loading}
          >
            {loading ? t("login.signingIn") : t("login.signIn")}
          </button>
        </form>

        <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "16px", textAlign: "center" }}>
          {t("login.noAccount")}{" "}
          <a href="/affiliate/apply" style={{ color: "var(--primary)", textDecoration: "none" }}>
            {t("login.applyHere")}
          </a>
        </p>
      </div>
    </div>
  );
}

// ── Dashboard View ─────────────────────────────────────────────────────────

function AffiliateDashboard() {
  const { t, i18n } = useTranslation("affiliate");
  const [stats, setStats] = useState<AffiliateStats | null>(null);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const { token } = useAuth();

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    setLoading(true);
    setError("");
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [statsRes, referralsRes, payoutsRes] = await Promise.all([
        axios.get("/api/affiliates/me", { headers }),
        axios.get("/api/affiliates/me/referrals", { headers }),
        axios.get("/api/affiliates/me/payouts", { headers }).catch(() => null),
      ]);
      setStats(statsRes.data);
      setReferrals(referralsRes.data.referrals);
      setPayouts(payoutsRes?.data.payouts ?? []);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("dashboard.failedDashboard")));
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <div style={{ textAlign: "center", padding: "40px" }}>{t("dashboard.loading")}</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="dashboard-page">
        <div style={{ textAlign: "center", padding: "40px", color: "var(--danger)" }}>
          {error || t("dashboard.failedLoad")}
        </div>
      </div>
    );
  }

  function handleCopyLink() {
    navigator.clipboard.writeText(stats!.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const locale = i18n.language?.startsWith("fr") ? "fr-FR" : "en-GB";

  return (
    <div className="dashboard-page">
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "24px" }}>
        {/* Header */}
        <div style={{ marginBottom: "32px" }}>
          <h1 style={{ fontSize: "28px", fontWeight: 600, marginBottom: "8px" }}>
            {t("dashboard.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>
            {t("dashboard.welcomeBack", { name: stats.name })}
          </p>
          {stats.status !== "active" && (
            <div className="warning-banner" style={{ marginTop: "12px" }}>
              {t("dashboard.statusWarning", { status: stats.status })}
            </div>
          )}
        </div>

        {/* Referral Link Section */}
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            marginBottom: "24px",
          }}
        >
          <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "16px" }}>
            {t("dashboard.referralLinkTitle")}
          </h2>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="text"
              value={stats.referral_link}
              readOnly
              aria-label={t("dashboard.referralLinkTitle")}
              style={{
                flex: 1,
                padding: "10px 12px",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius)",
                fontFamily: "monospace",
                fontSize: "13px",
              }}
            />
            <button
              className="btn btn-primary"
              onClick={handleCopyLink}
              style={{ whiteSpace: "nowrap" }}
              aria-label={copied ? t("dashboard.copied") : t("dashboard.copy")}
            >
              {copied ? t("dashboard.copied") : t("dashboard.copy")}
            </button>
          </div>
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "8px" }}>
            {t("dashboard.commissionDesc", { commission: stats.commission_pct })}
          </p>
        </div>

        {/* Stats Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
          <StatCard label={t("dashboard.statsSignups")} value={stats.signups} />
          <StatCard label={t("dashboard.statsConversions")} value={stats.conversions} />
          <StatCard label={t("dashboard.statsTotalEarned")} value={`$${stats.total_earned.toFixed(2)}`} />
          <StatCard label={t("dashboard.statsPaidOut")} value={`$${stats.total_paid.toFixed(2)}`} />
          <StatCard
            label={t("dashboard.statsPending")}
            value={`$${stats.pending_earnings.toFixed(2)}`}
            highlight={stats.pending_earnings >= stats.payout_threshold}
          />
        </div>

        {/* Payout Info */}
        <div
          style={{
            background: "var(--brand-50)",
            border: "1px solid var(--brand-200)",
            borderRadius: "var(--radius-lg)",
            padding: "16px",
            marginBottom: "24px",
          }}
        >
          <p style={{ fontSize: "13px", color: "var(--text-primary)" }}>
            <strong>{t("dashboard.payoutThresholdLabel")}:</strong> ${stats.payout_threshold.toFixed(2)}
            <br />
            <strong>{t("dashboard.payoutStatusLabel")}:</strong>{" "}
            {stats.pending_earnings >= stats.payout_threshold
              ? t("dashboard.payoutReady")
              : t("dashboard.payoutUntil", { amount: (stats.payout_threshold - stats.pending_earnings).toFixed(2) })}
            <br />
            <strong>{t("dashboard.payoutRequestLabel")}:</strong>{" "}
            <a href="mailto:affiliates@qualipulse.com" style={{ color: "var(--primary)" }}>
              affiliates@qualipulse.com
            </a>
          </p>
        </div>

        {/* How It Works */}
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            padding: "24px",
            marginBottom: "24px",
          }}
        >
          <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "16px" }}>
            {t("dashboard.howItWorksTitle")}
          </h2>
          <ol style={{ paddingLeft: "20px", color: "var(--text-secondary)", lineHeight: "1.6" }}>
            <li>{t("dashboard.howItWorks1")}</li>
            <li>{t("dashboard.howItWorks2")}</li>
            <li>{t("dashboard.howItWorks3", { commission: stats.commission_pct })}</li>
            <li>{t("dashboard.howItWorks4", { threshold: stats.payout_threshold.toFixed(2) })}</li>
          </ol>
        </div>

        {/* Referrals Table */}
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "24px", borderBottom: "1px solid var(--border-default)" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 600 }}>{t("dashboard.recentReferrals")}</h2>
          </div>
          {referrals.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--text-secondary)" }}>
              {t("dashboard.noReferrals")}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border-default)" }}>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableEmail")}
                    </th>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableStatus")}
                    </th>
                    <th style={{ padding: "12px", textAlign: "right", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableCommission")}
                    </th>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableDate")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {referrals.map((ref) => (
                    <tr key={ref.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
                      <td style={{ padding: "12px", fontSize: "13px" }}>
                        {ref.referred_company_email.split("@")[0]}***
                      </td>
                      <td style={{ padding: "12px", fontSize: "13px" }}>
                        <span
                          style={{
                            background: ref.status === "converted" ? "var(--success-bg)" : "var(--warning-bg)",
                            color: ref.status === "converted" ? "var(--success)" : "var(--warning)",
                            padding: "4px 8px",
                            borderRadius: "4px",
                            fontSize: "11px",
                            fontWeight: 600,
                          }}
                        >
                          {ref.status}
                        </span>
                      </td>
                      <td style={{ padding: "12px", textAlign: "right", fontSize: "13px", fontWeight: 600 }}>
                        {ref.commission_amount ? `$${ref.commission_amount.toFixed(2)}` : "—"}
                      </td>
                      <td style={{ padding: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
                        {new Date(ref.signed_up_at).toLocaleDateString(locale)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Payout History */}
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
            marginTop: "24px",
          }}
        >
          <div style={{ padding: "24px", borderBottom: "1px solid var(--border-default)" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 600 }}>{t("dashboard.payoutHistory")}</h2>
          </div>
          {payouts.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--text-secondary)" }}>
              {t("dashboard.noPayouts")}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border-default)" }}>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableDate")}
                    </th>
                    <th style={{ padding: "12px", textAlign: "right", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableAmount")}
                    </th>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>
                      {t("dashboard.tableNotes")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {payouts.map((p) => (
                    <tr key={p.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
                      <td style={{ padding: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
                        {new Date(p.paid_at).toLocaleDateString(locale)}
                      </td>
                      <td style={{ padding: "12px", textAlign: "right", fontSize: "13px", fontWeight: 600 }}>
                        ${p.amount.toFixed(2)}
                      </td>
                      <td style={{ padding: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
                        {p.notes || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div
      style={{
        background: highlight ? "var(--brand-50)" : "var(--bg-surface)",
        border: `1px solid ${highlight ? "var(--brand-200)" : "var(--border-default)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "16px",
      }}
    >
      <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "8px" }}>{label}</p>
      <p style={{ fontSize: "24px", fontWeight: 600 }}>{value}</p>
    </div>
  );
}

// ── Router ─────────────────────────────────────────────────────────────────

export default function AffiliatePortal() {
  const { section } = useParams<{ section: string }>();

  switch (section) {
    case "apply":
      return <AffiliateApply />;
    case "login":
      return <AffiliateLogin />;
    case "dashboard":
      return <AffiliateDashboard />;
    default:
      return <AffiliateApply />;
  }
}
