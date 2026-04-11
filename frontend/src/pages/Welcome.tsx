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
// Experience is now inline on Step 2 (not a dedicated step) — kept as a
// constant here so we don't duplicate the stable order between component
// and locale arrays.
const EXPERIENCE_VALUES = ["new", "some", "professional"] as const;

// Country-level values for the "Primary market" select. Keep in the same
// order as the `regions` i18n array so labels line up by index. ISO 3166-1
// alpha-2 codes where possible; "europe", "global", "other" are our own
// catch-all buckets.
const REGION_VALUES = [
  "fr", "be", "ch", "de", "uk", "es", "it", "nl", "pt",
  "europe", "us", "ca", "global", "other",
];

// Qualification selects on Step 4. Keys are stable identifiers sent to the
// backend; labels come from the i18n files.
const INTERVIEWS_TARGET_VALUES = ["0-5", "5-20", "20-50", "50+"];
const CURRENT_TOOL_VALUES = [
  "nothing",
  "diy_interviews",
  "dovetail",
  "usertesting",
  "userinterviews",
  "respondent",
  "other",
];
const DECISION_ROLE_VALUES = ["buyer", "influencer", "user", "evaluator"];

// Number of "reading your site / understanding your business / …" messages
// shown while the website analyser is running. Must stay in sync with the
// number of keys under `onboarding.websiteProgress.*` in the locale files.
const WEBSITE_PROGRESS_STEP_COUNT = 8;

// Field names used for per-field inline errors. Keeps the state object
// typed — see `fieldErrors` below.
type FieldErrors = Partial<Record<"role" | "companySize" | "interviewsTarget" | "decisionRole", string>>;

