import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { savePanelProfile, PanelProfileData } from "../api/interviews";

/**
 * Pre-interview profiling questionnaire (one question per screen, all-tap,
 * grandma-friendly). Maps to the reusable PanelProfile. Runs after consent,
 * before the study's screening questions.
 *
 * Self-contained: owns its own stepper + the savePanelProfile call. The
 * parent only needs the handful of fields used to create the participant
 * row + the chosen language, returned via onComplete.
 */

// ISO 3166-1 alpha-2 codes for the country picker. Names are localized at
// render time via Intl.DisplayNames — no per-language country translations
// needed. Stored to the backend as the English display name for stable
// segmentation.
const COUNTRY_CODES = [
  "US", "GB", "FR", "DE", "ES", "IT", "PT", "NL", "BE", "CH", "AT", "IE",
  "SE", "NO", "DK", "FI", "PL", "CZ", "GR", "RO", "HU", "BG", "HR", "SK",
  "CA", "MX", "BR", "AR", "CL", "CO", "PE",
  "AU", "NZ",
  "JP", "CN", "KR", "IN", "ID", "SG", "MY", "TH", "PH", "VN",
  "AE", "SA", "IL", "TR",
  "ZA", "NG", "EG", "KE", "MA",
];

const WORK_EMPLOYMENT = new Set(["full_time", "part_time", "freelance"]);

type StepKey =
  | "firstName" | "country" | "age" | "gender" | "education" | "employment"
  | "industry" | "jobFunction" | "seniority" | "companySize" | "consent";

interface Answers {
  firstName: string;
  country: string; // ISO code
  age: string;
  gender: string;
  education: string;
  employment: string;
  industry: string;
  jobFunction: string;
  seniority: string;
  companySize: string;
  consent: "" | "yes" | "no";
}

export interface QuestionnaireResult {
  firstName: string;
  ageRange?: string;
  country?: string; // English display name
  preferredLanguage: string;
  panelConsent: boolean;
}

interface Props {
  linkToken: string;
  email: string;
  sessionToken: string | null;
  initialFirstName?: string;
  onComplete: (data: QuestionnaireResult) => void;
}

// Single-select chip steps and the i18n option-group each maps to.
const CHIP_GROUPS: Record<string, string> = {
  age: "ageOptions",
  gender: "genderOptions",
  education: "educationOptions",
  employment: "employmentOptions",
  industry: "industryOptions",
  jobFunction: "jobFunctionOptions",
  seniority: "seniorityOptions",
  companySize: "companySizeOptions",
};

const OPTION_ORDER: Record<string, string[]> = {
  age: ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
  gender: ["male", "female", "non_binary", "prefer_not"],
  education: ["high_school", "bachelor", "master", "phd", "other"],
  employment: ["full_time", "part_time", "freelance", "student", "unemployed", "retired"],
  industry: ["technology", "healthcare", "finance", "retail", "education", "manufacturing", "media", "public", "hospitality", "other"],
  jobFunction: ["engineering", "product", "marketing", "design", "sales", "finance", "operations", "hr", "executive", "other"],
  seniority: ["junior", "mid", "senior", "manager", "director", "c_suite"],
  companySize: ["1", "2-10", "11-50", "51-200", "201-1000", "1000+"],
};

