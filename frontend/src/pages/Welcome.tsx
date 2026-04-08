import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  getMe,
  completeOnboarding,
  saveOnboardingProfile,
  resendVerification,
  analyseWebsite,
} from "../api/auth";
import type { CompanyResponse } from "../api/auth";
import { getErrorMessage } from "../utils/errorMessages";

const TEAM_SIZES = ["Just me", "2–10", "11–50", "50+"];

const ROLES = [
  "Researcher",
  "Product Manager",
  "Marketer",
  "Consultant",
  "Academic",
  "Founder",
  "Other",
];

const INDUSTRIES = [
  "Consumer Brands",
  "SaaS / Tech",
  "Agency",
  "Healthcare",
  "Academia",
  "Government",
  "Other",
];

const REGIONS = [
  { label: "Europe", value: "europe" },
  { label: "North America", value: "north_america" },
  { label: "APAC", value: "apac" },
  { label: "Global", value: "global" },
  { label: "Other", value: "other" },
];

const EXPERIENCE_OPTIONS = [
  {
    emoji: "🌱",
    title: "Brand new",
    subtitle: "I've never run research interviews before",
    value: "new",
  },
  {
    emoji: "📊",
    title: "Some experience",
    subtitle: "I've done a few projects",
    value: "some",
  },
  {
    emoji: "🎓",
    title: "Professional",
    subtitle: "It's a core part of my work",
    value: "professional",
  },
];

const STEP_LABELS = ["Verify", "Profile", "Business", "Experience", "Goals", "Ready"];

