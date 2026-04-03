import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createProject, updateProject, getProject } from "../api/projects";
import type { QuestionCreate, ScreeningQuestionCreate } from "../api/projects";
import {
  parseBrief,
  suggestObjective,
  suggestScope,
  suggestQuestions,
} from "../api/research";

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

const STEPS = ["Brief", "Objective", "Scope", "Questionnaire"];

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

  // In edit mode, skip draft restore and load from API instead
  const draft = isEditMode ? null : loadDraft();

  const [step, setStep] = useState(draft?.step ?? 1);

  // Step 1
  const [name, setName] = useState(draft?.name ?? "");
  const [context, setContext] = useState(draft?.context ?? "");
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

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-save draft (only in create mode)
  useEffect(() => {
    if (isEditMode) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      step, name, context, briefSummary,
      objective, learningGoals, studyType, rationale,
      audience, durationMinutes, language, questions, screeningQuestions,
    }));
  }, [isEditMode, step, name, context, briefSummary, objective, learningGoals, studyType, rationale, audience, durationMinutes, language, questions, screeningQuestions]);

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
    setLoadingMsg("Reading your brief...");
    setError("");
    try {
      const res = await parseBrief(context, files);
      setBriefSummary(res.summary);
    } catch {
      setError("Failed to parse brief. Please try again.");
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestObjective() {
    setLoading(true);
    setLoadingMsg("Crafting your research objective...");
    setError("");
    try {
      const res = await suggestObjective(context, briefSummary);
      setObjective(res.objective);
      setLearningGoals(res.learning_goals);
      setStudyType(res.study_type);
      setRationale(res.rationale);
    } catch {
      setError("Failed to generate objective. Please try again.");
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestScope() {
    setLoading(true);
    setLoadingMsg("Recommending study scope...");
    setError("");
    try {
      const res = await suggestScope(objective, learningGoals, context);
      setAudience(res.audience);
      setDurationMinutes(res.duration_minutes);
      setLanguage(res.language);
    } catch {
      setError("Failed to recommend scope. Please try again.");
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  async function handleSuggestQuestions() {
    setLoading(true);
    setLoadingMsg("Writing your interview guide...");
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
      setError("Failed to generate questions. Please try again.");
    } finally {
      setLoading(false);
      setLoadingMsg("");
    }
  }

  // ── Submit ───────────────────────────────────────────────────────────────

  async function handleCreate() {
    setLoading(true);
    setLoadingMsg("Creating project...");
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
      if (!isEditMode) localStorage.removeItem(DRAFT_KEY);
      navigate(`/projects/${project.id}`);
    } catch {
      setError("Failed to create project. Please try again.");
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
    setQuestions((prev) => prev.filter((_, idx) => idx !== i));
  }

  function addQuestion() {
    const lastSection = questions[questions.length - 1];
    setQuestions((prev) => [
      ...prev,
      {
        section_index: lastSection?.section_index ?? 0,
        section_title: lastSection?.section_title ?? "General",
        question_index: prev.length,
        main_question: "",
        interview_notes: "",
        desired_learning: "",
      },
    ]);
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="wizard-layout">
      <header className="wizard-header">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate("/dashboard")}>
          ← Back
        </button>
        <h2 className="wizard-title">{isEditMode ? "Edit Project" : "New Research Project"}</h2>
        <div style={{ width: 80 }} />
      </header>

      {/* Progress */}
      <div className="wizard-progress">
        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`wizard-step-dot ${step === i + 1 ? "active" : step > i + 1 ? "done" : ""}`}
          >
            <div className="wizard-dot-circle">{step > i + 1 ? "✓" : i + 1}</div>
            <span className="wizard-dot-label">{label}</span>
          </div>
        ))}
      </div>

      <main className="wizard-main">
        {hasDraft && (
        <div className="draft-banner">
          <span>Draft restored — pick up where you left off.</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              localStorage.removeItem(DRAFT_KEY);
              setHasDraft(false);
              setStep(1); setName(""); setContext(""); setBriefSummary("");
              setObjective(""); setLearningGoals(["", "", ""]); setStudyType("exploratory"); setRationale("");
              setAudience(""); setDurationMinutes(20); setLanguage("en"); setQuestions([]);
            }}
          >
            Discard draft
          </button>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

        {/* ── STEP 1: BRIEF ── */}
        {step === 1 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>Project Brief</h2>
              <p className="muted-text">Tell us about your project so the AI can guide you through the rest.</p>
            </div>

            <label className="field-label">Project Name *</label>
            <input
              className="field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Customer Churn Research Q2"
            />

            <label className="field-label">
              Context &amp; Business Situation
            </label>
            <textarea
              className="field-input wizard-textarea"
              rows={5}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Describe your business, the problem you're trying to understand, and what decision this research will inform. The more detail you give, the sharper the AI guidance will be."
            />

            <label className="field-label">
              Supporting Documents <span className="optional-tag">(optional)</span>
            </label>
            <div className="file-upload-area" onClick={() => fileInputRef.current?.click()}>
              {files.length === 0 ? (
                <span className="muted-text">Click to upload .txt or .md files</span>
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
                {loading ? <><span className="spinner-sm" />{loadingMsg}</> : "✦ Summarise with AI"}
              </button>
            )}

            {briefSummary && (
              <div className="ai-output-box">
                <div className="ai-output-label">AI understood your brief as:</div>
                <p>{briefSummary}</p>
              </div>
            )}

            <div className="wizard-nav">
              <div />
              <button
                className="btn btn-primary"
                disabled={!name.trim()}
                onClick={() => { setError(""); setStep(2); }}
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 2: OBJECTIVE ── */}
        {step === 2 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>Research Objective</h2>
              <p className="muted-text">Define precisely what you want to learn. The AI will propose an objective based on your brief.</p>
            </div>

            <button
              className="btn btn-ai"
              onClick={handleSuggestObjective}
              disabled={loading}
            >
              {loading ? <><span className="spinner-sm" />{loadingMsg}</> : "✦ Generate Objective"}
            </button>

            {rationale && (
              <div className="ai-output-box">
                <div className="ai-output-label">Why this framing:</div>
                <p>{rationale}</p>
                {studyType && (
                  <span className="badge" style={{ marginTop: 8, display: "inline-block" }}>
                    {studyType}
                  </span>
                )}
              </div>
            )}

            <label className="field-label">Primary Objective *</label>
            <textarea
              className="field-input wizard-textarea"
              rows={3}
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder="e.g. Understand what leads first-time buyers to not return, and what would need to change for them to become regulars"
            />

            <label className="field-label">Learning Goals</label>
            {learningGoals.map((goal: string, i: number) => (
              <input
                key={i}
                className="field-input"
                style={{ marginBottom: 8 }}
                value={goal}
                onChange={(e) =>
                  setLearningGoals((prev: string[]) =>
                    prev.map((g: string, j: number) => (j === i ? e.target.value : g))
                  )
                }
                placeholder={`Learning goal ${i + 1}`}
              />
            ))}

            <div className="wizard-nav">
              <button className="btn btn-ghost" onClick={() => setStep(1)}>← Back</button>
              <button
                className="btn btn-primary"
                disabled={!objective.trim()}
                onClick={() => { setError(""); setStep(3); }}
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 3: SCOPE ── */}
        {step === 3 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>Study Scope</h2>
              <p className="muted-text">Define who you're talking to and how long the interview should be.</p>
            </div>

            <button
              className="btn btn-ai"
              onClick={handleSuggestScope}
              disabled={loading}
            >
              {loading ? <><span className="spinner-sm" />{loadingMsg}</> : "✦ AI Recommend Scope"}
            </button>

            <label className="field-label">Target Audience</label>
            <textarea
              className="field-input wizard-textarea"
              rows={3}
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="e.g. Adults 25–45 who have purchased online at least once in the past 3 months"
            />

            <label className="field-label">Interview Duration</label>
            <select
              className="field-input"
              value={durationMinutes}
              onChange={(e) => setDurationMinutes(Number(e.target.value))}
            >
              {DURATIONS.map((d) => (
                <option key={d} value={d}>{d} minutes</option>
              ))}
            </select>

            <label className="field-label">Interview Language</label>
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
                <span>Screening Questions <span className="optional-tag">(optional)</span></span>
                <button className="btn btn-ghost btn-sm" onClick={addSQ}>+ Add</button>
              </label>
              <p className="muted-text" style={{ marginBottom: 12, fontSize: 13 }}>
                Asked before the interview. Mark answers that disqualify the participant.
              </p>
              {screeningQuestions.map((sq, sqIdx) => (
                <div key={sqIdx} className="guide-editor-question" style={{ marginBottom: 8 }}>
                  <div className="guide-editor-header" onClick={() => setExpandedSQ(expandedSQ === sqIdx ? null : sqIdx)}>
                    <span className="guide-editor-num">Q{sqIdx + 1}</span>
                    <span className="guide-editor-preview" style={{ flex: 1, marginLeft: 8 }}>
                      {sq.question || <em className="muted-text">Empty screening question</em>}
                    </span>
                    {sq.disqualifying_options.length > 0 && (
                      <span className="badge" style={{ marginRight: 8, background: "#fef2f2", color: "#dc2626", fontSize: 11 }}>
                        {sq.disqualifying_options.length} disqualifying
                      </span>
                    )}
                    <span className="guide-editor-chevron">{expandedSQ === sqIdx ? "▲" : "▼"}</span>
                  </div>
                  {expandedSQ === sqIdx && (
                    <div className="guide-editor-body">
                      <label className="field-label">Question</label>
                      <input className="field-input" value={sq.question} onChange={(e) => updateSQField(sqIdx, e.target.value)} placeholder="e.g. Do you shop online at least once a month?" />
                      <label className="field-label" style={{ marginTop: 12 }}>
                        Options <span className="optional-tag">— click ✕/✓ to mark disqualifying</span>
                      </label>
                      {sq.options.map((opt, optIdx) => (
                        <div key={optIdx} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                          <button
                            style={{ width: 28, height: 28, flexShrink: 0, borderRadius: 6, border: "1.5px solid", borderColor: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#d1d5db", background: sq.disqualifying_options.includes(opt) ? "#fef2f2" : "#fff", color: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#9ca3af", cursor: "pointer", fontWeight: 700, fontSize: 14 }}
                            onClick={() => opt.trim() && toggleDisqualifying(sqIdx, opt)}
                          >{sq.disqualifying_options.includes(opt) ? "✕" : "✓"}</button>
                          <input className="field-input" style={{ flex: 1, marginBottom: 0 }} value={opt} onChange={(e) => updateSQOption(sqIdx, optIdx, e.target.value)} placeholder={`Option ${optIdx + 1}`} />
                          {sq.options.length > 1 && (
                            <button style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 18, padding: "0 4px" }} onClick={() => removeSQOption(sqIdx, optIdx)}>×</button>
                          )}
                        </div>
                      ))}
                      <button className="btn btn-ghost btn-sm" onClick={() => addSQOption(sqIdx)}>+ Add option</button>
                      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                        <button className="btn btn-ghost btn-sm btn-danger-text" onClick={() => removeSQ(sqIdx)}>Remove question</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="wizard-nav">
              <button className="btn btn-ghost" onClick={() => setStep(2)}>← Back</button>
              <button
                className="btn btn-primary"
                onClick={() => { setError(""); setStep(4); }}
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 4: QUESTIONNAIRE ── */}
        {step === 4 && (
          <div className="wizard-card">
            <div className="wizard-card-header">
              <h2>Interview Guide</h2>
              <p className="muted-text">
                AI will write a full guide based on your objective. You can edit, reorder, or add questions.
              </p>
            </div>

            <button
              className="btn btn-ai"
              onClick={handleSuggestQuestions}
              disabled={loading}
            >
              {loading
                ? <><span className="spinner-sm" />{loadingMsg}</>
                : questions.length > 0
                ? "✦ Regenerate Guide"
                : "✦ Generate Interview Guide"}
            </button>

            {questions.length > 0 && (
              <div className="guide-editor">
                {questions.map((q, i) => (
                  <div key={i} className="guide-editor-question">
                    <div
                      className="guide-editor-header"
                      onClick={() => setExpandedQ(expandedQ === i ? null : i)}
                    >
                      <div className="guide-editor-meta">
                        <span className="guide-editor-section">{q.section_title}</span>
                        <span className="guide-editor-num">Q{i + 1}</span>
                      </div>
                      <span className="guide-editor-preview">
                        {q.main_question || <em className="muted-text">Empty question</em>}
                      </span>
                      <span className="guide-editor-chevron">
                        {expandedQ === i ? "▲" : "▼"}
                      </span>
                    </div>

                    {expandedQ === i && (
                      <div className="guide-editor-body">
                        <label className="field-label">Section Title</label>
                        <input
                          className="field-input"
                          value={q.section_title}
                          onChange={(e) => updateQuestion(i, "section_title", e.target.value)}
                        />

                        <label className="field-label">Question</label>
                        <textarea
                          className="field-input wizard-textarea"
                          rows={3}
                          value={q.main_question}
                          onChange={(e) => updateQuestion(i, "main_question", e.target.value)}
                        />

                        <label className="field-label">Interview Notes
                          <span className="optional-tag"> — probing tips for the interviewer</span>
                        </label>
                        <textarea
                          className="field-input"
                          rows={2}
                          value={q.interview_notes ?? ""}
                          onChange={(e) => updateQuestion(i, "interview_notes", e.target.value)}
                        />

                        <label className="field-label">Desired Learning
                          <span className="optional-tag"> — what insight this question aims to uncover</span>
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
                          Remove question
                        </button>
                      </div>
                    )}
                  </div>
                ))}

                <button className="btn btn-ghost btn-sm" onClick={addQuestion}>
                  + Add question
                </button>
              </div>
            )}

            <div className="wizard-nav" style={{ marginTop: 24 }}>
              <button className="btn btn-ghost" onClick={() => setStep(3)}>← Back</button>
              <button
                className="btn btn-primary btn-lg"
                disabled={loading || !name.trim()}
                onClick={handleCreate}
              >
                {loading ? <><span className="spinner-sm" />{loadingMsg}</> : isEditMode ? "Save Changes" : "Create Project"}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
