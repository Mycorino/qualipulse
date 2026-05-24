/**
 * Phase 1 of the hybrid onboarding — a 3-step structured wizard that
 * sits in front of the conversational Research Copilot. Sets the deal
 * upfront (10 free interview credits / 3 free transcript views /
 * unlock with a plan), captures the qualification data we need for
 * downstream personalisation, and surfaces email verification as a
 * load-bearing action (credits are gated on verified email).
 *
 * Phase 2 (the existing conversational onboarding in Welcome.tsx)
 * kicks in after step 3 — the agent reads the captured data from
 * the snapshot and opens with personalised context rather than
 * re-asking.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  resendVerification,
  saveOnboardingProfile,
  type CompanyResponse,
} from "../api/auth";
import { useToast } from "../components/Toast";

interface WelcomeSetupProps {
  me: CompanyResponse;
  onProfileSaved: (next: CompanyResponse) => void;
  onComplete: () => void;
}

type StepId = 1 | 2 | 3;

const ROLES = [
  "Product Manager",
  "UX Researcher",
  "Designer",
  "Founder / CEO",
  "Marketing",
  "Other",
];
const TEAM_SIZES = ["1–10", "11–50", "51–200", "201–1000", "1000+"];
const USE_CASES = [
  "Product discovery",
  "Concept testing",
  "Onboarding research",
  "Brand / messaging",
  "Usability",
  "Other",
];

export default function WelcomeSetup({
  me,
  onProfileSaved,
  onComplete,
}: WelcomeSetupProps) {
  const { t } = useTranslation("welcome_setup");
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<StepId>(1);
  const [saving, setSaving] = useState(false);

  const [companyName, setCompanyName] = useState(me.name || "");
  const [role, setRole] = useState(me.role || "");
  const [teamSize, setTeamSize] = useState(me.company_size || "");
  const [useCase, setUseCase] = useState(me.use_case || "");
  const [intent, setIntent] = useState<"team" | "solo" | "">(
    me.company_size && me.company_size !== "1–10" ? "team" : "",
  );
  const [studyReadiness, setStudyReadiness] = useState<
    "concrete" | "evaluating" | ""
  >("");

  const step1Valid = !!companyName.trim() && !!role && !!teamSize;
  const step2Valid = !!useCase && !!intent && !!studyReadiness;

  const recommendedPlan = useMemo(() => {
    if (teamSize === "1–10") return { name: "Exploration", monthly: "€89" };
    if (teamSize === "11–50" || teamSize === "51–200")
      return { name: "Team", monthly: "€299" };
    if (teamSize === "201–1000" || teamSize === "1000+")
      return { name: "Agency", monthly: "€799" };
    return null;
  }, [teamSize]);

  const saveAndAdvance = async () => {
    setSaving(true);
    try {
      if (step === 1) {
        const next = await saveOnboardingProfile({
          name: companyName.trim(),
          role,
          company_size: teamSize,
        });
        onProfileSaved(next);
        setStep(2);
      } else if (step === 2) {
        const next = await saveOnboardingProfile({
          use_case: useCase,
          decision_role:
            intent === "team" ? "I'm helping someone decide" : "I'll decide",
        });
        onProfileSaved(next);
        setStep(3);
      } else {
        onComplete();
      }
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    try {
      localStorage.setItem("qp_welcome_setup_skipped", "1");
    } catch {
      /* private-mode no-op */
    }
    onComplete();
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !saving) {
        if (step === 1 && step1Valid) saveAndAdvance();
        else if (step === 2 && step2Valid) saveAndAdvance();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, step1Valid, step2Valid, saving]);

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
        <ol
          className="welcome-setup__progress"
          aria-label={t("progress_aria")}
        >
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
              <span className="welcome-setup__progress-dot" aria-hidden>
                {n < step ? "✓" : n}
              </span>
              <span className="welcome-setup__progress-label">
                {t(`step_${n}_label`)}
              </span>
            </li>
          ))}
        </ol>

        {step === 1 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_1_title")}</h1>
            <p className="welcome-setup__sub">{t("step_1_sub")}</p>

            <label className="welcome-setup__field">
              <span className="welcome-setup__field-label">
                {t("field_company")}
              </span>
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
              <span className="welcome-setup__field-label">
                {t("field_role")}
              </span>
              <div className="welcome-setup__chips" role="radiogroup">
                {ROLES.map((r) => (
                  <button
                    key={r}
                    type="button"
                    role="radio"
                    aria-checked={role === r}
                    className={`welcome-setup__chip ${
                      role === r ? "welcome-setup__chip--active" : ""
                    }`}
                    onClick={() => setRole(r)}
                    disabled={saving}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">
                {t("field_team_size")}
              </span>
              <div className="welcome-setup__chips" role="radiogroup">
                {TEAM_SIZES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={teamSize === s}
                    className={`welcome-setup__chip ${
                      teamSize === s ? "welcome-setup__chip--active" : ""
                    }`}
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
                className="btn btn-primary"
                onClick={saveAndAdvance}
                disabled={!step1Valid || saving}
              >
                {saving ? t("saving") : t("step_1_cta")}
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_2_title")}</h1>
            <p className="welcome-setup__sub">{t("step_2_sub")}</p>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">
                {t("field_use_case")}
              </span>
              <div className="welcome-setup__chips" role="radiogroup">
                {USE_CASES.map((u) => (
                  <button
                    key={u}
                    type="button"
                    role="radio"
                    aria-checked={useCase === u}
                    className={`welcome-setup__chip ${
                      useCase === u ? "welcome-setup__chip--active" : ""
                    }`}
                    onClick={() => setUseCase(u)}
                    disabled={saving}
                  >
                    {u}
                  </button>
                ))}
              </div>
            </div>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">
                {t("field_intent")}
              </span>
              <div className="welcome-setup__radio-list">
                <label className="welcome-setup__radio">
                  <input
                    type="radio"
                    name="intent"
                    checked={intent === "solo"}
                    onChange={() => setIntent("solo")}
                    disabled={saving}
                  />
                  <span>{t("intent_solo")}</span>
                </label>
                <label className="welcome-setup__radio">
                  <input
                    type="radio"
                    name="intent"
                    checked={intent === "team"}
                    onChange={() => setIntent("team")}
                    disabled={saving}
                  />
                  <span>{t("intent_team")}</span>
                </label>
              </div>
            </div>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">
                {t("field_readiness")}
              </span>
              <div className="welcome-setup__radio-list">
                <label className="welcome-setup__radio">
                  <input
                    type="radio"
                    name="readiness"
                    checked={studyReadiness === "concrete"}
                    onChange={() => setStudyReadiness("concrete")}
                    disabled={saving}
                  />
                  <span>{t("readiness_concrete")}</span>
                </label>
                <label className="welcome-setup__radio">
                  <input
                    type="radio"
                    name="readiness"
                    checked={studyReadiness === "evaluating"}
                    onChange={() => setStudyReadiness("evaluating")}
                    disabled={saving}
                  />
                  <span>{t("readiness_evaluating")}</span>
                </label>
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
                onClick={saveAndAdvance}
                disabled={!step2Valid || saving}
              >
                {saving ? t("saving") : t("step_2_cta")}
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="welcome-setup__card welcome-setup__card--deal">
            <div className="welcome-setup__eyebrow">
              ✦ {t("step_3_eyebrow")}
            </div>
            <h1 className="welcome-setup__title">{t("step_3_title")}</h1>
            <p className="welcome-setup__sub">{t("step_3_sub")}</p>

            <div className="welcome-setup__deal-grid">
              <div className="welcome-setup__deal-item">
                <div className="welcome-setup__deal-number">10</div>
                <div className="welcome-setup__deal-label">
                  {t("deal_run_label")}
                </div>
                <p className="welcome-setup__deal-body">{t("deal_run_body")}</p>
              </div>
              <div className="welcome-setup__deal-item">
                <div className="welcome-setup__deal-number">3</div>
                <div className="welcome-setup__deal-label">
                  {t("deal_view_label")}
                </div>
                <p className="welcome-setup__deal-body">{t("deal_view_body")}</p>
              </div>
              <div className="welcome-setup__deal-item">
                <div className="welcome-setup__deal-number">∞</div>
                <div className="welcome-setup__deal-label">
                  {t("deal_unlock_label")}
                </div>
                <p className="welcome-setup__deal-body">
                  {recommendedPlan
                    ? t("deal_unlock_body_with_plan", {
                        planName: recommendedPlan.name,
                        monthly: recommendedPlan.monthly,
                      })
                    : t("deal_unlock_body_generic")}
                </p>
              </div>
            </div>

            {!me.email_verified ? (
              <div className="welcome-setup__verify">
                <div className="welcome-setup__verify-eyebrow">
                  {t("verify_eyebrow")}
                </div>
                <p className="welcome-setup__verify-body">
                  {t("verify_body", { email: me.email })}
                </p>
                <div className="welcome-setup__verify-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() =>
                      resendVerification()
                        .then(() => toast(t("toast_resend_ok"), "success"))
                        .catch(() => toast(t("toast_resend_failed"), "error"))
                    }
                  >
                    {t("verify_resend")}
                  </button>
                  <span className="welcome-setup__verify-hint">
                    {t("verify_hint_post_action")}
                  </span>
                </div>
              </div>
            ) : (
              <div className="welcome-setup__verify welcome-setup__verify--done">
                ✓ {t("verify_done", { email: me.email })}
              </div>
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
                className="btn btn-primary welcome-setup__primary-cta"
                onClick={saveAndAdvance}
                disabled={saving}
              >
                {saving ? t("saving") : t("step_3_cta")}
              </button>
            </div>
          </section>
        )}
      </div>

      <footer className="welcome-setup__foot">
        <button
          type="button"
          className="welcome-setup__foot-link"
          onClick={() => navigate("/dashboard")}
        >
          {t("foot_dashboard")}
        </button>
      </footer>
    </div>
  );
}
