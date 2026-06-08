import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  getMe,
  completeOnboarding,
  saveOnboardingProfile,
  getOnboardingSuggestions,
  type CompanyResponse,
  type OnboardingSuggestions,
} from "../api/auth";
import { setCachedOnboarded } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import LanguageSwitcher from "../components/LanguageSwitcher";

const ROLES = [
  "Product Manager",
  "UX Researcher",
  "Designer",
  "Founder / CEO",
  "Marketing",
  "Other",
];
const TEAM_SIZES = ["1–10", "11–50", "51–200", "201–1000", "1000+"];

type StepId = 1 | 2 | 3;

function inferStartStep(me: CompanyResponse): StepId {
  if (me.role && me.company_size) return 3;
  if (me.name) return 2;
  return 1;
}

export default function Welcome() {
  const { t, i18n } = useTranslation("welcome_setup");
  const navigate = useNavigate();
  const { toast } = useToast();

  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const [step, setStep] = useState<StepId>(1);
  const [saving, setSaving] = useState(false);

  // Step 1
  const [companyName, setCompanyName] = useState("");
  // Step 2
  const [role, setRole] = useState("");
  const [roleOther, setRoleOther] = useState("");
  const [teamSize, setTeamSize] = useState("");
  // Step 3
  const [suggestions, setSuggestions] = useState<OnboardingSuggestions | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedUseCases, setSelectedUseCases] = useState<Set<string>>(new Set());

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCompanyName(data.name || "");
        setRole(data.role || "");
        if (data.role && !ROLES.includes(data.role)) setRoleOther(data.role);
        setTeamSize(data.company_size || "");
        const rawUc = data.selected_use_cases as unknown;
        if (rawUc && typeof rawUc === "string") {
          setSelectedUseCases(new Set(rawUc.split(",").map((s: string) => s.trim()).filter(Boolean)));
        } else if (Array.isArray(rawUc) && rawUc.length) {
          setSelectedUseCases(new Set(rawUc));
        }
        const startStep = inferStartStep(data);
        setStep(startStep);
        if (startStep === 3) fetchSuggestions();
      })
      .catch(() => navigate("/login", { replace: true }))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const roleResolved = role === "Other" ? roleOther.trim() : role;
  const step1Valid = !!companyName.trim();
  const step2Valid = !!roleResolved && !!teamSize;

  async function fetchSuggestions() {
    setSuggestionsLoading(true);
    try {
      const data = await getOnboardingSuggestions();
      setSuggestions(data);
    } catch {
      setSuggestions({
        use_cases: i18n.language.startsWith("fr")
          ? ["Découverte produit", "Test de concept", "Recherche onboarding", "Marque & messaging", "Tests d'utilisabilité"]
          : ["Product discovery", "Concept testing", "Onboarding research", "Brand & messaging", "Usability testing"],
        profile_summary: null,
        business_summary: null,
      });
    } finally {
      setSuggestionsLoading(false);
    }
  }

  async function handleStep1Next() {
    setSaving(true);
    try {
      const lang = (i18n.language || "en").startsWith("fr") ? "fr" : "en";
      const next = await saveOnboardingProfile({
        name: companyName.trim(),
        preferred_language: lang,
      });
      setMe(next);
      setStep(2);
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleStep2Next() {
    setSaving(true);
    try {
      const next = await saveOnboardingProfile({
        role: roleResolved || role,
        company_size: teamSize,
      });
      setMe(next);
      setStep(3);
      fetchSuggestions();
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleComplete() {
    setSaving(true);
    try {
      const casesArray = Array.from(selectedUseCases);
      await completeOnboarding({
        selected_use_cases: casesArray.length ? casesArray.join(",") : undefined,
        use_case: casesArray[0] || undefined,
      });
      setCachedOnboarded(true);
      navigate("/dashboard", { replace: true });
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  }

  function handleSkip() {
    completeOnboarding({})
      .then(() => {
        setCachedOnboarded(true);
        navigate("/dashboard", { replace: true });
      })
      .catch(() => {
        setCachedOnboarded(true);
        navigate("/dashboard", { replace: true });
      });
  }

  function toggleUseCase(uc: string) {
    setSelectedUseCases((prev) => {
      const next = new Set(prev);
      if (next.has(uc)) next.delete(uc);
      else next.add(uc);
      return next;
    });
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !saving) {
        if (step === 1 && step1Valid) handleStep1Next();
        else if (step === 2 && step2Valid) handleStep2Next();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, step1Valid, step2Valid, saving, companyName, role, roleOther, teamSize]);

  if (loading || !me) {
    return (
      <div className="welcome-setup">
        <header className="welcome-setup__bar">
          <span className="welcome-setup__brand">QualiPulse</span>
        </header>
        <div className="welcome-setup__main" style={{ alignItems: "center", justifyContent: "center" }}>
          <div className="spinner" />
        </div>
      </div>
    );
  }

  return (
    <div className="welcome-setup">
      <header className="welcome-setup__bar">
        <span className="welcome-setup__brand">QualiPulse</span>
        <button
          type="button"
          className="welcome-setup__skip"
          onClick={handleSkip}
          disabled={saving}
        >
          {t("header_skip")}
        </button>
      </header>

      <div className="welcome-setup__main">
        <ol className="welcome-setup__progress" aria-label={t("progress_aria")}>
          {[1, 2, 3].map((n) => (
            <li
              key={n}
              className={`welcome-setup__progress-step ${
                n === step
                  ? "welcome-setup__progress-step--active"
                  : n < step
                    ? "welcome-setup__progress-step--done"
                    : ""
              }`}
            >
              <span className="welcome-setup__progress-dot" aria-hidden="true">
                {n < step ? "✓" : n}
              </span>
              <span className="welcome-setup__progress-label">
                {t(`step_${n}_label`)}
              </span>
            </li>
          ))}
        </ol>

        {/* ── Step 1: Company name + language ── */}
        {step === 1 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_1_title")}</h1>
            <p className="welcome-setup__sub">{t("step_1_sub")}</p>

            <label className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("field_company")}</span>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder={t("field_company_placeholder")}
                autoFocus
                disabled={saving}
              />
            </label>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("step_1_language_label")}</span>
              <LanguageSwitcher />
            </div>

            <div className="welcome-setup__actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleStep1Next}
                disabled={!step1Valid || saving}
              >
                {saving ? t("saving") : t("step_1_cta")}
              </button>
            </div>
          </section>
        )}

        {/* ── Step 2: Role + Company size ── */}
        {step === 2 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_2_title")}</h1>
            <p className="welcome-setup__sub">{t("step_2_sub")}</p>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("field_role")}</span>
              <div className="welcome-setup__chips" role="radiogroup">
                {ROLES.map((r) => (
                  <button
                    key={r}
                    type="button"
                    role="radio"
                    aria-checked={role === r}
                    className={`welcome-setup__chip ${role === r ? "welcome-setup__chip--active" : ""}`}
                    onClick={() => setRole(r)}
                    disabled={saving}
                  >
                    {r}
                  </button>
                ))}
              </div>
              {role === "Other" && (
                <input
                  type="text"
                  className="welcome-setup__other-input"
                  value={roleOther}
                  onChange={(e) => setRoleOther(e.target.value)}
                  placeholder={t("role_other_placeholder")}
                  aria-label={t("role_other_placeholder")}
                  autoFocus
                  disabled={saving}
                />
              )}
            </div>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("field_team_size")}</span>
              <div className="welcome-setup__chips" role="radiogroup">
                {TEAM_SIZES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={teamSize === s}
                    className={`welcome-setup__chip ${teamSize === s ? "welcome-setup__chip--active" : ""}`}
                    onClick={() => setTeamSize(s)}
                    disabled={saving}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div className="welcome-setup__actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setStep(1)}
                disabled={saving}
              >
                {t("back")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleStep2Next}
                disabled={!step2Valid || saving}
              >
                {saving ? t("saving") : t("step_2_cta")}
              </button>
            </div>
          </section>
        )}

        {/* ── Step 3: AI-suggested use cases + profile summary ── */}
        {step === 3 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_3_title")}</h1>
            <p className="welcome-setup__sub">{t("step_3_sub")}</p>

            {suggestionsLoading ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "32px 0" }}>
                <div className="spinner" />
                <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                  {t("step_3_loading")}
                </span>
              </div>
            ) : (
              <>
                {suggestions && (
                  <div className="welcome-setup__field">
                    <span className="welcome-setup__field-label">{t("step_3_use_cases_label")}</span>
                    <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", margin: 0 }}>
                      {t("step_3_use_cases_hint")}
                    </p>
                    <div className="welcome-setup__chips">
                      {suggestions.use_cases.map((uc) => (
                        <button
                          key={uc}
                          type="button"
                          className={`welcome-setup__chip ${selectedUseCases.has(uc) ? "welcome-setup__chip--active" : ""}`}
                          onClick={() => toggleUseCase(uc)}
                          disabled={saving}
                        >
                          {uc}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {suggestions?.profile_summary && (
                  <div className="welcome-setup__summary-card">
                    <span className="welcome-setup__field-label">{t("step_3_summary_label")}</span>
                    <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", margin: "4px 0 0", lineHeight: 1.5 }}>
                      {suggestions.profile_summary}
                    </p>
                  </div>
                )}
              </>
            )}

            <div className="welcome-setup__actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setStep(2)}
                disabled={saving}
              >
                {t("back")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleComplete}
                disabled={saving || suggestionsLoading}
              >
                {saving ? t("saving") : t("step_3_cta")}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