export default function ParticipantQuestionnaire({
  linkToken, email, sessionToken, initialFirstName, onComplete,
}: Props) {
  const { t, i18n } = useTranslation("interview");
  const lang = (i18n.language || "en").slice(0, 2);

  const [answers, setAnswers] = useState<Answers>({
    firstName: initialFirstName || "",
    country: "", age: "", gender: "", education: "", employment: "",
    industry: "", jobFunction: "", seniority: "", companySize: "", consent: "",
  });
  const [stepIndex, setStepIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [countryQuery, setCountryQuery] = useState("");

  // Step list is derived from employment so non-workers skip the work block.
  const steps: StepKey[] = useMemo(() => {
    const base: StepKey[] = ["firstName", "country", "age", "gender", "education", "employment"];
    const work: StepKey[] = WORK_EMPLOYMENT.has(answers.employment)
      ? ["industry", "jobFunction", "seniority", "companySize"]
      : [];
    return [...base, ...work, "consent"];
  }, [answers.employment]);

  const safeIndex = Math.min(stepIndex, steps.length - 1);
  const step = steps[safeIndex];
  const isLast = safeIndex === steps.length - 1;
  const progress = ((safeIndex + 1) / steps.length) * 100;

  // Localized country names (display) + a stable English name (storage).
  const regionNames = useMemo(() => {
    try { return new Intl.DisplayNames([lang], { type: "region" }); }
    catch { return null; }
  }, [lang]);
  const regionNamesEN = useMemo(() => {
    try { return new Intl.DisplayNames(["en"], { type: "region" }); }
    catch { return null; }
  }, []);
  const countryLabel = (code: string) => regionNames?.of(code) || code;
  const countryLabelEN = (code: string) => regionNamesEN?.of(code) || code;

  const sortedCountries = useMemo(() => {
    const list = COUNTRY_CODES.map((c) => ({ code: c, label: countryLabel(c) }));
    list.sort((a, b) => a.label.localeCompare(b.label, lang));
    const q = countryQuery.trim().toLowerCase();
    return q ? list.filter((c) => c.label.toLowerCase().includes(q)) : list;
  }, [countryQuery, lang, regionNames]);

  function goNext() {
    if (isLast) { void finish(); return; }
    setStepIndex(safeIndex + 1);
  }
  function goBack() {
    setError("");
    setStepIndex((s) => Math.max(0, Math.min(s, steps.length - 1) - 1));
  }
  function pickChip(field: keyof Answers, value: string) {
    setAnswers((a) => ({ ...a, [field]: value }));
    // Auto-advance one tick later so the selection paints first.
    setTimeout(() => {
      if (isLast) void finish({ ...answers, [field]: value });
      else setStepIndex((s) => s + 1);
    }, 140);
  }

  async function finish(final?: Answers) {
    const a = final || answers;
    setSaving(true);
    setError("");
    const englishCountry = a.country ? String(countryLabelEN(a.country)) : undefined;
    try {
      if (sessionToken) {
        const payload: PanelProfileData = {
          email,
          session_token: sessionToken,
          first_name: a.firstName.trim() || undefined,
          age_range: a.age || undefined,
          gender: a.gender || undefined,
          country: englishCountry,
          education: a.education || undefined,
          employment_status: a.employment || undefined,
          job_function: WORK_EMPLOYMENT.has(a.employment) ? (a.jobFunction || undefined) : undefined,
          seniority: WORK_EMPLOYMENT.has(a.employment) ? (a.seniority || undefined) : undefined,
          industry: WORK_EMPLOYMENT.has(a.employment) ? (a.industry || undefined) : undefined,
          company_size: WORK_EMPLOYMENT.has(a.employment) ? (a.companySize || undefined) : undefined,
          preferred_language: lang,
          panel_consent: a.consent === "yes",
          tag_ids: [],
        };
        await savePanelProfile(linkToken, payload);
      }
      onComplete({
        firstName: a.firstName.trim(),
        ageRange: a.age || undefined,
        country: englishCountry,
        preferredLanguage: lang,
        panelConsent: a.consent === "yes",
      });
    } catch {
      setError(t("questionnaire.saveError"));
      setSaving(false);
    }
  }

  // ── Render one step ────────────────────────────────────────────────────
  function renderStep() {
    if (step === "firstName") {
      const trimmed = answers.firstName.trim();
      return (
        <div className="profiling-question">
          <h2 className="profiling-label">{t("questionnaire.firstNameQ")}</h2>
          <p className="questionnaire-help">{t("questionnaire.firstNameHelp")}</p>
          <input
            type="text"
            className="field-input questionnaire-text-input"
            value={answers.firstName}
            onChange={(e) => setAnswers((a) => ({ ...a, firstName: e.target.value }))}
            placeholder={t("questionnaire.firstNamePlaceholder")}
            autoFocus
            autoComplete="given-name"
            onKeyDown={(e) => { if (e.key === "Enter" && trimmed) goNext(); }}
          />
          <button className="btn btn-primary questionnaire-continue" disabled={!trimmed} onClick={goNext}>
            {t("questionnaire.continue")} →
          </button>
        </div>
      );
    }

    if (step === "country") {
      return (
        <div className="profiling-question">
          <h2 className="profiling-label">{t("questionnaire.countryQ")}</h2>
          <input
            type="text"
            className="field-input questionnaire-text-input"
            value={countryQuery}
            onChange={(e) => setCountryQuery(e.target.value)}
            placeholder={t("questionnaire.countrySearch")}
            autoComplete="country-name"
          />
          <div className="questionnaire-country-list">
            {sortedCountries.map((c) => (
              <button
                key={c.code}
                className={`profiling-option-btn${answers.country === c.code ? " selected" : ""}`}
                onClick={() => pickChip("country", c.code)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      );
    }

    if (step === "consent") {
      // Soft, low-pressure framing: a single "accept & continue" primary with
      // a quiet decline. Anyone who declines here is re-prompted (with a fuller
      // paid-studies explanation) after the interview.
      return (
        <div className="profiling-question">
          <h2 className="profiling-label">{t("questionnaire.consentQ")}</h2>
          <p className="questionnaire-help">{t("questionnaire.consentHelp")}</p>
          <button
            className="btn btn-primary questionnaire-continue"
            onClick={() => pickChip("consent", "yes")}
            disabled={saving}
          >
            {t("questionnaire.consentAccept")}
          </button>
          <button
            className="questionnaire-decline-btn"
            onClick={() => pickChip("consent", "no")}
            disabled={saving}
          >
            {t("questionnaire.consentDecline")}
          </button>
        </div>
      );
    }

    // Generic single-select chip step (age / gender / education / employment /
    // industry / jobFunction / seniority / companySize).
    const group = CHIP_GROUPS[step];
    const questionText = t(`questionnaire.${step}Q`);
    return (
      <div className="profiling-question">
        <h2 className="profiling-label">{questionText}</h2>
        <div className="profiling-options">
          {OPTION_ORDER[step].map((opt) => (
            <button
              key={opt}
              className={`profiling-option-btn${(answers as any)[step] === opt ? " selected" : ""}`}
              onClick={() => pickChip(step as keyof Answers, opt)}
            >
              {t(`questionnaire.${group}.${opt}`)}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const canSkip = step !== "firstName" && step !== "consent";

  return (
    <div className="interview-page">
      <div className="interview-container interview-profiling">
        <div className="profiling-header">
          <p className="profiling-intro">{t("questionnaire.intro")}</p>
          <p className="questionnaire-subtitle">{t("questionnaire.introSubtitle")}</p>
          <div className="profiling-progress-bar">
            <div className="profiling-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="profiling-step-label">
            {t("questionnaire.progress", { current: safeIndex + 1, total: steps.length })}
          </p>
        </div>

        {renderStep()}

        {error && <div className="error-banner" role="alert">{error}</div>}
        {saving && <p className="profiling-step-label">{t("questionnaire.saving")}</p>}

        <div className="questionnaire-nav">
          {safeIndex > 0 && !saving && (
            <button className="profiling-back-btn" onClick={goBack}>
              ← {t("questionnaire.back")}
            </button>
          )}
          {canSkip && !saving && (
            <button className="questionnaire-skip-btn" onClick={goNext}>
              {t("questionnaire.skip")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
