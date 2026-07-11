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

// Two-level role picker: job family → specific role. Labels are i18n'd
// (welcome_setup: roleFamilies.* and roles.*). We persist the canonical
// EN role label to Company.role so backend personalisation stays stable
// regardless of UI language. The "other" family reveals a free-text input.
const ROLE_FAMILIES: { key: string; roles: string[] }[] = [
  { key: "product", roles: ["product_manager", "head_of_product", "product_owner"] },
  { key: "design", roles: ["product_designer", "ux_ui_designer", "design_lead"] },
  { key: "research", roles: ["ux_researcher", "market_researcher", "insights_data"] },
  { key: "marketing", roles: ["product_marketing", "brand_marketing", "growth"] },
  { key: "sales_cs", roles: ["sales", "customer_success", "support"] },
  { key: "data", roles: ["data_analyst", "data_scientist", "product_analyst"] },
  { key: "ops", roles: ["operations", "strategy_bizops", "project_manager"] },
  { key: "people", roles: ["hr_people_ops", "recruiting", "learning_dev"] },
  { key: "engineering", roles: ["engineer", "engineering_manager", "cto"] },
  { key: "leadership", roles: ["founder_ceo", "exec"] },
  { key: "consulting", roles: ["consultant", "agency_lead", "independent"] },
  { key: "other", roles: [] },
];
const ALL_ROLE_KEYS = ROLE_FAMILIES.flatMap((f) => f.roles);
// Sentinel role chip appended to every family's role list — reveals the same
// free-text input as the "other" family, for people whose field matches a
// family but whose exact role isn't listed.
const ROLE_OTHER = "__other";
const TEAM_SIZES = ["1–10", "11–50", "51–200", "201–1000", "1000+"];

type StepId = 1 | 2 | 3;

function inferStartStep(me: CompanyResponse): StepId {
  // Fresh Google signups arrive with a placeholder company name derived from
  // the email local-part (set by the OAuth callback). Start them on step 1 so
  // they can correct it — the field is prefilled, so it's one click if right.
  if (localStorage.getItem("qp_google_new_signup") === "1") {
    localStorage.removeItem("qp_google_new_signup");
    return 1;
  }
  if (me.role && me.company_size) return 3;
  if (me.name) return 2;
  return 1;
}

