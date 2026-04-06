import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, completeOnboarding, saveOnboardingProfile, resendVerification } from "../api/auth";
import type { CompanyResponse } from "../api/auth";
import { getErrorMessage } from "../utils/errorMessages";

const COMPANY_SIZES = ["Just me", "2-10", "11-50", "51-200", "201-1,000", "1,000+"];

const ROLES = [
  "UX Researcher",
  "Product Manager",
  "Designer",
  "Founder / CEO",
  "Marketing / Growth",
  "Consultant",
  "Academic Researcher",
  "Other",
];

const INDUSTRIES = [
  "Technology / SaaS",
  "Healthcare",
  "Finance / Fintech",
  "Education",
  "E-commerce / Retail",
  "Media / Publishing",
  "Consulting / Agency",
  "Non-profit",
  "Other",
];

const USE_CASES = [
  { label: "Customer discovery", emoji: "🔍" },
  { label: "User research", emoji: "🧪" },
  { label: "Market validation", emoji: "📊" },
  { label: "Employee feedback", emoji: "💬" },
  { label: "Academic research", emoji: "📚" },
  { label: "Something else", emoji: "✨" },
];

export default function Welcome() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: verify email, 2: about you, 3: use case, 4: ready
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  // Profile fields
  const [companyName, setCompanyName] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [role, setRole] = useState("");
  const [industry, setIndustry] = useState("");
  const [useCase, setUseCase] = useState("");

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCompanyName(data.name);
        // If already onboarded, go to dashboard
        if (data.onboarding_completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        // If email already verified, skip step 1
        if (data.email_verified) {
          setStep(2);
        }
        setLoading(false);
      })
      .catch(() => {
        navigate("/login", { replace: true });
      });
  }, [navigate]);

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

  async function handleSaveAndContinue() {
    // Intermediate save — persist Step 2 data without marking onboarding complete
    setSaving(true);
    setError("");
    try {
      await saveOnboardingProfile({
        name: companyName.trim() || undefined,
        company_size: companySize || undefined,
        role: role || undefined,
        industry: industry || undefined,
      });
      setStep(3);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to save. Please try again."));
    } finally {
      setSaving(false);
    }
  }

  async function handleCompleteOnboarding() {
    setSaving(true);
    setError("");
    try {
      await completeOnboarding({
        name: companyName.trim() || undefined,
        company_size: companySize || undefined,
        role: role || undefined,
        industry: industry || undefined,
        use_case: useCase || undefined,
      });
      setStep(4);
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

        {/* Progress indicator */}
        <div className="onboarding-progress">
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              className={`onboarding-progress-dot ${s <= step ? "active" : ""} ${s === step ? "current" : ""}`}
            />
          ))}
        </div>

        {error && <div className="error-banner" style={{ marginBottom: 20 }}>{error}</div>}

        {/* Step 1: Verify Email */}
        {step === 1 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">📧</div>
            <h1 className="welcome-title">Check your inbox</h1>
            <p className="welcome-subtitle">
              We sent a verification link to <strong>{me?.email}</strong>.
              Click it to verify your email, then come back here.
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
                {resendCooldown > 0 ? `Resend in ${resendCooldown}s (to prevent spam)` : "Resend verification email"}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)} style={{ fontSize: 13, color: "#9ca3af" }}>
                Skip for now
              </button>
            </div>
          </div>
        )}

        {/* Step 2: About you */}
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
                <label className="field-label">Team size</label>
                <div className="onboarding-chip-grid">
                  {COMPANY_SIZES.map((size) => (
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

              <div className="onboarding-field">
                <label className="field-label">Your role</label>
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
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button className="btn btn-primary btn-lg" onClick={handleSaveAndContinue}>
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Use case */}
        {step === 3 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">What will you use QualiPulse for?</h1>
            <p className="welcome-subtitle">Pick the one that best describes your first project.</p>

            <div className="welcome-usecase-grid" style={{ marginTop: 24, marginBottom: 32 }}>
              {USE_CASES.map((uc) => (
                <button
                  key={uc.label}
                  className={`welcome-usecase-chip ${useCase === uc.label ? "selected" : ""}`}
                  onClick={() => setUseCase(uc.label)}
                >
                  <span className="welcome-usecase-emoji">{uc.emoji}</span>
                  {uc.label}
                </button>
              ))}
            </div>

            <div className="welcome-actions">
              <button
                className="btn btn-primary btn-lg"
                onClick={handleCompleteOnboarding}
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

        {/* Step 4: Ready to go */}
        {step === 4 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">🎉</div>
            <h1 className="welcome-title">You're all set!</h1>
            <p className="welcome-subtitle">
              Here's how QualiPulse works — you'll have your first AI interview live in under 5 minutes.
            </p>

            <div className="welcome-steps">
              <div className="welcome-step">
                <div className="welcome-step-number">1</div>
                <div className="welcome-step-content">
                  <h3 className="welcome-step-title">Design your interview</h3>
                  <p className="welcome-step-desc">Paste a research brief or describe your goals — our AI builds a complete interview guide.</p>
                </div>
              </div>
              <div className="welcome-step">
                <div className="welcome-step-number">2</div>
                <div className="welcome-step-content">
                  <h3 className="welcome-step-title">Share & collect responses</h3>
                  <p className="welcome-step-desc">Generate a link. Participants complete the voice interview in their browser — no app needed.</p>
                </div>
              </div>
              <div className="welcome-step">
                <div className="welcome-step-number">3</div>
                <div className="welcome-step-content">
                  <h3 className="welcome-step-title">Analyse with AI</h3>
                  <p className="welcome-step-desc">Get themes, jobs-to-be-done, and recommendations — grounded in direct quotes.</p>
                </div>
              </div>
            </div>

            <div className="welcome-actions">
              <button className="btn btn-primary btn-lg" onClick={() => navigate("/projects/new")}>
                Create your first project →
              </button>
              <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>
                Explore the dashboard first
              </button>
            </div>

            <div className="welcome-trust">
              <span>Solo plan · 3 projects · 25 participants · No credit card needed</span>
            </div>
            {me?.trial_ends_at && (
              <div className="welcome-trust" style={{ marginTop: 4, color: "var(--primary)" }}>
                <span>🎉 14-day trial active — full Team features until {new Date(me.trial_ends_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
