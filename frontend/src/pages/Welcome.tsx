import { useState, useEffect, useRef, type ClipboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getMe,
  completeOnboarding,
  saveOnboardingProfile,
  resendVerification,
  analyseWebsite,
} from "../api/auth";
import type { CompanyResponse } from "../api/auth";
import { setCachedOnboarded } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";

const TEAM_SIZE_VALUES = ["Just me", "2–10", "11–50", "50+"];
const ROLE_VALUES = ["Researcher", "Product Manager", "Marketer", "Consultant", "Academic", "Founder", "Other"];
const INDUSTRY_VALUES = ["Consumer Brands", "SaaS / Tech", "Agency", "Healthcare", "Academia", "Government", "Other"];
const REGION_VALUES = [
  { value: "europe" },
  { value: "north_america" },
  { value: "apac" },
  { value: "global" },
  { value: "other" },
];
const EXPERIENCE_VALUES = ["new", "some", "professional"] as const;

export default function Welcome() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation("auth");
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
  // Index of the cycling progress message shown while websiteLoading is true
  // ("Reading your site…" → "Understanding your business…" → …).
  const [websiteProgressStep, setWebsiteProgressStep] = useState(0);
  const [businessSummary, setBusinessSummary] = useState("");
  const [industry, setIndustry] = useState("");
  const [primaryRegion, setPrimaryRegion] = useState("");
  // URL we successfully analysed (so we can show a "regenerate" button if
  // the user changes the URL after a successful analysis).
  const [analysedUrl, setAnalysedUrl] = useState("");
  // URL we last *attempted* to analyse — including failures. Used to skip
  // the auto-trigger debounce when the user re-types the same broken URL.
  const lastAttemptedUrlRef = useRef<string>("");
  // Extra industry chips Claude classified into that weren't in the static
  // list — rendered alongside the predefined chips.
  const [customIndustries, setCustomIndustries] = useState<string[]>([]);
  // User can tap "no website, describe manually" to force the textarea open
  // without going through the analyser.
  const [manualMode, setManualMode] = useState(false);
  // After an AI-generated summary arrives, the user must explicitly
  // confirm it before the Continue button unlocks. In manual mode this
  // is implicitly true because the user typed it themselves.
  const [summaryConfirmed, setSummaryConfirmed] = useState(false);
  // Debounce auto-analyse so we don't fire on every keystroke.
  const analyseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Step 5 — Goals
  const [goalsFreeform, setGoalsFreeform] = useState("");

  // Translated option arrays (re-read on language change)
  const teamSizeLabels = t("onboarding.teamSizes", { returnObjects: true }) as string[];
  const roleLabels = t("onboarding.roles", { returnObjects: true }) as string[];
  const industryLabels = t("onboarding.industries", { returnObjects: true }) as string[];
  const regionLabels = t("onboarding.regions", { returnObjects: true }) as string[];

  const STEP_LABELS = [
    t("onboarding.stepVerify"),
    t("onboarding.stepProfile"),
    t("onboarding.stepBusiness"),
    t("onboarding.stepExperience"),
    t("onboarding.stepGoals"),
    t("onboarding.stepReady"),
  ];

  const EXPERIENCE_OPTIONS = [
    { emoji: "🌱", title: t("onboarding.expTitle_new"), subtitle: t("onboarding.expSub_new"), value: "new" as const },
    { emoji: "📊", title: t("onboarding.expTitle_some"), subtitle: t("onboarding.expSub_some"), value: "some" as const },
    { emoji: "🎓", title: t("onboarding.expTitle_professional"), subtitle: t("onboarding.expSub_professional"), value: "professional" as const },
  ];

  // Auto-poll for email verification
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCompanyName(data.name);
        setCachedOnboarded(!!data.onboarding_completed);
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
    const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  async function handleResendVerification() {
    if (resendCooldown > 0) return;
    try {
      await resendVerification();
      setResendCooldown(60);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedResend")));
    }
  }

  async function handleRefreshVerification() {
    try {
      const data = await getMe();
      setMe(data);
      if (data.email_verified) {
        setStep(2);
      } else {
        setError(t("onboarding.notYetVerified"));
      }
    } catch {
      // ignore
    }
  }

  // Step 2 → 3
  async function handleProfileContinue() {
    if (!role) {
      setError(t("onboarding.profileRoleRequired"));
      return;
    }
    if (!companySize) {
      setError(t("onboarding.profileTeamRequired"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      // Normalise the live UI locale into a 2-letter code we persist as the
      // account's preferred_language. This is what the AI research wizard
      // and email service will read for every future generation.
      const uiLang = (i18n.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
      await saveOnboardingProfile({
        name: companyName.trim() || undefined,
        company_size: companySize || undefined,
        role: role || undefined,
        preferred_language: uiLang,
      });
      setStep(3);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedSave")));
    } finally {
      setSaving(false);
    }
  }

  // Step 3 — Analyse website with AI
  async function handleAnalyseWebsite() {
    const trimmed = websiteUrl.trim();
    if (!trimmed) return;
    // Cancel any pending debounced call so we don't double-fire.
    if (analyseTimeoutRef.current) {
      clearTimeout(analyseTimeoutRef.current);
      analyseTimeoutRef.current = null;
    }
    lastAttemptedUrlRef.current = trimmed;
    setWebsiteLoading(true);
    setWebsiteProgressStep(0);
    setError("");
    // Fresh result — require the user to explicitly confirm before
    // the Continue button unlocks.
    setSummaryConfirmed(false);
    try {
      const { business_summary, industry: detectedIndustry } =
        await analyseWebsite(trimmed);
      setBusinessSummary(business_summary);
      setAnalysedUrl(trimmed);
      setManualMode(false);

      // Auto-select the industry chip. If Claude returned a label that
      // isn't in the predefined list, add it as a custom chip so the user
      // sees it preselected and can still change it.
      if (detectedIndustry) {
        const known = INDUSTRY_VALUES.some(
          (v) => v.toLowerCase() === detectedIndustry.toLowerCase(),
        );
        if (known) {
          // Use the canonical casing from INDUSTRY_VALUES
          const canonical =
            INDUSTRY_VALUES.find(
              (v) => v.toLowerCase() === detectedIndustry.toLowerCase(),
            ) ?? detectedIndustry;
          setIndustry(canonical);
        } else {
          setCustomIndustries((prev) =>
            prev.some((v) => v.toLowerCase() === detectedIndustry.toLowerCase())
              ? prev
              : [...prev, detectedIndustry],
          );
          setIndustry(detectedIndustry);
        }
      }
    } catch (err: unknown) {
      // The backend returns { detail: { code, message } } for scraper
      // failures — translate the code rather than surfacing the English
      // fallback message from the server.
      const detail = (err as {
        response?: { data?: { detail?: { code?: string } | string } };
      })?.response?.data?.detail;
      const code =
        typeof detail === "object" && detail !== null ? detail.code : undefined;
      if (code) {
        setError(t(`onboarding.scraperError_${code}`, { defaultValue: t("onboarding.failedWebsite") }));
      } else {
        setError(getErrorMessage(err, t("onboarding.failedWebsite")));
      }
      // On failure, open the manual textarea so the user has a clear next
      // step (type it themselves) instead of being stuck on the URL input.
      setManualMode(true);
    } finally {
      setWebsiteLoading(false);
    }
  }

  function handleWebsitePaste(e: ClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData("text").trim();
    if (!pasted) return;
    // Fire quickly after paste — no need to wait for the full debounce.
    setTimeout(() => {
      if (analyseTimeoutRef.current) {
        clearTimeout(analyseTimeoutRef.current);
        analyseTimeoutRef.current = null;
      }
      handleAnalyseWebsite();
    }, 50);
  }

  // Clean up the debounce timer on unmount.
  useEffect(() => {
    return () => {
      if (analyseTimeoutRef.current) clearTimeout(analyseTimeoutRef.current);
    };
  }, []);

  // Auto-trigger the website analyser ~900ms after the user stops typing,
  // as long as the URL looks plausibly complete (has a dot, ≥4 chars after
  // any scheme). Skips:
  //   - manualMode (user opted out of AI)
  //   - URLs we've already attempted (success or failure) — they re-fire
  //     only via the explicit "Regenerate" button or pressing Enter
  //   - the loading state (don't queue a second call while one's in flight)
  useEffect(() => {
    if (manualMode) return;
    if (websiteLoading) return;
    const trimmed = websiteUrl.trim();
    if (!trimmed) return;
    if (trimmed === lastAttemptedUrlRef.current) return;

    // Crude "looks like a URL" gate. We accept anything with a dot and a
    // TLD-ish suffix, optionally prefixed with a scheme. The backend
    // normaliser handles missing https://.
    const looksLikeUrl = /^(https?:\/\/)?[^\s.]+\.[a-z]{2,}/i.test(trimmed);
    if (!looksLikeUrl) return;

    if (analyseTimeoutRef.current) clearTimeout(analyseTimeoutRef.current);
    analyseTimeoutRef.current = setTimeout(() => {
      handleAnalyseWebsite();
    }, 900);

    return () => {
      if (analyseTimeoutRef.current) clearTimeout(analyseTimeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [websiteUrl, manualMode, websiteLoading]);

  // While the analyser is running, cycle through 4 progress messages
  // ("Reading your site…" → "Understanding your business…" → …) every
  // 1.5s so the user has something concrete to look at instead of a
  // bare spinner. Resets to step 0 each time loading flips on.
  useEffect(() => {
    if (!websiteLoading) return;
    setWebsiteProgressStep(0);
    const id = setInterval(() => {
      setWebsiteProgressStep((s) => (s + 1) % 4);
    }, 1500);
    return () => clearInterval(id);
  }, [websiteLoading]);

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
      setError(getErrorMessage(err, t("onboarding.failedSave")));
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
      setCachedOnboarded(true);
      setStep(6);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedSave")));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="welcome-page">
        <div className="welcome-container" style={{ textAlign: "center" }}>
          <div className="auth-logo">QualiPulse</div>
          <p style={{ color: "#6b7280" }}>{t("onboarding.continue")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="welcome-page">
      <div className="welcome-container">
        <div className="auth-logo" style={{ textAlign: "center", marginBottom: 8 }}>QualiPulse</div>

        {/* Progress indicator — 6 steps */}
        <div className="onboarding-progress" role="group" aria-label={`Step ${step} of ${STEP_LABELS.length}`}>
          {STEP_LABELS.map((label, i) => {
            const s = i + 1;
            return (
              <div key={s} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }} aria-current={s === step ? "step" : undefined}>
                <div
                  className={`onboarding-progress-dot ${s <= step ? "active" : ""} ${s === step ? "current" : ""}`}
                />
                <span style={{ fontSize: 10, color: s <= step ? "var(--primary, #6366f1)" : "var(--text-tertiary, #9ca3af)", whiteSpace: "nowrap" }}>
                  {label}
                </span>
                {s === step && <span style={{ position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", borderWidth: 0 }}>{`Step ${step} of ${STEP_LABELS.length}`}</span>}
              </div>
            );
          })}
        </div>

        {error && <div className="error-banner" role="alert" style={{ marginBottom: 20 }}>{error}</div>}

        {/* ── Step 1: Verify Email ── */}
        {step === 1 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">📧</div>
            <h1 className="welcome-title">{t("onboarding.verifyTitle")}</h1>
            <p className="welcome-subtitle">
              {t("onboarding.verifyDesc")} <strong>{me?.email}</strong>.
              {" "}{t("onboarding.verifyNote")}
            </p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8, marginBottom: 0 }}>
              {t("onboarding.checkingAutomatically")}
            </p>
            <div className="welcome-actions">
              <button className="btn btn-primary btn-lg" onClick={handleRefreshVerification}>
                {t("onboarding.alreadyVerifiedBtn")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={handleResendVerification}
                disabled={resendCooldown > 0}
              >
                {resendCooldown > 0
                  ? t("onboarding.resendCooldown", { seconds: resendCooldown })
                  : t("onboarding.resendVerification")}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)} style={{ fontSize: 13, color: "#9ca3af" }}>
                {t("onboarding.skip")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: About you ── */}
        {step === 2 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.profileTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.readyDesc")}</p>

            <div className="onboarding-form">
              {/* Language picker — drives email locale, AI research wizard
                  output, and the default project language. Changing this
                  swaps the onboarding UI itself in real time via i18n;
                  it's persisted to the company record on Continue. */}
              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.languageLabel")}
                </label>
                <div className="onboarding-chip-grid">
                  {[
                    { code: "en", label: "English" },
                    { code: "fr", label: "Français" },
                  ].map((opt) => {
                    const active = (i18n.language || "en")
                      .toLowerCase()
                      .startsWith(opt.code);
                    return (
                      <button
                        key={opt.code}
                        type="button"
                        className={`onboarding-chip ${active ? "selected" : ""}`}
                        onClick={() => i18n.changeLanguage(opt.code)}
                        disabled={saving}
                        aria-pressed={active}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginTop: 6,
                  }}
                >
                  {t("onboarding.languageHint")}
                </div>
              </div>

              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.profileCompanyLabel")}</label>
                <input
                  type="text"
                  className="field-input"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder={t("onboarding.profileCompanyPlaceholder")}
                  disabled={saving}
                />
              </div>

              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.profileRoleLabel")} <span style={{ color: "var(--danger)" }}>*</span>
                </label>
                <div className="onboarding-chip-grid">
                  {ROLE_VALUES.map((value, idx) => (
                    <button
                      key={value}
                      className={`onboarding-chip ${role === value ? "selected" : ""}`}
                      onClick={() => setRole(value)}
                      disabled={saving}
                    >
                      {roleLabels[idx] ?? value}
                    </button>
                  ))}
                </div>
              </div>

              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.teamSizeLabel")} <span style={{ color: "var(--danger)" }}>*</span>
                </label>
                <div className="onboarding-chip-grid">
                  {TEAM_SIZE_VALUES.map((value, idx) => (
                    <button
                      key={value}
                      className={`onboarding-chip ${companySize === value ? "selected" : ""}`}
                      onClick={() => setCompanySize(value)}
                      disabled={saving}
                    >
                      {teamSizeLabels[idx] ?? value}
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
                {saving ? t("onboarding.saving") : t("onboarding.continue")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Your business ── */}
        {step === 3 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.businessTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.businessSubtitle")}</p>

            <div className="onboarding-form">
              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.websiteLabel")}{" "}
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                    {t("onboarding.websiteOptional")}
                  </span>
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    className="field-input"
                    value={websiteUrl}
                    onChange={(e) => {
                      setWebsiteUrl(e.target.value);
                      // Typing doesn't auto-analyse — the user must press
                      // Enter or click the button. Paste still auto-fires
                      // (handleWebsitePaste) since pasting is an explicit
                      // "use this URL" intent.
                    }}
                    onPaste={handleWebsitePaste}
                    placeholder={t("onboarding.websitePlaceholder")}
                    style={{ flex: 1 }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAnalyseWebsite();
                      }
                    }}
                    disabled={saving}
                  />
                  <button
                    className="btn btn-secondary"
                    onClick={handleAnalyseWebsite}
                    disabled={websiteLoading || !websiteUrl.trim() || saving}
                    style={{ whiteSpace: "nowrap", flexShrink: 0 }}
                  >
                    {websiteLoading ? (
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span className="spinner" style={{ width: 14, height: 14, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block", animation: "spin 0.6s linear infinite" }} />
                        {t("onboarding.websiteAnalysing")}
                      </span>
                    ) : (
                      websiteUrl.trim() &&
                      websiteUrl.trim() !== analysedUrl.trim() &&
                      analysedUrl
                        ? t("onboarding.websiteRegenerate")
                        : t("onboarding.websiteAnalyseFriendly")
                    )}
                  </button>
                </div>
                {/* Claude-style cycling progress panel — shown only while
                    the analyser is running. Replaces the bare spinner with
                    a sequence of concrete status messages so the user has
                    something tangible to look at during the ~3-5s round
                    trip. */}
                {websiteLoading && (
                  <div
                    role="status"
                    aria-live="polite"
                    style={{
                      marginTop: 12,
                      padding: "12px 14px",
                      borderRadius: "var(--radius)",
                      background: "var(--primary-subtle, #eef2ff)",
                      border: "1px solid var(--primary-border, #c7d2fe)",
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      fontSize: 14,
                      color: "var(--text-primary)",
                    }}
                  >
                    <span
                      className="spinner"
                      style={{
                        width: 16,
                        height: 16,
                        border: "2px solid var(--primary)",
                        borderTopColor: "transparent",
                        borderRadius: "50%",
                        display: "inline-block",
                        animation: "spin 0.6s linear infinite",
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ flex: 1 }}>
                      {t(`onboarding.websiteProgress.${websiteProgressStep}`, {
                        defaultValue: t("onboarding.websiteAnalysing"),
                      })}
                    </span>
                  </div>
                )}
                {/* "No website? Describe manually" escape hatch */}
                {!businessSummary && !manualMode && !websiteLoading && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setManualMode(true)}
                    style={{
                      marginTop: 8,
                      fontSize: 13,
                      color: "var(--text-muted)",
                      padding: "4px 0",
                      textAlign: "left",
                      textDecoration: "underline",
                    }}
                    disabled={saving}
                  >
                    {t("onboarding.websiteDescribeManually")}
                  </button>
                )}
              </div>

              {/* Textarea only appears once we have a summary, an error,
                  or the user has opted into manual mode. */}
              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.businessSummaryLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
                  {businessSummary && analysedUrl && !summaryConfirmed && (
                    <div
                      style={{
                        background: "var(--primary-subtle, #eef2ff)",
                        border: "1px solid var(--primary-border, #c7d2fe)",
                        borderRadius: "var(--radius)",
                        padding: "10px 12px",
                        marginBottom: 8,
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 8,
                        fontSize: 13,
                        color: "var(--text-primary)",
                      }}
                    >
                      <span style={{ fontSize: 16 }}>✨</span>
                      <span style={{ flex: 1 }}>
                        {t("onboarding.websiteReviewPrompt")}
                      </span>
                    </div>
                  )}
                  {businessSummary && summaryConfirmed && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--success, #16a34a)",
                        marginBottom: 6,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span>✓</span>
                      <span>{t("onboarding.websiteConfirmed")}</span>
                    </div>
                  )}
                  <textarea
                    className="field-input"
                    value={businessSummary}
                    onChange={(e) => {
                      setBusinessSummary(e.target.value);
                      // Editing the summary counts as reviewing it.
                      if (!summaryConfirmed) setSummaryConfirmed(true);
                    }}
                    rows={4}
                    placeholder={t("onboarding.businessSummaryPlaceholder")}
                    style={{ resize: "vertical", lineHeight: 1.6 }}
                    disabled={saving}
                  />
                  {/* Explicit confirm button appears once we have an
                      AI-generated summary that the user hasn't touched. */}
                  {businessSummary && analysedUrl && !summaryConfirmed && !manualMode && (
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => setSummaryConfirmed(true)}
                        disabled={saving}
                        style={{ fontSize: 13 }}
                      >
                        ✓ {t("onboarding.websiteLooksRight")}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={handleAnalyseWebsite}
                        disabled={saving || websiteLoading}
                        style={{ fontSize: 13 }}
                      >
                        ↻ {t("onboarding.websiteTryAgain")}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Industry chips — hidden until we have a summary OR the user
                  is in manual mode. */}
              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">{t("onboarding.industryLabel")}</label>
                  <div className="onboarding-chip-grid">
                    {INDUSTRY_VALUES.map((value, idx) => (
                      <button
                        key={value}
                        className={`onboarding-chip ${industry === value ? "selected" : ""}`}
                        onClick={() => setIndustry(value)}
                        disabled={saving}
                      >
                        {industryLabels[idx] ?? value}
                      </button>
                    ))}
                    {customIndustries.map((value) => (
                      <button
                        key={`custom-${value}`}
                        className={`onboarding-chip ${industry === value ? "selected" : ""}`}
                        onClick={() => setIndustry(value)}
                        disabled={saving}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">{t("onboarding.primaryMarketLabel")}</label>
                  <div className="onboarding-chip-grid">
                    {REGION_VALUES.map((r, idx) => (
                      <button
                        key={r.value}
                        className={`onboarding-chip ${primaryRegion === r.value ? "selected" : ""}`}
                        onClick={() => setPrimaryRegion(r.value)}
                        disabled={saving}
                      >
                        {regionLabels[idx] ?? r.value}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              {(() => {
                // Continue is locked until either:
                //   (a) the user confirmed an AI-generated summary, OR
                //   (b) the user is in manual mode (they typed it themselves), OR
                //   (c) there's no summary at all (website is optional — skip)
                // Also locked while the analyser is in flight so the user
                // can't click past a half-loaded summary.
                const hasAi = !!(businessSummary && analysedUrl);
                const reviewLocked = hasAi && !summaryConfirmed && !manualMode;
                const continueLocked = reviewLocked || websiteLoading;
                return (
                  <>
                    <button
                      className="btn btn-primary btn-lg"
                      onClick={handleBusinessContinue}
                      disabled={saving || continueLocked}
                      title={
                        websiteLoading
                          ? t("onboarding.websiteAnalysing")
                          : reviewLocked
                            ? t("onboarding.websiteReviewPrompt")
                            : undefined
                      }
                    >
                      {saving ? t("onboarding.saving") : t("onboarding.continue")}
                    </button>
                    {reviewLocked && !websiteLoading && (
                      <div
                        style={{
                          fontSize: 12,
                          color: "var(--text-muted)",
                          textAlign: "center",
                          marginTop: -4,
                        }}
                      >
                        {t("onboarding.websiteReviewHint")}
                      </div>
                    )}
                  </>
                );
              })()}
              <button className="btn btn-ghost" onClick={() => setStep(2)} disabled={saving}>
                ← {t("onboarding.stepProfile")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Research experience ── */}
        {step === 4 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.experienceTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.experienceSubtitle")}</p>

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
                ← {t("onboarding.stepBusiness")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 5: Goals ── */}
        {step === 5 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.goalsTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.readyDesc")}</p>

            <div className="onboarding-form" style={{ marginTop: 24 }}>
              <div className="onboarding-field">
                <textarea
                  className="field-input"
                  value={goalsFreeform}
                  onChange={(e) => setGoalsFreeform(e.target.value)}
                  rows={5}
                  style={{ minHeight: 120, resize: "vertical", lineHeight: 1.6 }}
                  placeholder={t("onboarding.goalsPlaceholder")}
                  disabled={saving}
                />
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right", marginTop: 4 }}>
                  {t("onboarding.goalsCharCount", { count: goalsFreeform.length })}
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 8 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={() => handleGoalsContinue(false)}
                disabled={saving}
              >
                {saving ? t("onboarding.saving") : t("onboarding.continue")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => handleGoalsContinue(true)}
                disabled={saving}
                style={{ fontSize: 13, color: "var(--text-muted)" }}
              >
                {t("onboarding.skip")}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(4)} disabled={saving} style={{ fontSize: 13 }}>
                ← {t("onboarding.stepExperience")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 6: Ready ── */}
        {step === 6 && (
          <div className="onboarding-step">
            <div className="onboarding-icon">🎉</div>
            <h1 className="welcome-title">{t("onboarding.readyTitle")}</h1>

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
                  {t("onboarding.trialActive")}
                </span>
                <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                  {" "}{t("onboarding.trialUntil", {
                    date: new Date(me.trial_ends_at).toLocaleDateString(i18n.language),
                  })}
                </span>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 28 }}>
              {([
                t("onboarding.benefit1"),
                t("onboarding.benefit2"),
                t("onboarding.benefit3"),
              ] as string[]).map((benefit) => (
                <div key={benefit} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: "var(--success, #16a34a)", fontWeight: 700, fontSize: 16 }}>✓</span>
                  <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>{benefit}</span>
                </div>
              ))}
            </div>

            <div className="welcome-actions">
              <button className="btn btn-primary btn-lg" onClick={() => navigate("/projects/new")}>
                {t("onboarding.createFirstProject")}
              </button>
              <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>
                {t("onboarding.exploreDashboard")}
              </button>
            </div>

            <div className="welcome-trust" style={{ marginTop: 16 }}>
              <span>{t("onboarding.trustNote")}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
