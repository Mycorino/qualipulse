import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { createProject, updateProject, getProject, createLink } from "../api/projects";
import type { QuestionCreate, ScreeningQuestionCreate } from "../api/projects";
import {
  parseBrief,
  suggestObjective,
  suggestScope,
  suggestQuestions,
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
  const isEditMode = !!editId;
  const { t } = useTranslation("project");

  // In edit mode, skip draft restore and load from API instead
  const draft = isEditMode ? null : loadDraft();

  const [step, setStep] = useState(draft?.step ?? 1);

  // Step 1
  const [name, setName] = useState(draft?.name ?? "");
  const [context, setContext] = useState(draft?.context ?? "");
  const [originalContext, setOriginalContext] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [briefSummary, setBriefSummary] = useState(draft?.briefSummary ?? "");

  // Step 2
  const [objective, setObjective] = useState(draft?.objective ?? "");
  const [learningGoals, setLearningGoals] = useState(draft?.learningGoals ?? ["", "", ""]);
  const [studyType, setStudyType] = useState(draft?.studyType ?? "exploratory");
  const [rationale, setRationale] = useState(draft?.rationale ?? "");

  // Step 3
  const [audience, setAudience] = useState(draft?.audience ?? "");
  const [durationMinutes, setDurationMinutes] = useState(draft?.durationMinutes ?? 20);
  const [language, setLanguage] = useState(draft?.language ?? "en");
  const [screeningQuestions, setScreeningQuestions] = useState<ScreeningQuestionCreate[]>(draft?.screeningQuestions ?? []);
  const [expandedSQ, setExpandedSQ] = useState<number | null>(null);

  // Step 4
  const [questions, setQuestions] = useState<QuestionCreate[]>(draft?.questions ?? []);
  const [expandedQ, setExpandedQ] = useState<number | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError] = useState("");
  const [hasDraft, setHasDraft] = useState(!!draft);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const { toast } = useToast();

  // Template picker: shown first on fresh create (no draft, not edit)
  const [showTemplatePicker, setShowTemplatePicker] = useState(!isEditMode && !draft);
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
      audience, durationMinutes, language, questions, screeningQuestions,
    }));
  }, [isEditMode, step, name, context, briefSummary, objective, learningGoals, studyType, rationale, audience, durationMinutes, language, questions, screeningQuestions]);

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
      // Ensure at least 3 learning goal slots so the UI stays consistent
      const goals = [...tpl.learning_goals];
      while (goals.length < 3) goals.push("");
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

  // Load existing project in edit mode
  useEffect(() => {
    if (!editId) return;
    getProject(editId).then((p) => {
      setName(p.name);
      setLanguage(p.language);
      setDurationMinutes(p.interview_duration_minutes);
      setObjective(p.research_objective ?? "");
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

  // ── Render ───────────────────────────────────────────────────────────────

  // ── Template picker view ───────────────────────────────────────────────
  if (showTemplatePicker) {
    return (
      <div className="wizard-layout">
        <header className="wizard-header">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate("/dashboard")}>
            {t("wizard.backButton")}
          </button>
          <h2 className="wizard-title">{t("wizard.title")}</h2>
          <div style={{ width: 80 }} />
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
        <button className="btn btn-ghost btn-sm" onClick={() => navigate("/dashboard")}>
          {t("wizard.backButton")}
        </button>
        <h2 className="wizard-title">{isEditMode ? t("wizard.titleEdit") : t("wizard.title")}</h2>
        {!isEditMode && <span className="wizard-autosave wizard-autosave--hide-mobile">{t("wizard.draftAutoSaved")}</span>}
        {isEditMode && <div style={{ width: 80 }} />}
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
        <div className="draft-banner" style={{ background: "var(--brand-50, #eff6ff)", color: "var(--brand-700, #1d4ed8)", borderColor: "var(--brand-200, #bfdbfe)" }}>
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
              <textarea
                key={i}
                className="field-input"
                rows={2}
                style={{ marginBottom: 8, resize: "vertical", whiteSpace: "normal" }}
                value={goal}
                onChange={(e) =>
                  setLearningGoals((prev: string[]) =>
                    prev.map((g: string, j: number) => (j === i ? e.target.value : g))
                  )
                }
                placeholder={t("wizard.learningGoalPlaceholder", { number: i + 1 })}
              />
            ))}

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
                  const sectionLocalIndex = questions.slice(0, i).filter((prev) => prev.section_index === q.section_index).length + 1;
                  return (
                  <div key={i} className="guide-editor-question">
                    <div
                      className="guide-editor-header"
                      onClick={() => setExpandedQ(expandedQ === i ? null : i)}
                    >
                      <div className="guide-editor-meta">
                        <span className="guide-editor-section">{q.section_title}</span>
                        <span className="guide-editor-num">Q{sectionLocalIndex}</span>
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