export default function Welcome() {
  const { t, i18n } = useTranslation("welcome_setup");
  // Canonical EN role label (used for persistence) regardless of UI language.
  const enT = i18n.getFixedT("en", "welcome_setup");
  const navigate = useNavigate();
  const { toast } = useToast();

  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const [step, setStep] = useState<StepId>(1);
  const [saving, setSaving] = useState(false);
  // Airlock finale: after completion we show a workspace-handoff screen
  // instead of navigating cold — it previews the seeded example and
  // absorbs the few seconds the backend needs to finish seeding it.
  const [done, setDone] = useState(false);

  // Step 1
  const [companyName, setCompanyName] = useState("");
  // Step 2 — job family → role (two levels)
  const [roleFamily, setRoleFamily] = useState("");
  const [roleKey, setRoleKey] = useState("");
  const [roleOther, setRoleOther] = useState("");
  const [teamSize, setTeamSize] = useState("");
  // Step 3 — split into two phases so the user's own words drive the AI:
  //   'ask'    → free-text goal first (fed to the model)
  //   'themes' → the generated theme chips to confirm/expand
  const [phase3, setPhase3] = useState<"ask" | "themes">("ask");
  const [suggestions, setSuggestions] = useState<OnboardingSuggestions | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedUseCases, setSelectedUseCases] = useState<Set<string>>(new Set());
  // Free-form goals — the wizard captures almost nothing personal, so this
  // is the one place users can say what they're actually working on. Saved
  // to Company.goals_freeform and fed back into the Haiku suggestions.
  const [goals, setGoals] = useState("");
  // What goals_freeform the current `suggestions` were generated from —
  // gates the "Refine" button so it only lights up on real changes.
  const [goalsUsed, setGoalsUsed] = useState("");

  useEffect(() => {
    getMe()
      .then((data) => {
        setMe(data);
        setCompanyName(data.name || "");
        const storedRole = (data.role || "").trim();
        if (storedRole) {
          const match = ALL_ROLE_KEYS.find((rk) => enT(`roles.${rk}`) === storedRole);
          if (match) {
            setRoleKey(match);
            setRoleFamily(ROLE_FAMILIES.find((f) => f.roles.includes(match))?.key || "");
          } else {
            setRoleFamily("other");
            setRoleOther(storedRole);
          }
        }
        setTeamSize(data.company_size || "");
        setGoals(data.goals_freeform || "");
        setGoalsUsed(data.goals_freeform || "");
        const rawUc = data.selected_use_cases as unknown;
        if (rawUc && typeof rawUc === "string") {
          setSelectedUseCases(new Set(rawUc.split(",").map((s: string) => s.trim()).filter(Boolean)));
        } else if (Array.isArray(rawUc) && rawUc.length) {
          setSelectedUseCases(new Set(rawUc));
        }
        const startStep = inferStartStep(data);
        setStep(startStep);
        // A returning user who already told us their goal (or picked themes
        // before) skips straight to the themes phase; everyone else starts on
        // the ask phase so their own words drive the first generation.
        if (startStep === 3) {
          const hadGoals = !!(data.goals_freeform || "").trim();
          const hadCases =
            (typeof rawUc === "string" && rawUc.trim().length > 0) ||
            (Array.isArray(rawUc) && rawUc.length > 0);
          if (hadGoals || hadCases) {
            setPhase3("themes");
            // Sonnet only pays off when there's a goal to anchor on.
            fetchSuggestions(hadGoals ? "sonnet" : "haiku");
          }
        }
      })
      .catch(() => navigate("/login", { replace: true }))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const roleResolved =
    roleFamily === "other" || roleKey === ROLE_OTHER
      ? roleOther.trim()
      : roleKey
        ? enT(`roles.${roleKey}`)
        : "";
  const step1Valid = !!companyName.trim();
  const step2Valid = !!roleResolved && !!teamSize;

  // `model` routes to the fast (haiku) or high-quality (sonnet) tier —
  // the caller picks based on whether the user gave a free-text goal.
  async function fetchSuggestions(model?: "haiku" | "sonnet") {
    setSuggestionsLoading(true);
    try {
      const data = await getOnboardingSuggestions(model);
      setSuggestions(data);
    } catch {
      setSuggestions({
        use_cases: i18n.language.startsWith("fr")
          ? ["Pourquoi les utilisateurs décrochent", "Ce qui favorise la fidélité", "Comment les gens font leur choix", "Où l'expérience crée de la friction", "Ce que les clients valorisent le plus"]
          : ["Why users drop off", "What drives loyalty and repeat use", "How people choose between options", "Where the experience creates friction", "What customers value most"],
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
        role: roleResolved,
        company_size: teamSize,
      });
      setMe(next);
      // Land on the ask phase — suggestions are NOT fetched yet, so the
      // user's own words (entered next) become the primary input to the model.
      setPhase3("ask");
      setStep(3);
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  }

  // Ask phase → themes phase. Persist the free-text goal (when provided or
  // changed) FIRST, then generate the themes so the model is anchored on the
  // user's own words. An empty goal is fine — it just generates from role.
  async function handleGenerateThemes() {
    const trimmed = goals.trim();
    setSaving(true);
    try {
      if (trimmed && trimmed !== goalsUsed) {
        const next = await saveOnboardingProfile({ goals_freeform: trimmed });
        setMe(next);
        setGoalsUsed(trimmed);
      }
    } catch {
      toast(t("toast_save_failed"), "error");
      setSaving(false);
      return;
    }
    setSaving(false);
    setPhase3("themes");
    // Route by input richness: a typed goal → Sonnet (its anchoring on the
    // user's words is exactly the win); skipped → Haiku (fast, and role-only
    // themes don't need Sonnet's reasoning).
    fetchSuggestions(trimmed ? "sonnet" : "haiku");
  }

  // Themes phase → back to ask phase, so the user can edit their words and
  // regenerate. The textarea is prefilled from `goals`.
  function handleBackToAsk() {
    setPhase3("ask");
  }

  async function handleComplete() {
    setSaving(true);
    try {
      const casesArray = Array.from(selectedUseCases);
      await completeOnboarding({
        selected_use_cases: casesArray.length ? casesArray.join(",") : undefined,
        use_case: casesArray[0] || undefined,
        goals_freeform: goals.trim() || undefined,
      });
      setCachedOnboarded(true);
      setDone(true);
    } catch {
      toast(t("toast_save_failed"), "error");
    } finally {
      setSaving(false);
    }
  }

  function handleEnterWorkspace() {
    // Hand off to the demo-project tour: the dashboard waits for the
    // background-seeded demo study, then opens it with the tour armed.
    navigate("/dashboard?tour=1", { replace: true });
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
      // Ignore Enter on focused buttons (chips, CTAs) — the click already
      // handles it, and advancing here too would double-fire the action.
      // Ignore textareas too: Enter there is a newline, not "continue".
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "BUTTON" || tag === "TEXTAREA") return;
      if (e.key === "Enter" && !saving) {
        if (done) handleEnterWorkspace();
        else if (step === 1 && step1Valid) handleStep1Next();
        else if (step === 2 && step2Valid) handleStep2Next();
        else if (step === 3 && phase3 === "ask") handleGenerateThemes();
        else if (step === 3 && phase3 === "themes" && !suggestionsLoading) handleComplete();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, phase3, step1Valid, step2Valid, saving, suggestionsLoading, done, companyName, roleFamily, roleKey, roleOther, teamSize, goals, goalsUsed]);

  if (loading || !me) {
    return (
      <div className="welcome-setup">
        <header className="welcome-setup__bar">
          <span className="welcome-setup__brand">
            <span className="welcome-setup__mark" aria-hidden="true">
              <span />
            </span>
            QualiPulse
          </span>
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
        <span className="welcome-setup__brand">
          <span className="welcome-setup__mark" aria-hidden="true">
            <span />
          </span>
          QualiPulse
        </span>
        {!done && (
          <button
            type="button"
            className="welcome-setup__skip"
            onClick={handleSkip}
            disabled={saving}
          >
            {t("header_skip")}
          </button>
        )}
      </header>

      <div className="welcome-setup__main">
        {!done && (
          <div className="welcome-setup__progress" aria-label={t("progress_aria")}>
            <div className="welcome-setup__progress-row">
              <span className="welcome-setup__progress-count">
                {t("progress_step", { step })}
              </span>
              <span className="welcome-setup__progress-name">{t(`step_${step}_label`)}</span>
            </div>
            <div
              className="welcome-setup__progress-track"
              role="progressbar"
              aria-valuenow={step}
              aria-valuemin={1}
              aria-valuemax={3}
              aria-label={t("progress_aria")}
            >
              <i style={{ width: `${(step / 3) * 100}%` }} />
            </div>
          </div>
        )}

        {/* ── Finale: workspace handoff ── */}
        {done && (
          <section className="welcome-setup__card welcome-handoff">
            <div className="welcome-setup__eyebrow">{t("handoff_kicker")}</div>
            <h1 className="welcome-setup__title">{t("handoff_title")}</h1>
            <p className="welcome-setup__sub">{t("handoff_sub")}</p>

            <div className="welcome-handoff__preview" aria-hidden="true">
              <div className="welcome-handoff__rail">
                <span />
              </div>
              <div className="welcome-handoff__rows">
                <span className="welcome-handoff__row">
                  <i style={{ width: "58%" }} />
                </span>
                <span className="welcome-handoff__row">
                  <i style={{ width: "42%" }} />
                </span>
                <div className="welcome-handoff__memo">
                  <span>{t("handoff_memo_kicker")}</span>
                  {t("handoff_memo_title")}
                </div>
              </div>
            </div>

            <p className="welcome-handoff__note">{t("handoff_note")}</p>

            <div className="welcome-setup__actions">
              <button type="button" className="btn btn-primary" onClick={handleEnterWorkspace}>
                {t("handoff_cta")}
              </button>
            </div>
          </section>
        )}

        {/* ── Step 1: Company name + language ── */}
        {!done && step === 1 && (
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
        {!done && step === 2 && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_2_title")}</h1>
            <p className="welcome-setup__sub">{t("step_2_sub")}</p>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("field_role_family")}</span>
              <div className="welcome-setup__chips" role="radiogroup">
                {ROLE_FAMILIES.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    role="radio"
                    aria-checked={roleFamily === f.key}
                    className={`welcome-setup__chip ${roleFamily === f.key ? "welcome-setup__chip--active" : ""}`}
                    onClick={() => { setRoleFamily(f.key); setRoleKey(""); }}
                    disabled={saving}
                  >
                    {t(`roleFamilies.${f.key}`)}
                  </button>
                ))}
              </div>
            </div>

            {roleFamily && roleFamily !== "other" && (
              <div className="welcome-setup__field">
                <span className="welcome-setup__field-label">{t("field_role")}</span>
                <div className="welcome-setup__chips" role="radiogroup">
                  {[...(ROLE_FAMILIES.find((f) => f.key === roleFamily)?.roles ?? []), ROLE_OTHER].map((rk) => (
                    <button
                      key={rk}
                      type="button"
                      role="radio"
                      aria-checked={roleKey === rk}
                      className={`welcome-setup__chip ${roleKey === rk ? "welcome-setup__chip--active" : ""}`}
                      onClick={() => setRoleKey(rk)}
                      disabled={saving}
                    >
                      {rk === ROLE_OTHER ? t("role_other_chip") : t(`roles.${rk}`)}
                    </button>
                  ))}
                </div>
                {roleKey === ROLE_OTHER && (
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
            )}

            {roleFamily === "other" && (
              <div className="welcome-setup__field">
                <span className="welcome-setup__field-label">{t("field_role")}</span>
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
              </div>
            )}

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

        {/* ── Step 3a: Ask — the user's own words, fed to the model first ── */}
        {!done && step === 3 && phase3 === "ask" && (
          <section className="welcome-setup__card">
            <h1 className="welcome-setup__title">{t("step_3_title")}</h1>
            <p className="welcome-setup__sub">{t("step_3_ask_sub")}</p>

            <div className="welcome-setup__field">
              <span className="welcome-setup__field-label">{t("step_3_ask_label")}</span>
              <textarea
                className="welcome-setup__other-input"
                style={{ resize: "vertical" }}
                rows={4}
                value={goals}
                onChange={(e) => setGoals(e.target.value)}
                placeholder={t("step_3_goals_placeholder")}
                autoFocus
                disabled={saving}
              />
            </div>

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
                onClick={handleGenerateThemes}
                disabled={saving}
              >
                {saving
                  ? t("saving")
                  : goals.trim()
                    ? t("step_3_ask_cta")
                    : t("step_3_ask_cta_empty")}
              </button>
            </div>
          </section>
        )}

        {/* ── Step 3b: Themes — confirm/expand the AI's proposal ── */}
        {!done && step === 3 && phase3 === "themes" && (
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
                      {(Array.isArray(suggestions.use_cases) ? suggestions.use_cases : []).map((uc) => (
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
                    <span className="welcome-setup__summary-kicker">
                      {t("step_3_summary_label")}
                    </span>
                    <p>{suggestions.profile_summary}</p>
                  </div>
                )}

                {/* Read-only recap of the words that drove these themes, with
                    a one-click way back to the ask phase to edit + regenerate. */}
                {goalsUsed.trim() && (
                  <div className="welcome-setup__field">
                    <span className="welcome-setup__field-label">{t("step_3_your_goal_label")}</span>
                    <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", margin: "0 0 6px", fontStyle: "italic" }}>
                      “{goalsUsed}”
                    </p>
                  </div>
                )}
              </>
            )}

            <div className="welcome-setup__actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleBackToAsk}
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
