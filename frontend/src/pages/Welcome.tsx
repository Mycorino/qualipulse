import { useState, useEffect, useRef, type ClipboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getMe,
  completeOnboarding,
  saveOnboardingProfile,
  resendVerification,
  analyseWebsite,
  generateStudyDraft,
} from "../api/auth";
import type { CompanyResponse, StudyDraft } from "../api/auth";
import { createProject } from "../api/projects";
import { setCachedOnboarded } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";

const INDUSTRY_VALUES = ["Consumer Brands", "SaaS / Tech", "Agency", "Healthcare", "Academia", "Government", "Other"];

const REGION_VALUES = [
  "fr", "be", "ch", "de", "uk", "es", "it", "nl", "pt",
  "europe", "us", "ca", "global", "other",
];

const EXPERIENCE_VALUES = ["new", "some", "professional"] as const;

// Number of "reading your site / understanding your business / ..." messages
const WEBSITE_PROGRESS_STEP_COUNT = 8;

// ── Reusable loading carousel ──

function LoadingCarousel({ messages, interval = 2500 }: { messages: string[]; interval?: number }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setIndex(i => (i + 1) % messages.length), interval);
    return () => clearInterval(timer);
  }, [messages, interval]);
  return <p className="loading-carousel">{messages[index]}</p>;
}