export default function Welcome() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation("auth");
  const [step, setStep] = useState(1);
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Global "something blew up on save" banner. Field-level validation now
  // uses the per-field `fieldErrors` state instead of this.
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [resendCooldown, setResendCooldown] = useState(0);

  // Step 2 — Profile (now also holds research_experience — we folded the
  // old dedicated Step 4 into this one to cut the flow from 6 steps to 5).
  const [companyName, setCompanyName] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [role, setRole] = useState("");
  const [researchExperience, setResearchExperience] = useState<string>("");

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
  // Debounce auto-analyse so we don't fire on every keystroke.
  const analyseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Step 4 — Goals + qualification
  const [goalsFreeform, setGoalsFreeform] = useState<string>("");
  const [interviewsTarget, setInterviewsTarget] = useState("");
  const [currentTool, setCurrentTool] = useState("");
  const [decisionRole, setDecisionRole] = useState("");

  // Translated option arrays (re-read on language change)
  const teamSizeLabels = t("onboarding.teamSizes", { returnObjects: true }) as string[];
  const roleLabels = t("onboarding.roles", { returnObjects: true }) as string[];
  const industryLabels = t("onboarding.industries", { returnObjects: true }) as string[];
  const regionLabels = t("onboarding.regions", { returnObjects: true }) as string[];
  const interviewsTargetLabels = t("onboarding.interviewsTargetOptions", { returnObjects: true }) as string[];
  const currentToolLabels = t("onboarding.currentToolOptions", { returnObjects: true }) as string[];
  const decisionRoleLabels = t("onboarding.decisionRoleOptions", { returnObjects: true }) as string[];

  // Step labels — 5 steps now (Experience was folded into Profile).
  const STEP_LABELS = [
    t("onboarding.stepVerify"),
    t("onboarding.stepProfile"),
    t("onboarding.stepBusiness"),
    t("onboarding.stepGoals"),
    t("onboarding.stepReady"),
  ];

  // Experience chip copy (now inline on Step 2)
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
    const errs: FieldErrors = {};
    if (!role) errs.role = t("onboarding.profileRoleRequired");
    if (!companySize) errs.companySize = t("onboarding.profileTeamRequired");
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});
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
        research_experience: researchExperience || undefined,
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
    try {
      const {
        business_summary,
        industry: detectedIndustry,
        primary_country: detectedCountry,
      } = await analyseWebsite(trimmed);
      setBusinessSummary(business_summary);
      setAnalysedUrl(trimmed);
      setManualMode(false);

      // Auto-select the country chip if Claude identified a primary market.
      // Only overwrite if we don't already have a user selection so the
      // user's explicit choice takes precedence on a regenerate.
      if (detectedCountry) {
        if (REGION_VALUES.includes(detectedCountry)) {
          setPrimaryRegion((prev) => prev || detectedCountry);
        }
      }

      // Auto-select the industry chip. If Claude returned a label that
      // isn't in the predefined list, add it as a custom chip.
      if (detectedIndustry) {
        const known = INDUSTRY_VALUES.some(
          (v) => v.toLowerCase() === detectedIndustry.toLowerCase(),
        );
        if (known) {
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

  // Auto-trigger the website analyser ~900ms after the user stops typing.
  useEffect(() => {
    if (manualMode) return;
    if (websiteLoading) return;
    const trimmed = websiteUrl.trim();
    if (!trimmed) return;
    if (trimmed === lastAttemptedUrlRef.current) return;

    const looksLikeUrl = /\.[^\s.]{2,}$/.test(trimmed) && !/\s/.test(trimmed);
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

  // Walk through 8 progress messages while the analyser runs, cap on the
  // last one so the user doesn't see the sequence loop and wonder if the
  // call is stuck.
  useEffect(() => {
    if (!websiteLoading) return;
    setWebsiteProgressStep(0);
    const id = setInterval(() => {
      setWebsiteProgressStep((s) =>
        s >= WEBSITE_PROGRESS_STEP_COUNT - 1 ? s : s + 1,
      );
    }, 1800);
    return () => clearInterval(id);
  }, [websiteLoading]);

  // Step 3 → 4. Summary review gate removed — the summary is editable
  // inline and users should not need a separate "Looks right" click to
  // advance. If they typed a URL and nothing's analysed yet, we trigger
  // the analyser instead of advancing.
  async function handleBusinessContinue() {
    const trimmed = websiteUrl.trim();
    if (trimmed && !businessSummary && !manualMode && !websiteLoading) {
      handleAnalyseWebsite();
      return;
    }

    setSaving(true);
    setError("");
    try {
      await saveOnboardingProfile({
        website_url: trimmed || undefined,
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

  // Step 4 → 5 (completes onboarding)
  async function handleGoalsContinue(skipGoals = false) {
    // Qualification selects are all optional — but we try to nudge the
    // user into filling them because they drive sales routing and AI
    // context. No hard validation here; an incomplete answer is better
    // than a drop-off.
    setSaving(true);
    setError("");
    setFieldErrors({});
    try {
      await completeOnboarding({
        goals_freeform: skipGoals ? undefined : (goalsFreeform || "").trim() || undefined,
        interviews_per_month_target: interviewsTarget || undefined,
        current_tool: currentTool || undefined,
        decision_role: decisionRole || undefined,
      });
      setCachedOnboarded(true);
      setStep(5);
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

  // Persistent trial ribbon — visible across Steps 1-4 so the user can see
  // what they're unlocking while they work through onboarding. On Step 5
  // we show a fancier framed version.
  const trialRibbon =
    step < 5 && me?.trial_ends_at ? (
      <div
        className="onboarding-trial-ribbon"
        role="status"
        aria-live="polite"
        style={{
          background: "var(--primary-subtle, #eef2ff)",
          border: "1px solid var(--primary-border, #c7d2fe)",
          borderRadius: "var(--radius)",
          padding: "8px 14px",
          marginBottom: 16,
          fontSize: 13,
          color: "var(--text-secondary)",
          textAlign: "center",
        }}
      >
        <strong style={{ color: "var(--primary)" }}>
          {t("onboarding.trialActive")}
        </strong>{" "}
        {t("onboarding.trialUntil", {
          date: new Date(me.trial_ends_at).toLocaleDateString(i18n.language),
        })}
      </div>
    ) : null;

  // Header row — logo left, persistent language toggle right. Language
  // was buried inside Step 2 before; moving it up means the flow is
  // immediately usable in the user's real language without clicking
  // through a step they can't read.
  const header = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 8,
      }}
    >
      <div className="auth-logo" style={{ margin: 0 }}>QualiPulse</div>
      <div className="onboarding-header-lang" role="group" aria-label={t("onboarding.languageLabel")}>
        {[
          { code: "en", label: "EN" },
          { code: "fr", label: "FR" },
        ].map((opt) => {
          const active = (i18n.language || "en")
            .toLowerCase()
            .startsWith(opt.code);
          return (
            <button
              key={opt.code}
              type="button"
              onClick={() => i18n.changeLanguage(opt.code)}
              aria-pressed={active}
              className={`onboarding-header-lang-btn ${active ? "active" : ""}`}
              style={{
                minHeight: 36,
                minWidth: 44,
                padding: "6px 12px",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                background: active ? "var(--primary)" : "var(--bg-surface)",
                color: active ? "#fff" : "var(--text-secondary)",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                marginLeft: 4,
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="welcome-page">
      <div className="welcome-container">
        {header}

        {/* Progress indicator — 5 steps */}
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

        {trialRibbon}

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

        {/* ── Step 2: About you (now also includes experience) ── */}
        {step === 2 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.profileTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.profileSubtitle")}</p>

            <div className="onboarding-form">
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
                      onClick={() => {
                        setRole(value);
                        if (fieldErrors.role) setFieldErrors((e) => ({ ...e, role: undefined }));
                      }}
                      disabled={saving}
                    >
                      {roleLabels[idx] ?? value}
                    </button>
                  ))}
                </div>
                {fieldErrors.role && (
                  <div className="field-error" role="alert" style={{ color: "var(--danger)", fontSize: 12, marginTop: 6 }}>
                    {fieldErrors.role}
                  </div>
                )}
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
                      onClick={() => {
                        setCompanySize(value);
                        if (fieldErrors.companySize) setFieldErrors((e) => ({ ...e, companySize: undefined }));
                      }}
                      disabled={saving}
                    >
                      {teamSizeLabels[idx] ?? value}
                    </button>
                  ))}
                </div>
                {fieldErrors.companySize && (
                  <div className="field-error" role="alert" style={{ color: "var(--danger)", fontSize: 12, marginTop: 6 }}>
                    {fieldErrors.companySize}
                  </div>
                )}
              </div>

              {/* Experience — formerly Step 4. Optional, no validation. */}
              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.experienceInlineLabel")}{" "}
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                    {t("onboarding.websiteOptional")}
                  </span>
                </label>
                <div className="onboarding-chip-grid">
                  {EXPERIENCE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      className={`onboarding-chip ${researchExperience === opt.value ? "selected" : ""}`}
                      onClick={() => setResearchExperience(opt.value)}
                      disabled={saving}
                      title={opt.subtitle}
                    >
                      <span style={{ marginRight: 4 }}>{opt.emoji}</span>
                      {opt.title}
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
                <input
                  type="text"
                  className="field-input"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  onPaste={handleWebsitePaste}
                  placeholder={t("onboarding.websitePlaceholder")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAnalyseWebsite();
                    }
                  }}
                  disabled={saving || websiteLoading}
                />
                {/* Privacy reassurance — addresses the "why do you want my
                    URL?" drop-off concern. Shown once the user starts
                    engaging with the input. */}
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginTop: 6,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span aria-hidden>🔒</span>
                  <span>{t("onboarding.websitePrivacyNote")}</span>
                </div>
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

              {/* Textarea — drops the 'Looks right' gate. If there's a
                  draft the user can edit it inline; if they need a new
                  pass they can click Regenerate. Continue never blocks on
                  review status anymore. */}
              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.businessSummaryLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
                  {businessSummary && analysedUrl && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        marginBottom: 6,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span>✨</span>
                      <span>{t("onboarding.websiteAutoFilled")}</span>
                    </div>
                  )}
                  <textarea
                    className="field-input"
                    value={businessSummary}
                    onChange={(e) => setBusinessSummary(e.target.value)}
                    rows={4}
                    placeholder={t("onboarding.businessSummaryPlaceholder")}
                    style={{ resize: "vertical", lineHeight: 1.6 }}
                    disabled={saving}
                  />
                  {businessSummary && analysedUrl && !manualMode && (
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
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

              {/* Industry chips — still here because we auto-detect from
                  website analysis and changing the chip is a 1-click fix. */}
              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.industryLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
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

              {/* Primary market — moved from 14-chip grid to a native
                  select. The grid was taking up half the viewport with
                  options 90% of users would never pick. */}
              {(businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.primaryMarketLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
                  <select
                    className="field-input"
                    value={primaryRegion}
                    onChange={(e) => setPrimaryRegion(e.target.value)}
                    disabled={saving}
                    style={{ minHeight: 44 }}
                  >
                    <option value="">{t("onboarding.primaryMarketPlaceholder")}</option>
                    {REGION_VALUES.map((value, idx) => (
                      <option key={value} value={value}>
                        {regionLabels[idx] ?? value}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleBusinessContinue}
                disabled={saving || websiteLoading}
              >
                {saving ? t("onboarding.saving") : t("onboarding.continue")}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)} disabled={saving}>
                ← {t("onboarding.stepProfile")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Goals + qualification ── */}
        {step === 4 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.goalsTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.goalsSubtitle")}</p>

            <div className="onboarding-form" style={{ marginTop: 24 }}>
              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.goalsInlineLabel")}</label>
                <textarea
                  className="field-input"
                  value={goalsFreeform || ""}
                  onChange={(e) => setGoalsFreeform(e.target.value)}
                  rows={4}
                  style={{ minHeight: 100, resize: "vertical", lineHeight: 1.6 }}
                  placeholder={t("onboarding.goalsPlaceholder")}
                  disabled={saving}
                />
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right", marginTop: 4 }}>
                  {t("onboarding.goalsCharCount", { count: (goalsFreeform || "").length })}
                </div>
              </div>

              {/* Qualification — drives sales routing. Optional, never
                  blocks advance, but heavily nudged. */}
              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.interviewsTargetLabel")}</label>
                <div className="onboarding-chip-grid">
                  {INTERVIEWS_TARGET_VALUES.map((value, idx) => (
                    <button
                      key={value}
                      className={`onboarding-chip ${interviewsTarget === value ? "selected" : ""}`}
                      onClick={() => setInterviewsTarget(value)}
                      disabled={saving}
                    >
                      {interviewsTargetLabels[idx] ?? value}
                    </button>
                  ))}
                </div>
              </div>

              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.currentToolLabel")}</label>
                <select
                  className="field-input"
                  value={currentTool}
                  onChange={(e) => setCurrentTool(e.target.value)}
                  disabled={saving}
                  style={{ minHeight: 44 }}
                >
                  <option value="">{t("onboarding.currentToolPlaceholder")}</option>
                  {CURRENT_TOOL_VALUES.map((value, idx) => (
                    <option key={value} value={value}>
                      {currentToolLabels[idx] ?? value}
                    </option>
                  ))}
                </select>
              </div>

              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.decisionRoleLabel")}</label>
                <div className="onboarding-chip-grid">
                  {DECISION_ROLE_VALUES.map((value, idx) => (
                    <button
                      key={value}
                      className={`onboarding-chip ${decisionRole === value ? "selected" : ""}`}
                      onClick={() => setDecisionRole(value)}
                      disabled={saving}
                    >
                      {decisionRoleLabels[idx] ?? value}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 8 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={() => handleGoalsContinue(false)}
                disabled={saving}
              >
                {saving ? t("onboarding.saving") : t("onboarding.finishSetup")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => handleGoalsContinue(true)}
                disabled={saving}
                style={{ fontSize: 13, color: "var(--text-muted)" }}
              >
                {t("onboarding.skipAndFinish")}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(3)} disabled={saving} style={{ fontSize: 13 }}>
                ← {t("onboarding.stepBusiness")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 5: Ready ── */}
        {step === 5 && (
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

            {/* Primary CTA now lands on the dashboard where the seeded
                demo project is waiting, not on /projects/new. The demo
                is the single biggest aha-moment we can deliver in the
                first 60 seconds — sending users to a blank wizard was
                burying it. */}
            <p
              style={{
                fontSize: 14,
                color: "var(--text-secondary)",
                textAlign: "center",
                marginBottom: 20,
              }}
            >
              {t("onboarding.readyDemoPointer")}
            </p>

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
              <button
                className="btn btn-primary btn-lg"
                onClick={() => navigate("/dashboard")}
              >
                {t("onboarding.exploreDemo")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => navigate("/projects/new")}
                style={{ fontSize: 13 }}
              >
                {t("onboarding.createFirstProject")}
              </button>
              {/* Talk-to-sales escape hatch for enterprise leads who
                  don't want to self-serve. */}
              <a
                className="btn btn-ghost"
                href="mailto:sales@qualipulse.com?subject=Enterprise%20inquiry"
                style={{ fontSize: 13, color: "var(--text-muted)", textDecoration: "none" }}
              >
                {t("onboarding.talkToSales")}
              </a>
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

// Silence unused-variable warning for EXPERIENCE_VALUES — it's kept for
// parity with backend valid values and docs even though we only iterate
// `EXPERIENCE_OPTIONS` in the component.
void EXPERIENCE_VALUES;