export default function Welcome() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  // Step 2 — Profile
  const [companyName, setCompanyName] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [role, setRole] = useState("");

  // Step 3 — Business
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [websiteLoading, setWebsiteLoading] = useState(false);
  const [businessSummary, setBusinessSummary] = useState("");
  const [industry, setIndustry] = useState("");
  const [primaryRegion, setPrimaryRegion] = useState("");

  // Step 5 — Goals
  const [goalsFreeform, setGoalsFreeform] = useState("");

  // Auto-poll for email verification
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCompanyName(data.name);
        if (data.onboarding_completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        if (data.email_verified) {
          setStep(2);
        }
        setLoading(false);
      })
      .catch(() => {
        navigate("/login", { replace: true });
      });
  }, [navigate]);

  // Auto-poll every 3s on step 1
  useEffect(() => {
    if (step !== 1) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const data = await getMe();
        if (data.email_verified) {
          if (pollRef.current) clearInterval(pollRef.current);
          setMe(data);
          setStep(2);
        }
      } catch {
        // ignore
      }
    }, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [step]);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  async function handleResendVerification() {
    if (resendCooldown > 0) return;
    try {
      await resendVerification();
      setResendCooldown(60);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to resend. Try again."));
    }
  }

  async function handleRefreshVerification() {
    try {
      const data = await getMe();
      setMe(data);
      if (data.email_verified) {
        setStep(2);
      } else {
        setError("Email not yet verified. Please check your inbox.");
      }
    } catch {
      // ignore
    }
  }

  // Step 2 → 3
  async function handleProfileContinue() {
    if (!role) {
      setError("Please select your role to continue.");
      return;
    }
    if (!companySize) {
      setError("Please select your team size to continue.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await saveOnboardingProfile({
        name: companyName.trim() || undefined,
        company_size: companySize || undefined,
        role: role || undefined,
      });
      setStep(3);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to save. Please try again."));
    } finally {
      setSaving(false);
    }
  }

  // Step 3 — Analyse website with AI
  async function handleAnalyseWebsite() {
    if (!websiteUrl.trim()) return;
    setWebsiteLoading(true);
    setError("");
    try {
      const { business_summary } = await analyseWebsite(websiteUrl.trim());
      setBusinessSummary(business_summary);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Could not analyse website. Please try again."));
    } finally {
      setWebsiteLoading(false);
    }
  }

  // Step 3 → 4
  async function handleBusinessContinue() {
    setSaving(true);
    setError("");
    try {
      await saveOnboardingProfile({
        website_url: websiteUrl.trim() || undefined,
        business_summary: businessSummary.trim() || undefined,
        industry: industry || undefined,
        primary_region: primaryRegion || undefined,
      });
      setStep(4);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to save. Please try again."));
    } finally {
      setSaving(false);
    }
  }

  // Step 4 — Research experience (auto-advance on click)
  async function handleExperienceSelect(value: string) {
    try {
      await saveOnboardingProfile({ research_experience: value });
    } catch {
      // non-critical, still advance
    }
    setStep(5);
  }

  // Step 5 → 6 (completes onboarding)
  async function handleGoalsContinue(skipGoals = false) {
    setSaving(true);
    setError("");
    try {
      await completeOnboarding({
        goals_freeform: skipGoals ? undefined : goalsFreeform.trim() || undefined,
      });
      setStep(6);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to save. Please try again."));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="welcome-page">
        <div className="welcome-container" style={{ textAlign: "center" }}>
          <div className="auth-logo">QualiPulse</div>
          <p style={{ color: "#6b7280" }}>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="welcome-page">
      <div className="welcome-container">
        <div className="auth-logo" style={{ textAlign: "center", marginBottom: 8 }}>QualiPulse</div>

        {/* Progress indicator — 6 steps */}
        <div className="onboarding-progress">
          {STEP_LABELS.map((label, i) => {
            const s = i + 1;
            return (
              <div key={s} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                <div
                  className={`onboarding-progress-dot ${s <= step ? "active" : ""} ${s === step ? "current" : ""}`}
                />
                <span style={{ fontSize: 10, color: s <= step ? "var(--primary, #6366f1)" : "var(--text-tertiary, #9ca3af)", whiteSpace: "nowrap" }}>
                  {label}
                </span>
              </div>
            );
          })}
        </div>

        {error && <div className="error-banner" style={{ marginBottom: 20 }}>{error}</div>}

        {/* ── Step 1: Verify Email ── */}
        {step === 1 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">📧</div>
            <h1 className="welcome-title">Check your inbox</h1>
            <p className="welcome-subtitle">
              We sent a verification link to <strong>{me?.email}</strong>.
              Click it to verify your email, then come back here.
            </p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8, marginBottom: 0 }}>
              Checking automatically...
            </p>
            <div className="welcome-actions">
              <button className="btn btn-primary btn-lg" onClick={handleRefreshVerification}>
                I've verified my email
              </button>
              <button
                className="btn btn-ghost"
                onClick={handleResendVerification}
                disabled={resendCooldown > 0}
              >
                {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend verification email"}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)} style={{ fontSize: 13, color: "#9ca3af" }}>
                Skip for now
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: About you ── */}
        {step === 2 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">Tell us about yourself</h1>
            <p className="welcome-subtitle">This helps us tailor QualiPulse to your needs.</p>

            <div className="onboarding-form">
              <div className="onboarding-field">
                <label className="field-label">Company or organization</label>
                <input
                  type="text"
                  className="field-input"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Acme Research"
                />
              </div>

              <div className="onboarding-field">
                <label className="field-label">Your role <span style={{ color: "var(--danger)" }}>*</span></label>
                <div className="onboarding-chip-grid">
                  {ROLES.map((r) => (
                    <button
                      key={r}
                      className={`onboarding-chip ${role === r ? "selected" : ""}`}
                      onClick={() => setRole(r)}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div className="onboarding-field">
                <label className="field-label">Team size <span style={{ color: "var(--danger)" }}>*</span></label>
                <div className="onboarding-chip-grid">
                  {TEAM_SIZES.map((size) => (
                    <button
                      key={size}
                      className={`onboarding-chip ${companySize === size ? "selected" : ""}`}
                      onClick={() => setCompanySize(size)}
                    >
                      {size}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleProfileContinue}
                disabled={saving}
              >
                {saving ? "Saving..." : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Your business ── */}
        {step === 3 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">Your business</h1>
            <p className="welcome-subtitle">Help us understand your company so we can personalise your experience.</p>

            <div className="onboarding-form">
              <div className="onboarding-field">
                <label className="field-label">Website URL <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    className="field-input"
                    value={websiteUrl}
                    onChange={(e) => setWebsiteUrl(e.target.value)}
                    placeholder="yourcompany.com"
                    style={{ flex: 1 }}
                    onKeyDown={(e) => { if (e.key === "Enter") handleAnalyseWebsite(); }}
                  />
                  <button
                    className="btn btn-secondary"
                    onClick={handleAnalyseWebsite}
                    disabled={websiteLoading || !websiteUrl.trim()}
                    style={{ whiteSpace: "nowrap", flexShrink: 0 }}
                  >
                    {websiteLoading ? (
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span className="spinner" style={{ width: 14, height: 14, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block", animation: "spin 0.6s linear infinite" }} />
                        Analysing...
                      </span>
                    ) : "Analyse with AI"}
                  </button>
                </div>
              </div>

              {businessSummary && (
                <div className="onboarding-field">
                  <label className="field-label">What we understood about your business — edit if needed</label>
                  <textarea
                    className="field-input"
                    value={businessSummary}
                    onChange={(e) => setBusinessSummary(e.target.value)}
                    rows={4}
                    style={{ resize: "vertical", lineHeight: 1.6 }}
                  />
                </div>
              )}

              <div className="onboarding-field">
                <label className="field-label">Industry</label>
                <div className="onboarding-chip-grid">
                  {INDUSTRIES.map((ind) => (
                    <button
                      key={ind}
                      className={`onboarding-chip ${industry === ind ? "selected" : ""}`}
                      onClick={() => setIndustry(ind)}
                    >
                      {ind}
                    </button>
                  ))}
                </div>
              </div>

              <div className="onboarding-field">
                <label className="field-label">Primary market</label>
                <div className="onboarding-chip-grid">
                  {REGIONS.map((r) => (
                    <button
                      key={r.value}
                      className={`onboarding-chip ${primaryRegion === r.value ? "selected" : ""}`}
                      onClick={() => setPrimaryRegion(r.value)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleBusinessContinue}
                disabled={saving}
              >
                {saving ? "Saving..." : "Continue"}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Research experience ── */}
        {step === 4 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">How familiar are you with qualitative research?</h1>
            <p className="welcome-subtitle">This helps us set the right defaults for you.</p>

            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 28, marginBottom: 8 }}>
              {EXPERIENCE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleExperienceSelect(opt.value)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "18px 20px",
                    border: "1.5px solid var(--border)",
                    borderRadius: "var(--radius)",
                    background: "var(--bg-surface)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "border-color 0.15s, background 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--primary)";
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--primary-subtle, #eef2ff)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-surface)";
                  }}
                >
                  <span style={{ fontSize: 28 }}>{opt.emoji}</span>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                      {opt.title}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                      {opt.subtitle}
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <div style={{ marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => setStep(3)}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {/* ── Step 5: Goals ── */}
        {step === 5 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">What do you want to learn from your participants?</h1>
            <p className="welcome-subtitle">Be as specific as you like — this helps us personalise your experience.</p>

            <div className="onboarding-form" style={{ marginTop: 24 }}>
              <div className="onboarding-field">
                <textarea
                  className="field-input"
                  value={goalsFreeform}
                  onChange={(e) => setGoalsFreeform(e.target.value)}
                  rows={5}
                  style={{ minHeight: 120, resize: "vertical", lineHeight: 1.6 }}
                  placeholder="e.g. We want to understand why users abandon checkout, what motivates B2B buyers to switch tools, or how remote workers manage their energy throughout the day..."
                />
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right", marginTop: 4 }}>
                  {goalsFreeform.length} characters
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 8 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={() => handleGoalsContinue(false)}
                disabled={saving}
              >
                {saving ? "Saving..." : "Continue"}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => handleGoalsContinue(true)}
                disabled={saving}
                style={{ fontSize: 13, color: "var(--text-muted)" }}
              >
                Skip for now
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(4)} style={{ fontSize: 13 }}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {/* ── Step 6: Ready ── */}
        {step === 6 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">🎉</div>
            <h1 className="welcome-title">You're all set!</h1>

            {me?.trial_ends_at && (
              <div
                style={{
                  background: "var(--primary-subtle, #eef2ff)",
                  border: "1px solid var(--primary-border, #c7d2fe)",
                  borderRadius: "var(--radius)",
                  padding: "12px 16px",
                  marginBottom: 24,
                  textAlign: "center",
                }}
              >
                <span style={{ fontWeight: 600, color: "var(--primary)" }}>
                  14-day trial active
                </span>
                <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                  {" "}— full Team features until {new Date(me.trial_ends_at).toLocaleDateString()}
                </span>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 28 }}>
              {[
                "AI-powered interview guide in minutes",
                "Voice interviews with real participants",
                "Instant analysis and insights",
              ].map((benefit) => (
                <div key={benefit} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: "var(--success, #16a34a)", fontWeight: 700, fontSize: 16 }}>✓</span>
                  <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>{benefit}</span>
                </div>
              ))}
            </div>

            <div className="welcome-actions">
              <button className="btn btn-primary btn-lg" onClick={() => navigate("/projects/new")}>
                Create my first project →
              </button>
              <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>
                Explore the dashboard first
              </button>
            </div>

            <div className="welcome-trust" style={{ marginTop: 16 }}>
              <span>Solo plan · 3 projects · 25 participants · No credit card needed</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