export default function Welcome() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation("auth");
  const [step, setStep] = useState(1);
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  // Step 2 — About you
  const [roleTitle, setRoleTitle] = useState("");
  const [occupationDescription, setOccupationDescription] = useState("");
  const [researchExperience, setResearchExperience] = useState<string>("");

  // Step 3 — Your company
  const [companyNameInput, setCompanyNameInput] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [websiteLoading, setWebsiteLoading] = useState(false);
  const [websiteProgressStep, setWebsiteProgressStep] = useState(0);
  const [businessSummary, setBusinessSummary] = useState("");
  const [industry, setIndustry] = useState("");
  const [primaryRegion, setPrimaryRegion] = useState("");
  const [analysedUrl, setAnalysedUrl] = useState("");
  const lastAttemptedUrlRef = useRef<string>("");
  const [customIndustries, setCustomIndustries] = useState<string[]>([]);
  const [manualMode, setManualMode] = useState(false);
  const [websiteHint, setWebsiteHint] = useState<string | null>(null);
  const analyseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [goalsFreeform, setGoalsFreeform] = useState("");
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  // Step 4 — Brief
  // Step 4 — Study draft (replaces standalone brief)
  const [studyDraft, setStudyDraft] = useState<StudyDraft | null>(null);
  const [studyLoading, setStudyLoading] = useState(false);
  const [studyError, setStudyError] = useState(false);

  // Translated option arrays
  const industryLabels = t("onboarding.industries", { returnObjects: true }) as string[];
  const regionLabels = t("onboarding.regions", { returnObjects: true }) as string[];

  // Step labels — 4 steps
  const STEP_LABELS = [
    t("onboarding.steps.verify"),
    t("onboarding.steps.researchGoal"),
    t("onboarding.steps.yourCompany"),
    t("onboarding.steps.yourStudy"),
  ];

  const experienceOptions = [
    { label: t("onboarding.experienceFirst"), value: "new" as const },
    { label: t("onboarding.experienceSome"), value: "some" as const },
    { label: t("onboarding.experienceRegular"), value: "professional" as const },
  ];

  const uiLang = (i18n.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
  // For Google signups we seed Company.name from the email domain (or
  // the local part for free-mail addresses), but the placeholder is
  // often still meaningless to the user ("Your role at Mycorino"
  // when their handle happens to match a freemail local-part). We
  // consider the name an unconfirmed placeholder when it matches the
  // person's full name, first/last name, or the email's local-part —
  // and in those cases drop the "at <X>" suffix from the role label.
  const rawCompanyName = me?.name ?? "";
  const emailLocalPart = (me?.email || "").split("@")[0] || "";
  const normalized = rawCompanyName.trim().toLowerCase();
  const isPlaceholderName =
    !rawCompanyName ||
    (!!me?.first_name &&
      !!me?.last_name &&
      normalized ===
        `${me.first_name} ${me.last_name}`.trim().toLowerCase()) ||
    (!!me?.first_name && normalized === me.first_name.toLowerCase()) ||
    (!!me?.last_name && normalized === me.last_name.toLowerCase()) ||
    (!!emailLocalPart && normalized === emailLocalPart.toLowerCase());
  const companyName = isPlaceholderName ? "" : rawCompanyName;

  // Auto-poll for email verification
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const pollTimeoutHit = pollTick >= 40; // 40 * 3s = 2 minutes

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCachedOnboarded(!!data.onboarding_completed);
        if (data.onboarding_completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        if (data.email_verified) {
          setStep(2);
        }
        // Pre-fill from existing data
        if (data.role) setRoleTitle(data.role);
        if (data.occupation_description) setOccupationDescription(data.occupation_description);
        if (data.research_experience) setResearchExperience(data.research_experience);
        if (data.name) setCompanyNameInput(data.name);
        if (data.website_url) setWebsiteUrl(data.website_url);
        if (data.business_summary) setBusinessSummary(data.business_summary);
        if (data.industry) setIndustry(data.industry);
        if (data.primary_region) setPrimaryRegion(data.primary_region);
        if (data.goals_freeform) setGoalsFreeform(data.goals_freeform);
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
    setPollTick(0);
    pollRef.current = setInterval(async () => {
      setPollTick((n) => {
        // Stop polling after 2 minutes — user can still click manual refresh
        if (n >= 40) {
          if (pollRef.current) clearInterval(pollRef.current);
          return n;
        }
        return n + 1;
      });
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

  // Step 2 -> 3
  async function handleAboutYouContinue() {
    if (!roleTitle.trim() || !occupationDescription.trim() || !researchExperience) return;
    setSaving(true);
    setError("");
    try {
      const langCode = uiLang;
      await saveOnboardingProfile({
        role: roleTitle.trim(),
        occupation_description: occupationDescription.trim() || undefined,
        research_experience: researchExperience,
        preferred_language: langCode,
      });
      setStep(3);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedSave")));
    } finally {
      setSaving(false);
    }
  }

  // Step 3 — Analyse website
  async function handleAnalyseWebsite() {
    const trimmed = websiteUrl.trim();
    if (!trimmed) return;
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

      if (detectedCountry) {
        if (REGION_VALUES.includes(detectedCountry)) {
          setPrimaryRegion((prev) => prev || detectedCountry);
        }
      }

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
    } catch {
      setWebsiteHint("fallback");
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

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (analyseTimeoutRef.current) clearTimeout(analyseTimeoutRef.current);
    };
  }, []);

  // Auto-trigger website analyser ~900ms after typing stops
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

  // Website progress step cycling
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

  // Step 3 -> 4
  async function handleCompanyContinue() {
    const trimmed = websiteUrl.trim();
    if (trimmed && !businessSummary && !manualMode && !websiteLoading) {
      handleAnalyseWebsite();
      return;
    }

    setSaving(true);
    setError("");
    try {
      await saveOnboardingProfile({
        name: companyNameInput.trim() || undefined,
        website_url: trimmed || undefined,
        business_summary: businessSummary.trim() || undefined,
        industry: industry || undefined,
        primary_region: primaryRegion || undefined,
        goals_freeform: goalsFreeform.trim() || undefined,
      });
      // Reflect the corrected workspace name locally so step 4's recap
      // ("Welcome at <company>") doesn't still show the old placeholder.
      if (companyNameInput.trim()) {
        setMe((prev) => (prev ? { ...prev, name: companyNameInput.trim() } : prev));
      }
      setStep(4);
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedSave")));
    } finally {
      setSaving(false);
    }
  }

  // Step 4 — generate study draft on enter
  useEffect(() => {
    if (step !== 4) return;
    setStudyLoading(true);
    setStudyError(false);
    generateStudyDraft({
      first_name: me?.first_name || undefined,
      company_name: companyName || undefined,
      role_title: roleTitle.trim() || undefined,
      research_intent: occupationDescription.trim() || undefined,
      research_experience: researchExperience || undefined,
      industry: industry || undefined,
      business_summary: businessSummary.trim() || undefined,
      goals_freeform: goalsFreeform.trim() || undefined,
      language: uiLang,
    })
      .then((res) => {
        if (res.draft) {
          setStudyDraft(res.draft);
        } else {
          setStudyError(true);
        }
      })
      .catch(() => {
        setStudyError(true);
      })
      .finally(() => {
        setStudyLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // Step 4 — Create the study from the draft + complete onboarding
  async function handleCreateStudy() {
    if (!studyDraft) return;
    setSaving(true);
    setError("");
    // Mark onboarding complete first (idempotent — if project creation
    // fails the user still lands on the dashboard rather than being
    // trapped in the wizard).
    let onboardingDone = false;
    try {
      await completeOnboarding({
        onboarding_recap: studyDraft.brief_summary || undefined,
        goals_freeform: goalsFreeform.trim() || undefined,
      });
      setCachedOnboarded(true);
      onboardingDone = true;

      const project = await createProject({
        name: studyDraft.study_title,
        language: uiLang,
        interview_duration_minutes: studyDraft.duration_minutes,
        research_objective: studyDraft.research_objective,
        target_customer_description: studyDraft.target_audience,
        questions: studyDraft.questions.map((q) => ({
          section_index: q.section_index,
          section_title: q.section_title,
          question_index: q.question_index,
          main_question: q.main_question,
          interview_notes: q.interview_notes,
          desired_learning: q.desired_learning,
        })),
        screening_questions: [],
      });
      navigate(`/projects/${project.id}`, { replace: true });
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("onboarding.failedSave")));
      if (onboardingDone) {
        // Onboarding succeeded but project creation failed — send the user
        // to the dashboard rather than leaving them stuck in the wizard.
        navigate("/dashboard", { replace: true });
      }
    } finally {
      setSaving(false);
    }
  }

  // Step 4 — Start from scratch (skip the AI study, but still complete onboarding)
  async function handleStartFromBlank() {
    setSaving(true);
    setError("");
    try {
      await completeOnboarding({
        onboarding_recap: studyDraft?.brief_summary || undefined,
        goals_freeform: goalsFreeform.trim() || undefined,
      });
      setCachedOnboarded(true);
      navigate("/projects/new", { replace: true });
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

  // Persistent trial ribbon
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

  // Header row
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
    </div>
  );

  // Carousel messages for study-draft loading
  const studyCarouselMessages = t("onboarding.studyCarousel", { returnObjects: true }) as string[];

  return (
    <div className="welcome-page">
      <div className="welcome-container">
        {header}

        {/* Progress indicator — 4 steps */}
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
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8, marginBottom: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              {pollTimeoutHit ? (
                <span>{t("onboarding.pollStopped", { defaultValue: "Still waiting? Click \"I've verified\" after clicking the email link." })}</span>
              ) : (
                <>
                  <span
                    aria-hidden="true"
                    style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: "var(--primary)",
                      animation: "pulse 1.4s ease-in-out infinite",
                    }}
                  />
                  <span>{t("onboarding.checkingAutomatically")}</span>
                </>
              )}
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

        {/* ── Step 2: What do you want to learn? ── */}
        {step === 2 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.researchIntentTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.researchIntentSubtitle")}</p>

            <div className="onboarding-form">
              <div className="onboarding-field">
                <label className="field-label" htmlFor="onb-role">
                  {companyName
                    ? t("onboarding.roleTitleLabel", { companyName })
                    : t("onboarding.roleTitleLabelShort")}
                </label>
                <input
                  id="onb-role"
                  type="text"
                  className="field-input"
                  value={roleTitle}
                  onChange={(e) => setRoleTitle(e.target.value)}
                  placeholder={t("onboarding.roleTitlePlaceholder")}
                  disabled={saving}
                  autoFocus
                  autoComplete="organization-title"
                />
              </div>

              <div className="onboarding-field">
                <label className="field-label" htmlFor="onb-occupation">
                  {t("onboarding.researchIntentLabel")}
                </label>
                <textarea
                  id="onb-occupation"
                  className="field-input"
                  value={occupationDescription}
                  onChange={(e) => setOccupationDescription(e.target.value)}
                  placeholder={t("onboarding.researchIntentPlaceholder")}
                  rows={3}
                  style={{ resize: "vertical", lineHeight: 1.6 }}
                  disabled={saving}
                />
              </div>

              <div className="onboarding-field">
                <label className="field-label">{t("onboarding.experienceLabel")}</label>
                <div className="onboarding-chip-grid">
                  {experienceOptions.map((opt) => (
                    <button
                      key={opt.value}
                      className={`onboarding-chip ${researchExperience === opt.value ? "selected" : ""}`}
                      onClick={() => setResearchExperience(opt.value)}
                      disabled={saving}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleAboutYouContinue}
                disabled={saving || !roleTitle.trim() || !occupationDescription.trim() || !researchExperience}
              >
                {saving ? t("onboarding.saving") : t("onboarding.continue")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => setStep(1)}
                disabled={saving}
                style={{ fontSize: 13 }}
              >
                ← {t("onboarding.steps.verify")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Your company ── */}
        {step === 3 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.businessTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.businessSubtitle")}</p>

            <div className="onboarding-form">
              {/* Company name */}
              <div className="onboarding-field">
                <label className="field-label" htmlFor="onboarding-company-name">
                  {t("onboarding.companyNameLabel")}
                </label>
                <input
                  id="onboarding-company-name"
                  type="text"
                  className="field-input"
                  value={companyNameInput}
                  onChange={(e) => setCompanyNameInput(e.target.value)}
                  placeholder={t("onboarding.companyNamePlaceholder")}
                  disabled={saving}
                  autoComplete="organization"
                />
              </div>

              {/* Website URL */}
              <div className="onboarding-field">
                <label className="field-label">
                  {t("onboarding.websiteLabel")}{" "}
                  <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                    {t("onboarding.websiteOptional")}
                  </span>
                </label>
                <input
                  type="url"
                  inputMode="url"
                  autoComplete="url"
                  className="field-input"
                  value={websiteUrl}
                  onChange={(e) => { setWebsiteUrl(e.target.value); setWebsiteHint(null); }}
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
                {websiteHint === "fallback" && !websiteLoading && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: "14px 16px",
                      borderRadius: "var(--radius)",
                      background: "var(--warning-bg, #fffbeb)",
                      border: "1px solid var(--warning-border, #fde68a)",
                      fontSize: 14,
                      lineHeight: 1.5,
                      color: "var(--text-primary)",
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>
                      {t("onboarding.websiteFallbackTitle")}
                    </div>
                    <div style={{ color: "var(--text-secondary)", marginBottom: 10 }}>
                      {t("onboarding.websiteFallbackBody")}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => {
                        setWebsiteHint(null);
                        setManualMode(false);
                        setWebsiteUrl("");
                        lastAttemptedUrlRef.current = "";
                      }}
                      style={{ fontSize: 13, padding: "4px 0", textDecoration: "underline" }}
                    >
                      {t("onboarding.websiteFallbackRetry")}
                    </button>
                  </div>
                )}
                {!businessSummary && !manualMode && !websiteLoading && !websiteHint && (
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

              {/* Business summary — collapsed when AI-drafted, inline when manual */}
              {businessSummary && analysedUrl && !manualMode && !summaryExpanded && (
                <div className="onboarding-field">
                  <div
                    style={{
                      fontSize: 13,
                      color: "var(--text-secondary)",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    <span>✨ {t("onboarding.websiteAutoFilled")}</span>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setSummaryExpanded(true)}
                      disabled={saving}
                      style={{ fontSize: 13, padding: "2px 0", textDecoration: "underline" }}
                    >
                      {t("onboarding.editAiSummary")}
                    </button>
                  </div>
                </div>
              )}

              {(manualMode || summaryExpanded) && (businessSummary || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.businessSummaryLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
                  <textarea
                    className="field-input"
                    value={businessSummary}
                    onChange={(e) => setBusinessSummary(e.target.value)}
                    rows={manualMode ? 3 : 4}
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
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setSummaryExpanded(false)}
                        disabled={saving}
                        style={{ fontSize: 13 }}
                      >
                        {t("onboarding.hideAiSummary")}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Industry chips */}
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

              {/* Primary market */}
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

              {/* Anything else */}
              {(industry || manualMode) && (
                <div className="onboarding-field">
                  <label className="field-label">
                    {t("onboarding.anythingElseLabel")}{" "}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                      {t("onboarding.websiteOptional")}
                    </span>
                  </label>
                  <textarea
                    className="field-input"
                    value={goalsFreeform}
                    onChange={(e) => setGoalsFreeform(e.target.value)}
                    rows={3}
                    placeholder={t("onboarding.anythingElsePlaceholder")}
                    style={{ resize: "vertical", lineHeight: 1.6 }}
                    disabled={saving}
                  />
                </div>
              )}
            </div>

            <div className="welcome-actions" style={{ marginTop: 28 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleCompanyContinue}
                disabled={saving || websiteLoading}
              >
                {saving ? t("onboarding.saving") : t("onboarding.continue")}
              </button>
              <button className="btn btn-ghost" onClick={() => setStep(2)} disabled={saving}>
                ← {t("onboarding.steps.researchGoal")}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Your first study ── */}
        {step === 4 && (
          <div className="onboarding-step">
            <h1 className="welcome-title">{t("onboarding.studyTitle")}</h1>
            <p className="welcome-subtitle">{t("onboarding.studySubtitle")}</p>

            {studyLoading && (
              <div style={{ padding: "40px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
                <span
                  className="spinner"
                  style={{
                    width: 24,
                    height: 24,
                    border: "3px solid var(--primary)",
                    borderTopColor: "transparent",
                    borderRadius: "50%",
                    display: "inline-block",
                    animation: "spin 0.6s linear infinite",
                  }}
                />
                <LoadingCarousel
                  messages={Array.isArray(studyCarouselMessages) && studyCarouselMessages.length > 0
                    ? studyCarouselMessages
                    : ["Designing your study..."]
                  }
                />
              </div>
            )}

            {!studyLoading && studyError && (
              <div className="recap-card" style={{ marginTop: 24 }}>
                <p style={{ color: "var(--text-secondary)", lineHeight: 1.7, margin: 0 }}>
                  {t("onboarding.studyFallback")}
                </p>
              </div>
            )}

            {!studyLoading && !studyError && studyDraft && (
              <div className="recap-card" style={{ marginTop: 24 }}>
                {/* Brief summary */}
                <p style={{ color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.6, margin: "0 0 20px" }}>
                  {studyDraft.brief_summary}
                </p>

                {/* Study title */}
                <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 16px" }}>
                  {studyDraft.study_title}
                </h2>

                {/* Objective */}
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    {t("onboarding.studyObjective")}
                  </div>
                  <div style={{ fontSize: 14, color: "var(--text-primary)", lineHeight: 1.5 }}>
                    {studyDraft.research_objective}
                  </div>
                </div>

                {/* Audience */}
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    {t("onboarding.studyAudience")}
                  </div>
                  <div style={{ fontSize: 14, color: "var(--text-primary)", lineHeight: 1.5 }}>
                    {studyDraft.target_audience}
                  </div>
                </div>

                {/* Duration + sample size chips */}
                <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12, padding: "4px 10px", borderRadius: 999, background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    ⏱ {t("onboarding.studyDuration", { minutes: studyDraft.duration_minutes })}
                  </span>
                  <span style={{ fontSize: 12, padding: "4px 10px", borderRadius: 999, background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    👥 {t("onboarding.studySampleSize", { count: studyDraft.sample_size })}
                  </span>
                </div>

                {/* Questions */}
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
                    {t("onboarding.studyQuestions")}
                  </div>
                  <ol style={{ paddingLeft: 22, margin: 0 }}>
                    {studyDraft.questions.map((q, i) => (
                      <li key={i} style={{ fontSize: 14, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 6 }}>
                        {q.main_question}
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}

            <div className="welcome-actions" style={{ marginTop: 32 }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleCreateStudy}
                disabled={saving || studyLoading || !studyDraft}
              >
                {saving ? t("onboarding.creatingStudy") : t("onboarding.createThisStudy")}
              </button>
              {saving && (
                <p style={{ fontSize: 13, color: "var(--text-tertiary)", margin: "8px 0 0", textAlign: "center" }}>
                  {t("onboarding.creatingStudyDesc")}
                </p>
              )}
              <button
                className="btn btn-ghost"
                onClick={handleStartFromBlank}
                disabled={saving || studyLoading}
                style={{ fontSize: 13 }}
              >
                {t("onboarding.startFromBlank")}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => setStep(3)}
                disabled={saving}
                style={{ fontSize: 13, color: "var(--text-muted)" }}
              >
                ← {t("onboarding.goBackAdjust")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Silence unused-variable warning
void EXPERIENCE_VALUES;
