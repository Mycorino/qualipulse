import { useState, useEffect, FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
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

// ââ Apply View ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

function AffiliateApply() {
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
      const res = await axios.post("/api/affiliates/apply", {
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
      setError(getErrorMessage(err, "Failed to submit application."));
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: "48px", marginBottom: "16px" }}>â</div>
          <h1 className="auth-title">Application Received</h1>
          <p className="auth-subtitle">
            Thank you! We'll review your application and get back to you within 2-3 business days.
          </p>
          <p style={{ marginTop: "16px", fontSize: "14px", color: "var(--text-secondary)" }}>
            Redirecting to login in a moment...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Become a QualiPulse Affiliate</h1>
        <p className="auth-subtitle">Earn up to 20% recurring commission on referrals</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label className="field-label">Your Name *</label>
          <input
            type="text"
            className="field-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jane Doe"
            required
            disabled={loading}
          />

          <label className="field-label">Email *</label>
          <input
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="jane@example.com"
            required
            disabled={loading}
          />

          <label className="field-label">Affiliate Code *</label>
          <input
            type="text"
            className="field-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toLowerCase())}
            placeholder="jane-doe"
            required
            disabled={loading}
          />
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Lowercase letters, numbers, hyphens only. Auto-generated from your name.
          </p>

          <label className="field-label">Website (optional)</label>
          <input
            type="url"
            className="field-input"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="https://yourwebsite.com"
            disabled={loading}
          />

          <label className="field-label">How did you find us? (optional)</label>
          <textarea
            className="field-input"
            value={howTheyFoundUs}
            onChange={(e) => setHowTheyFoundUs(e.target.value)}
            placeholder="Tell us about your audience..."
            style={{ minHeight: "80px", fontFamily: "inherit" }}
            disabled={loading}
          />

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", marginTop: "16px" }}
            disabled={loading}
          >
            {loading ? "Submitting..." : "Submit Application"}
          </button>
        </form>

        <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "16px", textAlign: "center" }}>
          Already applied?{" "}
          <a href="/affiliate/login" style={{ color: "var(--primary)", textDecoration: "none" }}>
            Sign in here
          </a>
        </p>
      </div>
    </div>
  );
}

// ââ Login View ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

function AffiliateLogin() {
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
      setError(getErrorMessage(err, "Invalid email or code."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Affiliate Sign In</h1>
        <p className="auth-subtitle">Access your affiliate dashboard</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <label className="field-label">Email</label>
          <input
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="jane@example.com"
            required
            disabled={loading}
          />

          <label className="field-label">Affiliate Code</label>
          <input
            type="text"
            className="field-input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="jane-doe"
            required
            disabled={loading}
          />

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", marginTop: "16px" }}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "16px", textAlign: "center" }}>
          Don't have an account?{" "}
          <a href="/affiliate/apply" style={{ color: "var(--primary)", textDecoration: "none" }}>
            Apply here
          </a>
        </p>
      </div>
    </div>
  );
}

// ââ Dashboard View ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

function AffiliateDashboard() {
  const [stats, setStats] = useState<AffiliateStats | null>(null);
  const [referrals, setReferrals] = useState<Referral[]>([]);
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
      const [statsRes, referralsRes] = await Promise.all([
        axios.get("/api/affiliates/me", { headers }),
        axios.get("/api/affiliates/me/referrals", { headers }),
      ]);
      setStats(statsRes.data);
      setReferrals(referralsRes.data.referrals);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to load dashboard."));
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <div style={{ textAlign: "center", padding: "40px" }}>Loading...</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="dashboard-page">
        <div style={{ textAlign: "center", padding: "40px", color: "var(--danger)" }}>
          {error || "Failed to load affiliate data."}
        </div>
      </div>
    );
  }

  function handleCopyLink() {
    navigator.clipboard.writeText(stats.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="dashboard-page">
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "24px" }}>
        {/* Header */}
        <div style={{ marginBottom: "32px" }}>
          <h1 style={{ fontSize: "28px", fontWeight: 600, marginBottom: "8px" }}>Affiliate Dashboard</h1>
          <p style={{ color: "var(--text-secondary)" }}>Welcome back, {stats.name}!</p>
          {stats.status !== "active" && (
            <div className="warning-banner" style={{ marginTop: "12px" }}>
              Your account is {stats.status}. Contact support if you have questions.
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
          <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "16px" }}>Your Referral Link</h2>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="text"
              value={stats.referral_link}
              readOnly
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
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "8px" }}>
            Share this link with your audience to earn {stats.commission_pct}% commission on their subscription.
          </p>
        </div>

        {/* Stats Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
          <StatCard label="Signups" value={stats.signups} />
          <StatCard label="Conversions" value={stats.conversions} />
          <StatCard label="Total Earned" value={`$${stats.total_earned.toFixed(2)}`} />
          <StatCard label="Paid Out" value={`$${stats.total_paid.toFixed(2)}`} />
          <StatCard label="Pending" value={`$${stats.pending_earnings.toFixed(2)}`} highlight={stats.pending_earnings >= stats.payout_threshold} />
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
            <strong>Payout Threshold:</strong> ${stats.payout_threshold.toFixed(2)}
            <br />
            <strong>Status:</strong> {stats.pending_earnings >= stats.payout_threshold ? "Ready for payout" : `${(stats.payout_threshold - stats.pending_earnings).toFixed(2)} until eligible`}
            <br />
            <strong>Request payouts:</strong> <a href="mailto:affiliates@qualipulse.com" style={{ color: "var(--primary)" }}>affiliates@qualipulse.com</a>
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
          <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "16px" }}>How It Works</h2>
          <ol style={{ paddingLeft: "20px", color: "var(--text-secondary)", lineHeight: "1.6" }}>
            <li>Share your referral link with your audience</li>
            <li>When someone signs up using your link, you get credit</li>
            <li>When they convert to a paid subscription, you earn {stats.commission_pct}% of the subscription value</li>
            <li>Request payout once you reach ${stats.payout_threshold.toFixed(2)}</li>
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
            <h2 style={{ fontSize: "16px", fontWeight: 600 }}>Recent Referrals</h2>
          </div>
          {referrals.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "var(--text-secondary)" }}>
              No referrals yet. Share your link to get started!
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--bg-sunken)", borderBottom: "1px solid var(--border-default)" }}>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>Email</th>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>Status</th>
                    <th style={{ padding: "12px", textAlign: "right", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>Commission</th>
                    <th style={{ padding: "12px", textAlign: "left", fontWeight: 600, fontSize: "12px", color: "var(--text-secondary)" }}>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {referrals.map((ref) => (
                    <tr key={ref.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
                      <td style={{ padding: "12px", fontSize: "13px" }}>{ref.referred_company_email.split("@")[0]}***</td>
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
                        {ref.commission_amount ? `$${ref.commission_amount.toFixed(2)}` : "â"}
                      </td>
                      <td style={{ padding: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
                        {new Date(ref.signed_up_at).toLocaleDateString()}
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

// ââ Router ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

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
