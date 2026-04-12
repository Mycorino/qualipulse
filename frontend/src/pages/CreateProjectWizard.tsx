import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";

import { useAuth } from "../hooks/useAuth";
import { getMe } from "../api/auth";
import { createProject, updateProject, getProject, createLink } from "../api/projects";
import type { QuestionCreate, ScreeningQuestionCreate } from "../api/projects";
import {
  parseBrief,
  suggestObjective,
  suggestScope,
  suggestQuestions,
  refineQuestion,
} from "../api/research";
import { listTemplates, getTemplate } from "../api/templates";
import type { TemplateSummary } from "../api/templates";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "fr", label: "French" },
  { code: "es", label: "Spanish" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt", label: "Portuguese" },
  { code: "nl", label: "Dutch" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "zh", label: "Chinese" },
];

const DURATIONS = [15, 20, 30, 45];

const DRAFT_KEY = "wizard_draft";

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function CreateProjectWizard() {
  const navigate = useNavigate();
  const { id: editId } = useParams<{ id?: string }>();
  const [searchParams] = useSearchParams();
  const isEditMode = !!editId;
  const { t, i18n } = useTranslation(["project", "common"]);
  const { logout } = useAuth();

  // In edit mode, skip draft restore and load from API instead
  const draft = isEditMode ? null : loadDraft();

  // Seed the project language from the user's UI locale on a fresh wizard
  // so the AI research wizard generates the brief, objective, scope, and
  // interview guide in their account language. We support en/fr in the UI
  // and fall back to "en" for any other locale (the dropdown still lets
  // them pick a different language for the participants).
  const accountLang = (i18n.language || "en").toLowerCase().startsWith("fr")
    ? "fr"
    : "en";

  const [step, setStep] = useState(draft?.step ?? 1);

  // Step 1
  const [name, setName] = useState(draft?.name ?? "");
  const [context, setContext] = useState<string>(draft?.context ?? "");
  const [originalContext, setOriginalContext] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [briefSummary, setBriefSummary] = useState(draft?.briefSummary ?? "");

  // Step 2
  const [objective, setObjective] = useState(draft?.objective ?? "");
  const [learningGoals, setLearningGoals] = useState(draft?.learningGoals ?? ["", ""]);
  const [studyType, setStudyType] = useState(draft?.studyType ?? "exploratory");
  const [rationale, setRationale] = useState(draft?.rationale ?? "");
  // Study-specific grounding fields — see backend services/business_context.py.
  // These override whatever company-level context is attached, so the analysis
  // prompt always knows exactly what this study is trying to decide and who
  // it's about (not just the general "what does the company do").
  const [decisionToInform, setDecisionToInform] = useState(draft?.decisionToInform ?? "");
  const [targetCustomerDescription, setTargetCustomerDescription] = useState(draft?.targetCustomerDescription ?? "");

  // Step 3
  const [audience, setAudience] = useState(draft?.audience ?? "");
  const [durationMinutes, setDurationMinutes] = useState(draft?.durationMinutes ?? 20);
  const [language, setLanguage] = useState(draft?.language ?? accountLang);
  const [screeningQuestions, setScreeningQuestions] = useState<ScreeningQuestionCreate[]>(draft?.screeningQuestions ?? []);
  const [expandedSQ, setExpandedSQ] = useState<number | null>(null);

  // Step 4
  const [questions, setQuestions] = useState<QuestionCreate[]>(draft?.questions ?? []);
  const [expandedQ, setExpandedQ] = useState<number | null>(null);
  // Per-question refinement state. These are keyed by question index so
  // the researcher can have an undo available on Q2 without it blocking
  // refinement on Q5, etc. Deliberately not persisted to the autosave
  // draft — refinement history is session-local by design.
  const [refiningQ, setRefiningQ] = useState<number | null>(null);
  const [refineSnapshot, setRefineSnapshot] = useState<Record<number, QuestionCreate>>({});
  const [refineRationale, setRefineRationale] = useState<Record<number, string>>({});
  // Optional user steering ("make it shorter", "less leading") typed into
  // a small inline field before calling refine. Also keyed per question.
  const [refineInstruction, setRefineInstruction] = useState<Record<number, string>>({});

  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError] = useState("");
  const [hasDraft, setHasDraft] = useState(!!draft);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const { toast } = useToast();

  // Template picker: shown first on fresh create (no draft, not edit).
  // If the URL carries `?template=<id>` (from the Dashboard "Studies that
  // fit your company" cards) we skip the picker entirely — the user already
  // chose their template when they clicked the recommendation, so showing
  // a picker again would feel like the click didn't do anything.
  const initialTemplateParam = searchParams.get("template");
  const [showTemplatePicker, setShowTemplatePicker] = useState(
    !isEditMode && !draft && !initialTemplateParam
  );
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [applyingTemplateId, setApplyingTemplateId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const STEPS = [
    t("wizard.step1"),
    t("wizard.step2"),
    t("wizard.step3"),
    t("wizard.step4"),
  ];

  // Auto-save draft (only in create mode)
  useEffect(() => {
    if (isEditMode) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      step, name, context, briefSummary,
      objective, learningGoals, studyType, rationale,
      decisionToInform, targetCustomerDescription,
      audience, durationMinutes, language, questions, screeningQuestions,
    }));
  }, [isEditMode, step, name, context, briefSummary, objective, learningGoals, studyType, rationale, decisionToInform, targetCustomerDescription, audience, durationMinutes, language, questions, screeningQuestions]);

  // Load template list on mount (only when picker is visible)
  useEffect(() => {
    if (!showTemplatePicker) return;
    if (templates.length > 0) return;
    setTemplatesLoading(true);
    listTemplates()
      .then((list) => setTemplates(list))
      .catch(() => {
        // Fall through silently — user can still start from scratch
        setError(t("wizard.templateLoadError"));
      })
      .finally(() => setTemplatesLoading(false));
  }, [showTemplatePicker]);

  async function handleUseTemplate(templateId: string) {
    setApplyingTemplateId(templateId);
    setError("");
    try {
      const tpl = await getTemplate(templateId);
      // Pre-fill wizard state from template
      setName(tpl.name);
      setObjective(tpl.research_objective);
      // Ensure at least 1 learning goal slot so the UI stays usable
      const goals = [...tpl.learning_goals];
      if (goals.length === 0) goals.push("");
      setLearningGoals(goals);
      setAudience(tpl.target_audience);
      setDurationMinutes(tpl.duration_minutes);
      setQuestions(
        tpl.questions.map((q) => ({
          section_index: q.section_index,
          section_title: q.section_title,
          question_index: q.question_index,
          main_question: q.main_question,
          interview_notes: q.interview_notes,
          desired_learning: q.desired_learning,
        }))
      );
      setScreeningQuestions(
        tpl.screening_questions.map((sq) => ({
          question: sq.question,
          options: sq.options,
          disqualifying_options: sq.disqualifying_options,
        }))
      );
      // Hide picker and jump to Step 1 so user can tweak the name + context first
      setShowTemplatePicker(false);
      setStep(1);
      toast(t("wizard.templateApplied"), "success");
    } catch {
      setError(t("wizard.templateLoadError"));
    } finally {
      setApplyingTemplateId(null);
    }
  }

  // Handle `?template=<id>` — the Dashboard "Studies that fit your company"
  // cards deep-link here so the researcher doesn't have to pick the template
  // twice. We auto-apply the template AND pre-fill the Step 1 brief with
  // whatever grounding we already have on the company (their monthly
  // priority, business summary, industry) so the AI parse-brief step has
  // something meaningful to work with instead of a blank canvas. That way
  // the first click on a recommendation feels like "the assistant already
  // knows who I am" rather than "empty form again".
  //
  // Skipped in edit mode and when a draft exists — those take precedence
  // so we don't silently blow away work the user had in progress.
  useEffect(() => {
    if (isEditMode) return;
    if (draft) return;
    const templateId = searchParams.get("template");
    if (!templateId) return;

    // Fire-and-forget company fetch to pre-seed the brief context.
    // We don't await it before applying the template because the template
    // load is the user-visible action — the context pre-fill is a bonus.
    getMe()
      .then((company) => {
        const parts: string[] = [];
        if (company.current_priority) {
          parts.push(
            t("wizard.contextPrefillPriority", {
              defaultValue: "Current priority: {{value}}",
              value: company.current_priority,
            })
          );
        }
        if (company.business_summary) {
          parts.push(company.business_summary);
        }
        if (company.industry) {
          parts.push(
            t("wizard.contextPrefillIndustry", {
              defaultValue: "Industry: {{value}}",
              value: company.industry,
            })
          );
        }
        if (parts.length > 0) {
          // Only pre-fill if the user hasn't typed anything yet — we don't
          // want to clobber a half-written brief on a re-render.
          setContext((prev) => (prev.trim() ? prev : parts.join("\n\n")));
        }
      })
      .catch(() => {
        // Silent — missing grounding is fine, the template alone is useful.
      });

    handleUseTemplate(templateId);
    // We intentionally only want this to run once on mount — the template
    // param is read from the URL at load time, not reactively.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pre-fill the Step 1 context with company profile data ("we remembered you")
  // for the start-from-scratch path. Skipped when a template deep-link is present
  // (that path has its own pre-fill above), when editing, or when a draft exists.
  useEffect(() => {
    if (isEditMode) return;
    if (draft) return;
    if (searchParams.get("template")) return; // handled by template useEffect above
    getMe()
      .then((company) => {
        const parts: string[] = [];
        if (company.current_priority) {
          parts.push(
            t("wizard.contextPrefillPriority", {
              defaultValue: "Current priority: {{value}}",
              value: company.current_priority,
            })
          );
        }
        if (company.business_summary) {
          parts.push(company.business_summary);
        }
        if (company.industry) {
          parts.push(
            t("wizard.contextPrefillIndustry", {
              defaultValue: "Industry: {{value}}",
              value: company.industry,
            })
          );
        }
        if (parts.length > 0) {
          setContext((prev) => (prev.trim() ? prev : parts.join("\n\n")));
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load existing project in edit mode
  useEffect(() => {
    if (!editId) return;
    getProject(editId).then((p) => {
      setName(p.name);
      setLanguage(p.language);
      setDurationMinutes(p.interview_duration_minutes);
      setObjective(p.research_objective ?? "");
      setDecisionToInform(p.decision_to_inform ?? "");
      setTargetCustomerDescription(p.target_customer_description ?? "");
      setQuestions(p.questions.map((q) => ({
        section_index: q.section_index,
        section_title: q.section_title,
        question_index: q.question_index,
        main_question: q.main_question,
        interview_notes: q.interview_notes ?? "",
        desired_learning: q.desired_learning ?? "",
      })));
      setScreeningQuestions(p.screening_questions.map((sq) => ({
        question: sq.question,
        options: sq.options,
        disqualifying_options: sq.disqualifying_options,
      })));
      setStep(4);
    }).catch(() => navigate("/dashboard"));
  }, [editId]);

  // ── AI Actions ──────────────────────────────────────────────────────────

  async function handleParseBrief() {
    if (!context.trim() && files.length === 0) return;
    setLoading(true);
    setLoadingMsg(t("wizard.loadingReadingBrief"));
    setError("");
    if (!originalContext) setOriginalContext(context);
    try {
      const res = await parseBrief(context, files);
      setBriefSummary(res.summary);
    } catch {
      setError(t("wizard.errorParseBrief"));
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestObjective() {
    setLoading(true);
    setLoadingMsg(t("wizard.loadingObjective"));
    setError("");
    try {
      const res = await suggestObjective(context, briefSummary);
      setObjective(res.objective);
      setLearningGoals(res.learning_goals);
      setStudyType(res.study_type);
      setRationale(res.rationale);
    } catch {
      setError(t("wizard.errorObjective"));
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestScope() {
    setLoading(true);
    setLoadingMsg(t("wizard.loadingScope"));
    setError("");
    try {
      const res = await suggestScope(objective, learningGoals, context);
      setAudience(res.audience);
      setDurationMinutes(res.duration_minutes);
      setLanguage(res.language);
    } catch {
      setError(t("wizard.errorScope"));
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestQuestions() {
    if (questions.length > 0 && !confirmRegenerate) {
      setConfirmRegenerate(true);
      return;
    }
    setConfirmRegenerate(false);
    setLoading(true);
    setLoadingMsg(t("wizard.loadingQuestions"));
    setError("");
    try {
      const res = await suggestQuestions(
        objective,
        learningGoals,
        audience,
        durationMinutes,
        language,
        context
      );
      setQuestions(res.questions);
      setExpandedQ(null);
    } catch {
      setError(t("wizard.errorQuestions"));
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  // ── Submit ───────────────────────────────────────────────────────────────

  async function handleCreate() {
    setLoading(true);
    setLoadingMsg(t("wizard.loadingCreating"));
    setError("");
    try {
      const body = {
        name,
        language,
        interview_duration_minutes: durationMinutes,
        research_objective: objective || undefined,
        decision_to_inform: decisionToInform.trim() || undefined,
        target_customer_description: targetCustomerDescription.trim() || undefined,
        questions: questions.filter((q) => q.main_question.trim()),
        screening_questions: screeningQuestions.filter((sq) => sq.question.trim()),
      };
      const project = isEditMode
        ? await updateProject(editId!, body)
        : await createProject(body);
      if (!isEditMode) {
        localStorage.removeItem(DRAFT_KEY);
        toast(t("wizard.projectCreated"), "success");
        // Auto-generate the first interview link so the welcome modal on the
        // project page can display it immediately. Failure is non-blocking.
        try {
          await createLink(project.id);
        } catch {
          // silent — user can create one manually on the project page
        }
        navigate(`/projects/${project.id}?created=1`);
        return;
      }
      navigate(`/projects/${project.id}`);
    } catch {
      setError(t("wizard.errorCreate"));
      setLoading(false);
      setLoadingMsg("");
    }
  }

  // ── Screening question editing ──────────────────────────────────────────

  function addSQ() {
    setScreeningQuestions((prev) => [...prev, { question: "", options: ["", ""], disqualifying_options: [] }]);
    setExpandedSQ(screeningQuestions.length);
  }

  function removeSQ(i: number) {
    if (!window.confirm(t("wizard.confirmRemoveScreening"))) return;
    setScreeningQuestions((prev) => prev.filter((_, idx) => idx !== i));
    setExpandedSQ(null);
  }

  function updateSQField(i: number, value: string) {
    setScreeningQuestions((prev) => prev.map((sq, idx) => idx === i ? { ...sq, question: value } : sq));
  }

  function updateSQOption(sqIdx: number, optIdx: number, value: string) {
    setScreeningQuestions((prev) =>
      prev.map((sq, idx) => {
        if (idx !== sqIdx) return sq;
        const oldVal = sq.options[optIdx];
        return {
          ...sq,
          options: sq.options.map((o, oi) => oi === optIdx ? value : o),
          disqualifying_options: sq.disqualifying_options.map((d) => d === oldVal ? value : d),
        };
      })
    );
  }

  function addSQOption(sqIdx: number) {
    setScreeningQuestions((prev) =>
      prev.map((sq, idx) => idx === sqIdx ? { ...sq, options: [...sq.options, ""] } : sq)
    );
  }

  function removeSQOption(sqIdx: number, optIdx: number) {
    setScreeningQuestions((prev) =>
      prev.map((sq, idx) => {
        if (idx !== sqIdx) return sq;
        const removed = sq.options[optIdx];
        return {
          ...sq,
          options: sq.options.filter((_, oi) => oi !== optIdx),
          disqualifying_options: sq.disqualifying_options.filter((d) => d !== removed),
        };
      })
    );
  }

  function toggleDisqualifying(sqIdx: number, option: string) {
    setScreeningQuestions((prev) =>
      prev.map((sq, idx) => {
        if (idx !== sqIdx) return sq;
        const isDisq = sq.disqualifying_options.includes(option);
        return {
          ...sq,
          disqualifying_options: isDisq
            ? sq.disqualifying_options.filter((d) => d !== option)
            : [...sq.disqualifying_options, option],
        };
      })
    );
  }

  // ── Question editing ────────────────────────────────────────────────────

  function updateQuestion(i: number, field: keyof QuestionCreate, value: string | number) {
    setQuestions((prev) =>
      prev.map((q, idx) => (idx === i ? { ...q, [field]: value } : q))
    );
  }

  function removeQuestion(i: number) {
    if (!window.confirm(t("wizard.confirmRemoveQuestion"))) return;
    setQuestions((prev) => prev.filter((_, idx) => idx !== i));
  }

  function addQuestion() {
    const lastSection = questions[questions.length - 1];
    setQuestions((prev) => [
      ...prev,
      {
        section_index: lastSection?.section_index ?? 0,
        section_title: lastSection?.section_title ?? t("wizard.sectionGeneral"),
        question_index: prev.length,
        main_question: "",
        interview_notes: "",
        desired_learning: "",
      },
    ]);
  }

  // ── Per-question AI refinement ─────────────────────────────────────────
  //
  // Refines ONE question without touching its siblings. We snapshot the
  // current question before the call so the researcher can undo if they
  // don't like the refinement. The snapshot lives in component state, not
  // the autosave draft — refinement history is session-local by design,
  // because resurrecting an undo stack across tabs would feel uncanny.
  async function handleRefineQuestion(i: number) {
    const current = questions[i];
    if (!current || !current.main_question.trim()) return;

    // Snapshot only if we don't already have one — a second refine without
    // undoing the first should still let the user get back to the original
    // (not the intermediate refined version).
    if (!refineSnapshot[i]) {
      setRefineSnapshot((prev) => ({ ...prev, [i]: { ...current } }));
    }

    setRefiningQ(i);
    setError("");
    try {
      const res = await refineQuestion({
        question: current,
        questionIndex: i,
        objective,
        learningGoals,
        audience,
        allQuestions: questions,
        language,
        instruction: refineInstruction[i] || undefined,
      });
      // Apply the refined question — explicitly only touching index `i`.
      setQuestions((prev) =>
        prev.map((q, idx) =>
          idx === i
            ? {
                ...q,
                section_title: res.refined.section_title || q.section_title,
                main_question: res.refined.main_question || q.main_question,
                interview_notes: res.refined.interview_notes,
                desired_learning: res.refined.desired_learning,
              }
            : q
        )
      );
      setRefineRationale((prev) => ({ ...prev, [i]: res.rationale }));
      // Clear the steering input so the next refine starts from a blank
      // field (the rationale above stays visible until the user acts).
      setRefineInstruction((prev) => ({ ...prev, [i]: "" }));
    } catch {
      setError(t("wizard.errorRefineQuestion", { defaultValue: "Couldn't refine that question. Please try again." }));
    } finally {
      setRefiningQ(null);
    }
  }

  function handleUndoRefine(i: number) {
    const snapshot = refineSnapshot[i];
    if (!snapshot) return;
    setQuestions((prev) => prev.map((q, idx) => (idx === i ? { ...snapshot } : q)));
    // Clear the undo affordance + rationale so the card returns to its
    // pre-refinement state visually too.
    setRefineSnapshot((prev) => {
      const next = { ...prev };
      delete next[i];
      return next;
    });
    setRefineRationale((prev) => {
      const next = { ...prev };
      delete next[i];
      return next;
    });
  }

  // ── Render ───────────────────────────────────────────────────────────────

  // ── Template picker view ───────────────────────────────────────────────
  if (showTemplatePicker) {
    return (
      <div className="wizard-layout">
        <header className="wizard-header">
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span
              className="logo"
              onClick={() => navigate("/dashboard")}
              style={{ cursor: "pointer" }}
            >
              QualiPulse
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => navigate("/dashboard")}
            >
              {t("wizard.backButton")}
            </button>
          </div>
          <h2 className="wizard-title" style={{ margin: 0 }}>
            {t("wizard.title")}
          </h2>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >

            <button
              className="btn btn-ghost btn-sm"
              onClick={() => navigate("/account")}
            >
              {t("common:account")}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={logout}>
              {t("common:signOut")}
            </button>
          </div>
        </header>

        <main className="wizard-main">
          <div className="wizard-card template-picker">
            <div className="wizard-card-header" style={{ textAlign: "center" }}>
              <h2>{t("wizard.templatePickerTitle")}</h2>
              <p className="muted-text">{t("wizard.templatePickerSubtitle")}</p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {templatesLoading ? (
              <div style={{ textAlign: "center", padding: "48px 16px" }}>
                <span className="spinner-sm" />
              </div>
            ) : (
              <div className="template-grid">
                {templates.map((tpl) => (
                  <button
                    key={tpl.id}
                    className="template-card"
                    onClick={() => handleUseTemplate(tpl.id)}
                    disabled={applyingTemplateId !== null}
                    type="button"
                  >
                    <div className="template-card-icon" aria-hidden="true">{tpl.icon}</div>
                    <div className="template-card-name">{tpl.name}</div>
                    <div className="template-card-desc">{tpl.description}</div>
                    <div className="template-card-meta">
                      <span className="template-card-chip">
                        {t("wizard.templateQuestionCount", { count: tpl.question_count })}
                      </span>
                      <span className="template-card-chip">
                        {t("wizard.templateDuration", { count: tpl.duration_minutes })}
                      </span>
                      {tpl.has_screening && (
                        <span className="template-card-chip">{t("wizard.templateHasScreening")}</span>
                      )}
                    </div>
                    <div className="template-card-bestfor">
                      <span className="template-card-bestfor-label">{t("wizard.templateBestFor")}</span>{" "}
                      {tpl.best_for}
                    </div>
                    {applyingTemplateId === tpl.id && (
                      <div className="template-card-loading">
                        <span className="spinner-sm" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}

            <div className="template-picker-divider">
              <span>{t("wizard.templatePickerOrDivider")}</span>
            </div>

            <div style={{ display: "flex", justifyContent: "center" }}>
              <button
                className="btn btn-ghost"
                onClick={() => setShowTemplatePicker(false)}
                disabled={applyingTemplateId !== null}
              >
                {t("wizard.templateStartFromScratch")}
              </button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="wizard-layout">
      <header className="wizard-header">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span
            className="logo"
            onClick={() => navigate("/dashboard")}
            style={{ cursor: "pointer" }}
          >
            QualiPulse
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate("/dashboard")}
          >
            {t("wizard.backButton")}
          </button>
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
          }}
        >
          <h2 className="wizard-title" style={{ margin: 0 }}>
            {isEditMode ? t("wizard.titleEdit") : t("wizard.title")}
          </h2>
          {!isEditMode && (
            <span className="wizard-autosave wizard-autosave--hide-mobile">
              {t("wizard.draftAutoSaved")}
            </span>
          )}
        </div>
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate("/account")}
          >
            {t("common:account")}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            {t("common:signOut")}
          </button>
        </div>
      </header>

      {/* Progress */}
      <div className="wizard-progress" style={{ gap: "clamp(8px, 4vw, 48px)" }}>
        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`wizard-step-dot ${step === i + 1 ? "active" : step > i + 1 ? "done" : ""}`}
          >
            <div className="wizard-dot-circle">{step > i + 1 ? "✓" : i + 1}</div>
            <span
              className={`wizard-dot-label${step !== i + 1 ? " wizard-dot-label--inactive" : ""}`}
            >
              {label}
            </span>
          </div>
        ))}
      </div>

      <main className="wizard-main">
        {hasDraft && (
        <div className="draft-banner" style={{ background: "var(--brand-50)", color: "var(--brand-700)", borderColor: "var(--brand-200)" }}>
          <span>{t("wizard.draftRestored")}</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              if (!window.confirm(t("wizard.confirmDiscardDraft"))) return;
              localStorage.removeItem(DRAFT_KEY);
              setHasDraft(false);
              setStep(1); setName(""); setContext(""); setBriefSummary("");
              setObjective(""); setLearningGoals(["", "", ""]); setStudyType("exploratory"); setRationale("");
              setAudience(""); setDurationMinutes(20); setLanguage("en"); setQuestions([]);
            }}
          >
            {t("wizard.discardDraft")}
          </button>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

        {/* ── STEP 1: BRIEF ── */}
        {step === 1 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>{t("wizard.briefTitle")}</h2>
              <p className="muted-text">{t("wizard.briefSubtitle")}</p>
            </div>

            <label className="field-label">{t("wizard.projectNameLabel")}</label>
            <input
              className="field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("wizard.projectNamePlaceholder")}
            />

            <label className="field-label">
              {t("wizard.contextLabel")}
            </label>
            <textarea
              className="field-input wizard-textarea"
              rows={5}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder={t("wizard.contextPlaceholder")}
            />

            <label className="field-label">
              {t("wizard.supportingDocs")} <span className="optional-tag">({t("wizard.optional")})</span>
            </label>
            <div className="file-upload-area" onClick={() => fileInputRef.current?.click()}>
              {files.length === 0 ? (
                <span className="muted-text">{t("wizard.uploadPrompt")}</span>
              ) : (
                <div className="file-chips">
                  {files.map((f, i) => (
                    <span key={i} className="file-chip">
                      {f.name}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiles((prev) => prev.filter((_, j) => j !== i));
                        }}
                      >×</button>
                    </span>
                  ))}
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.csv"
                multiple
                style={{ display: "none" }}
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </div>

            {(context.trim() || files.length > 0) && (
              <button
                className="btn btn-ai"
                onClick={handleParseBrief}
                disabled={loading}
              >
                {loading ? <><span className="spinner-sm" />{loadingMsg}</> : t("wizard.summariseWithAI")}
              </button>
            )}

            {briefSummary && (
              <div className="ai-output-box">
                <div className="ai-output-label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>{t("wizard.aiBriefLabel")}</span>
                  {originalContext && (
                    <button
                      className="btn btn-ghost btn-xs"
                      style={{ fontSize: 11 }}
                      onClick={() => { setContext(originalContext); setBriefSummary(""); setOriginalContext(""); }}
                    >
                      {t("wizard.revertToOriginal")}
                    </button>
                  )}
                </div>
                <p>{briefSummary}</p>
              </div>
            )}

            <div className="wizard-nav">
              <div />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                {!name.trim() && (
                  <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>{t("wizard.nameRequired")}</p>
                )}
                <button
                  className="btn btn-primary"
                  disabled={!name.trim()}
                  title={!name.trim() ? t("wizard.nameRequiredTooltip") : undefined}
                  onClick={() => { setError(""); setStep(2); }}
                >
                  {t("wizard.nextButton")}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 2: OBJECTIVE ── */}
        {step === 2 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>{t("wizard.objectiveTitle")}</h2>
              <p className="muted-text">{t("wizard.objectiveSubtitle")}</p>
            </div>

            <button
              className="btn btn-ai"
              onClick={handleSuggestObjective}
              disabled={loading}
            >
              {loading ? <><span className="spinner-sm" />{loadingMsg}</> : t("wizard.generateObjective")}
            </button>

            {rationale && (
              <div className="ai-output-box">
                <div className="ai-output-label">{t("wizard.whyThisFraming")}</div>
                <p>{rationale}</p>
                {studyType && (
                  <span className="badge" style={{ marginTop: 8, display: "inline-block" }}>
                    {studyType}
                  </span>
                )}
              </div>
            )}

            <label className="field-label">{t("wizard.primaryObjectiveLabel")}</label>
            <textarea
              className="field-input wizard-textarea"
              rows={3}
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder={t("wizard.objectivePlaceholder")}
            />

            <label className="field-label">{t("wizard.learningGoalsLabel")}</label>
            {learningGoals.map((goal: string, i: number) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "start" }}>
                <textarea
                  className="field-input"
                  rows={2}
                  style={{ flex: 1, resize: "vertical", whiteSpace: "normal" }}
                  value={goal}
                  onChange={(e) =>
                    setLearningGoals((prev: string[]) =>
                      prev.map((g: string, j: number) => (j === i ? e.target.value : g))
                    )
                  }
                  placeholder={t("wizard.learningGoalPlaceholder", { number: i + 1 })}
                />
                {learningGoals.length > 1 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ padding: "4px 8px", marginTop: 4, flexShrink: 0 }}
                    title={t("wizard.removeLearningGoal")}
                    onClick={() => setLearningGoals((prev: string[]) => prev.filter((_, j) => j !== i))}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
            {learningGoals.length < 8 && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setLearningGoals((prev: string[]) => [...prev, ""])}
              >
                {t("wizard.addLearningGoal")}
              </button>
            )}

            {/* Study-specific grounding fields — these sharpen the analysis
                prompt beyond the company-level context. Optional, but when
                filled they dramatically improve theme + recommendation quality. */}
            <label className="field-label" style={{ marginTop: 16 }}>
              {t("wizard.decisionToInformLabel")}{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 13 }}>
                {t("wizard.decisionToInformOptional")}
              </span>
            </label>
            <textarea
              className="field-input wizard-textarea"
              rows={2}
              value={decisionToInform}
              onChange={(e) => setDecisionToInform(e.target.value)}
              placeholder={t("wizard.decisionToInformPlaceholder")}
            />

            <label className="field-label" style={{ marginTop: 12 }}>
              {t("wizard.targetCustomerLabel")}{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 13 }}>
                {t("wizard.decisionToInformOptional")}
              </span>
            </label>
            <textarea
              className="field-input wizard-textarea"
              rows={2}
              value={targetCustomerDescription}
              onChange={(e) => setTargetCustomerDescription(e.target.value)}
              placeholder={t("wizard.targetCustomerPlaceholder")}
            />

            <div className="wizard-nav">
              <button className="btn btn-ghost" onClick={() => setStep(1)}>{t("wizard.backButton")}</button>
              <button
                className="btn btn-primary"
                disabled={!objective.trim()}
                onClick={() => { setError(""); setStep(3); }}
              >
                {t("wizard.nextButton")}
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 3: SCOPE ── */}
        {step === 3 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>{t("wizard.scopeTitle")}</h2>
              <p className="muted-text">{t("wizard.scopeSubtitle")}</p>
            </div>

            <button
              className="btn btn-ai"
              onClick={handleSuggestScope}
              disabled={loading}
            >
              {loading ? <><span className="spinner-sm" />{loadingMsg}</> : t("wizard.generateScope")}
            </button>

            <label className="field-label">{t("wizard.audienceLabel")}</label>
            <textarea
              className="field-input wizard-textarea"
              rows={3}
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder={t("wizard.audiencePlaceholder")}
            />

            <label className="field-label">{t("wizard.durationLabel")}</label>
            <select
              className="field-input"
              value={durationMinutes}
              onChange={(e) => setDurationMinutes(Number(e.target.value))}
            >
              {DURATIONS.map((d) => (
                <option key={d} value={d}>{t("wizard.durationMinutes", { count: d })}</option>
              ))}
            </select>

            <label className="field-label">{t("wizard.languageLabel")}</label>
            <select
              className="field-input"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>

            <div style={{ marginTop: 24 }}>
              <label className="field-label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>{t("wizard.screeningTitle")} <span className="optional-tag">({t("wizard.optional")})</span></span>
                <button className="btn btn-ghost btn-sm" onClick={addSQ}>{t("wizard.addScreening")}</button>
              </label>
              <p className="muted-text" style={{ marginBottom: 12, fontSize: 13 }}>
                {t("wizard.screeningSubtitle")}
              </p>
              {screeningQuestions.map((sq, sqIdx) => (
                <div key={sqIdx} className="guide-editor-question" style={{ marginBottom: 8 }}>
                  <div className="guide-editor-header" onClick={() => setExpandedSQ(expandedSQ === sqIdx ? null : sqIdx)}>
                    <span className="guide-editor-num">Q{sqIdx + 1}</span>
                    <span className="guide-editor-preview" style={{ flex: 1, marginLeft: 8 }}>
                      {sq.question || <em className="muted-text">{t("wizard.emptyScreeningQuestion")}</em>}
                    </span>
                    {sq.disqualifying_options.length > 0 && (
                      <span className="badge" style={{ marginRight: 8, background: "#fef2f2", color: "#dc2626", fontSize: 11 }}>
                        {t("wizard.disqualifyingCount", { count: sq.disqualifying_options.length })}
                      </span>
                    )}
                    <span className="guide-editor-chevron">{expandedSQ === sqIdx ? "▲" : "▼"}</span>
                  </div>
                  {expandedSQ === sqIdx && (
                    <div className="guide-editor-body">
                      <label className="field-label">{t("wizard.screeningQuestionLabel")}</label>
                      <input className="field-input" value={sq.question} onChange={(e) => updateSQField(sqIdx, e.target.value)} placeholder={t("wizard.screeningQuestionPlaceholder")} />
                      <label className="field-label" style={{ marginTop: 12 }}>
                        {t("wizard.optionsLabel")} <span className="optional-tag">{t("wizard.optionsHint")}</span>
                      </label>
                      {sq.options.map((opt, optIdx) => (
                        <div key={optIdx} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                          <button
                            style={{ width: 28, height: 28, flexShrink: 0, borderRadius: 6, border: "1.5px solid", borderColor: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#d1d5db", background: sq.disqualifying_options.includes(opt) ? "#fef2f2" : "#fff", color: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#9ca3af", cursor: "pointer", fontWeight: 700, fontSize: 14 }}
                            onClick={() => opt.trim() && toggleDisqualifying(sqIdx, opt)}
                          >{sq.disqualifying_options.includes(opt) ? "✕" : "✓"}</button>
                          <input className="field-input" style={{ flex: 1, marginBottom: 0 }} value={opt} onChange={(e) => updateSQOption(sqIdx, optIdx, e.target.value)} placeholder={t("wizard.optionPlaceholder", { number: optIdx + 1 })} />
                          {sq.options.length > 1 && (
                            <button style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 18, padding: "0 4px" }} onClick={() => removeSQOption(sqIdx, optIdx)}>×</button>
                          )}
                        </div>
                      ))}
                      <button className="btn btn-ghost btn-sm" onClick={() => addSQOption(sqIdx)}>{t("wizard.addOption")}</button>
                      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                        <button className="btn btn-ghost btn-sm btn-danger-text" onClick={() => removeSQ(sqIdx)}>{t("wizard.removeScreeningQuestion")}</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="wizard-nav">
              <button className="btn btn-ghost" onClick={() => setStep(2)}>{t("wizard.backButton")}</button>
              <button
                className="btn btn-primary"
                onClick={() => { setError(""); setStep(4); }}
              >
                {t("wizard.nextButton")}
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 4: QUESTIONNAIRE ── */}
        {step === 4 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>{t("wizard.questionsTitle")}</h2>
              <p className="muted-text">
                {t("wizard.questionsSubtitle")}
              </p>
            </div>

            {confirmRegenerate ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 16px", background: "var(--warning-50, #fffbeb)", border: "1px solid var(--warning-200, #fde68a)", borderRadius: 8, marginBottom: 4 }}>
                <p style={{ margin: 0, fontSize: 14, color: "var(--warning-800, #92400e)" }}>
                  {t("wizard.regenerateWarning", { count: questions.length })}
                </p>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-ai btn-sm" onClick={handleSuggestQuestions} disabled={loading}>
                    {t("wizard.yesRegenerate")}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setConfirmRegenerate(false)}>
                    {t("wizard.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <button
                className="btn btn-ai"
                onClick={handleSuggestQuestions}
                disabled={loading}
              >
                {loading
                  ? <><span className="spinner-sm" />{loadingMsg}</>
                  : questions.length > 0
                  ? t("wizard.regenerateGuide")
                  : t("wizard.generateGuide")}
              </button>
            )}

            {questions.length > 0 && (
              <div className="guide-editor">
                {questions.map((q, i) => {
                  // Global question number (Q1..Qn across the whole guide).
                  // We used to show section-local indices here — e.g. Q1, Q2,
                  // Q1, Q2 — which made a 5-question guide look like it only
                  // had 2 questions. Global numbering matches how researchers
                  // actually talk about an interview guide ("let's tweak
                  // question 4", not "question 1 of section 2").
                  const globalNum = i + 1;
                  const isRefining = refiningQ === i;
                  const hasSnapshot = !!refineSnapshot[i];
                  const lastRationale = refineRationale[i];
                  return (
                  <div key={i} className="guide-editor-question">
                    <div
                      className="guide-editor-header"
                      onClick={() => setExpandedQ(expandedQ === i ? null : i)}
                    >
                      <div className="guide-editor-meta">
                        <span className="guide-editor-section">{q.section_title}</span>
                        <span className="guide-editor-num">Q{globalNum}</span>
                      </div>
                      <span className="guide-editor-preview">
                        {q.main_question || <em className="muted-text">{t("wizard.emptyQuestion")}</em>}
                      </span>
                      <span className="guide-editor-chevron" title={t("wizard.questionLabel")}>
                        {expandedQ === i ? "▲" : "✏"}
                      </span>
                    </div>

                    {expandedQ === i && (
                      <div className="guide-editor-body">
                        <label className="field-label">{t("wizard.sectionTitleLabel")}</label>
                        <input
                          className="field-input"
                          value={q.section_title}
                          onChange={(e) => updateQuestion(i, "section_title", e.target.value)}
                        />

                        <label className="field-label">{t("wizard.questionLabel")}</label>
                        <textarea
                          className="field-input wizard-textarea"
                          rows={3}
                          value={q.main_question}
                          onChange={(e) => updateQuestion(i, "main_question", e.target.value)}
                        />

                        <label className="field-label">{t("wizard.interviewNotesLabel")}
                          <span className="optional-tag"> {t("wizard.interviewNotesHint")}</span>
                        </label>
                        <textarea
                          className="field-input"
                          rows={2}
                          value={q.interview_notes ?? ""}
                          onChange={(e) => updateQuestion(i, "interview_notes", e.target.value)}
                        />

                        <label className="field-label">{t("wizard.desiredLearningLabel")}
                          <span className="optional-tag"> {t("wizard.desiredLearningHint")}</span>
                        </label>
                        <textarea
                          className="field-input"
                          rows={2}
                          value={q.desired_learning ?? ""}
                          onChange={(e) => updateQuestion(i, "desired_learning", e.target.value)}
                        />

                        {/* ── Per-question AI refinement ───────────────
                            The whole point is scoped refinement: this
                            button refines ONLY this question. The
                            pre-refine version is snapshotted so the
                            researcher can undo in one click. */}
                        <div
                          className="refine-question-block"
                          style={{
                            marginTop: 14,
                            padding: "14px 16px",
                            borderRadius: 8,
                            border: "1px solid var(--border-default)",
                            borderLeft: "3px solid var(--primary)",
                            background: "var(--bg-surface)",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              gap: 8,
                              alignItems: "center",
                              flexWrap: "wrap",
                            }}
                          >
                            <input
                              className="field-input"
                              style={{ flex: "1 1 200px", minWidth: 0 }}
                              placeholder={t("wizard.refineInstructionPlaceholder", {
                                defaultValue: "Optional: how should we sharpen it? (e.g. more open-ended, shorter…)",
                              })}
                              value={refineInstruction[i] ?? ""}
                              onChange={(e) =>
                                setRefineInstruction((prev) => ({
                                  ...prev,
                                  [i]: e.target.value,
                                }))
                              }
                              disabled={isRefining}
                            />
                            <button
                              className="btn btn-ai btn-sm"
                              onClick={() => handleRefineQuestion(i)}
                              disabled={isRefining || !q.main_question.trim()}
                              type="button"
                            >
                              {isRefining ? (
                                <>
                                  <span className="spinner-sm" />
                                  {t("wizard.refiningQuestion", { defaultValue: "Refining…" })}
                                </>
                              ) : (
                                t("wizard.refineQuestion", { defaultValue: "✦ Refine with AI" })
                              )}
                            </button>
                            {hasSnapshot && !isRefining && (
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => handleUndoRefine(i)}
                                type="button"
                                title={t("wizard.undoRefineTitle", {
                                  defaultValue: "Restore the version before refinement",
                                })}
                              >
                                {t("wizard.undoRefine", { defaultValue: "↺ Undo refine" })}
                              </button>
                            )}
                          </div>
                          {lastRationale && (
                            <p
                              style={{
                                margin: "8px 0 0",
                                fontSize: 12,
                                color: "var(--text-tertiary)",
                                lineHeight: 1.4,
                              }}
                            >
                              <strong>{t("wizard.refineRationaleLabel", { defaultValue: "What changed:" })}</strong>{" "}
                              {lastRationale}
                            </p>
                          )}
                          <p
                            style={{
                              margin: "6px 0 0",
                              fontSize: 11,
                              color: "var(--text-tertiary)",
                              lineHeight: 1.4,
                            }}
                          >
                            {t("wizard.refineScopeHint", {
                              defaultValue: "Only this question will be rewritten. The rest of your guide stays untouched.",
                            })}
                          </p>
                        </div>

                        <button
                          className="btn btn-ghost btn-sm btn-danger-text"
                          style={{ marginTop: 8 }}
                          onClick={() => removeQuestion(i)}
                        >
                          {t("wizard.removeQuestion")}
                        </button>
                      </div>
                    )}
                  </div>
                  );
                })}

                <button className="btn btn-ghost btn-sm" onClick={addQuestion} style={{ border: "1.5px solid #d1d5db", borderRadius: 6, padding: "6px 16px" }}>
                  {t("wizard.addQuestion")}
                </button>
              </div>
            )}

            <div className="wizard-nav" style={{ marginTop: 24 }}>
              <button className="btn btn-ghost" onClick={() => setStep(3)}>{t("wizard.backButton")}</button>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                {!isEditMode && questions.length === 0 && (
                  <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>{t("wizard.generateGuideFirst")}</p>
                )}
                <button
                  className="btn btn-primary btn-lg"
                  disabled={loading || !name.trim() || (!isEditMode && questions.length === 0)}
                  onClick={handleCreate}
                >
                  {loading ? <><span className="spinner-sm" />{loadingMsg}</> : isEditMode ? t("wizard.saveChanges") : t("wizard.createProject")}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
