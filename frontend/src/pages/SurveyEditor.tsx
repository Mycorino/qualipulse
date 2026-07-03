import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  LintFlag,
  QuestionType,
  Survey,
  SurveyQuestion,
  createQuestion,
  defaultConfigForType,
  deprecateQuestion,
  getSurvey,
  lintQuestion,
  listLinks,
  createLink,
  listQuestions,
  patchQuestion,
  patchSurvey,
  SurveyLink,
} from "../api/surveys";
import { QuestionTypeCard } from "../components/QuestionTypeCard";
import { useToast } from "../components/Toast";
import { InstrumentShell } from "../components/InstrumentShell";
import { ResearchCopilotPanel } from "../components/ResearchCopilotPanel";
import {
  SURVEY_SECTIONS,
  surveySectionPath,
  surveyStatusPill,
} from "../components/surveyShellNav";
import { getStudy } from "../api/studies";
import { getConversation, runCopilot, saveConversation } from "../api/copilot";
import type { ProposedSurveyQuestion } from "../api/copilot";
import { resolveSurveyNextAction } from "../copilot/nextAction";

/**
 * SurveyEditor — wires the existing QuestionTypeCard + the inline question
 * editor surface to the /surveys API shipped in Sprint 6.
 *
 * Layout: 3-column.
 *   - Left rail: question list with drag-reorder + add-new button.
 *   - Centre: active question editor (prompt + type-specific config).
 *   - Right rail: type picker (when adding) or survey settings (otherwise).
 *
 * Autosave fires on prompt/config changes with a 600ms debounce. Question
 * order changes commit immediately because reorder is rare and a debounce
 * would risk losing a fast click.
 */

export default function SurveyEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation("survey");

  const [survey, setSurvey] = useState<Survey | null>(null);
  const [study, setStudy] = useState<{ id: string; name: string } | null>(null);
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [showTypePicker, setShowTypePicker] = useState(false);
  const [links, setLinks] = useState<SurveyLink[]>([]);

  // Track in-flight autosave so we don't fire two for the same diff.
  const saveTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    if (!id) return;
    getSurvey(id)
      .then((s) => {
        setSurvey(s);
        getStudy(s.study_id)
          .then((st) => setStudy({ id: st.id, name: st.name }))
          .catch(() => setStudy(null));
      })
      .catch(() => toast(t("editor.surveyNotFound"), "error"));
    listQuestions(id)
      .then((qs) => {
        setQuestions(qs);
        if (qs.length > 0) setActiveId(qs[0].id);
        else setShowTypePicker(true);
      })
      .catch(() => toast(t("editor.loadQuestionsFailed"), "error"));
    listLinks(id).then(setLinks).catch(() => undefined);
  }, [id, toast]);

  const activeQuestion = useMemo(
    () => questions.find((q) => q.id === activeId) ?? null,
    [questions, activeId],
  );

  /** Adds a question of the chosen type at the end of the list. */
  const onAddQuestion = useCallback(
    async (type: QuestionType) => {
      if (!id) return;
      try {
        const created = await createQuestion(id, {
          type,
          prompt: "",
          is_required: false,
          config: defaultConfigForType(type),
        });
        setQuestions((prev) => [...prev, created]);
        setActiveId(created.id);
        setShowTypePicker(false);
      } catch {
        toast(t("editor.addQuestionFailed"), "error");
      }
    },
    [id, toast, t],
  );

  /** Debounced autosave for prompt or config edits to a single question. */
  const queueAutosave = useCallback(
    (questionId: string, payload: Parameters<typeof patchQuestion>[2]) => {
      if (!id) return;
      const existing = saveTimers.current.get(questionId);
      if (existing) clearTimeout(existing);
      const timer = setTimeout(async () => {
        try {
          const updated = await patchQuestion(id, questionId, payload);
          setQuestions((prev) =>
            prev.map((q) => (q.id === questionId ? updated : q)),
          );
        } catch {
          toast(t("editor.saveFailed"), "error");
        }
      }, 600);
      saveTimers.current.set(questionId, timer);
    },
    [id, toast, t],
  );

  const onDelete = async (questionId: string) => {
    if (!id) return;
    try {
      await deprecateQuestion(id, questionId);
      setQuestions((prev) => prev.filter((q) => q.id !== questionId));
      if (activeId === questionId) {
        const remaining = questions.filter((q) => q.id !== questionId);
        setActiveId(remaining[0]?.id ?? null);
        if (remaining.length === 0) setShowTypePicker(true);
      }
    } catch {
      toast(t("editor.removeQuestionFailed"), "error");
    }
  };

  /** Drag-reorder via plain HTML5 drag — no extra dependency. */
  const dragSourceRef = useRef<string | null>(null);
  const onDragStart = (qid: string) => () => {
    dragSourceRef.current = qid;
  };
  const onDragOver: React.DragEventHandler = (e) => e.preventDefault();
  const onDropOn = (targetId: string) => async (e: React.DragEvent) => {
    e.preventDefault();
    const sourceId = dragSourceRef.current;
    dragSourceRef.current = null;
    if (!sourceId || sourceId === targetId || !id) return;

    const source = questions.find((q) => q.id === sourceId);
    const target = questions.find((q) => q.id === targetId);
    if (!source || !target) return;

    // Compute the reordered list optimistically.
    const reordered = [...questions];
    reordered.splice(reordered.indexOf(source), 1);
    reordered.splice(reordered.indexOf(target), 0, source);
    const renumbered = reordered.map((q, i) => ({ ...q, sort_order: (i + 1) * 10 }));
    setQuestions(renumbered);

    // Persist source's new sort_order (the one that actually changed).
    try {
      await patchQuestion(id, sourceId, {
        sort_order: renumbered.find((q) => q.id === sourceId)!.sort_order,
      });
    } catch {
      toast(t("editor.reorderFailed"), "error");
    }
  };

  const onTogglePublish = async () => {
    if (!survey) return;
    const next = survey.status === "live" ? "closed" : "live";
    try {
      const updated = await patchSurvey(survey.id, { status: next });
      setSurvey(updated);
      toast(
        next === "live" ? t("editor.surveyLive") : t("editor.surveyClosed"),
        "success",
      );
    } catch {
      toast(t("editor.statusChangeFailed"), "error");
    }
  };

  const onCreatePublicLink = async () => {
    if (!survey) return;
    try {
      const link = await createLink(survey.id, { is_anonymous: false });
      setLinks((prev) => [...prev, link]);
      toast(t("editor.linkCreated"), "success");
    } catch {
      toast(t("editor.createLinkFailed"), "error");
    }
  };

  if (!survey) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{t("common.loading")}</p>
      </div>
    );
  }

  // The copilot's mission + next-best-action for the survey editor. The
  // editor is the pre-launch surface, so the resolver works off question
  // count and status; post-launch response/report data lives on the
  // survey dashboard (a later phase).
  const surveyMission = t("editor.mission");
  // Once the survey is live, the post-publish rungs need response counts
  // this surface doesn't load — a chip built from zeros would show
  // "Share the survey (0/30)" against a survey with hundreds of responses.
  // Better no chip than a wrong one.
  const surveyNextAction =
    survey.status === "live" || survey.status === "closed"
      ? undefined
      : resolveSurveyNextAction({
          questionCount: questions.length,
          status: survey.status,
          completedResponses: 0,
          hasReport: false,
          reportResponseCount: 0,
        });

  return (
    <InstrumentShell
      crumbs={[
        { label: t("editor.crumbStudies"), to: "/studies" },
        ...(study ? [{ label: study.name, to: `/studies/${study.id}` }] : []),
        { label: survey.name },
      ]}
      eyebrow={t("editor.eyebrow")}
      title={
        <input
          type="text"
          className="survey-editor__title-input"
          value={survey.name}
          onChange={(e) => setSurvey({ ...survey, name: e.target.value })}
          onBlur={() =>
            patchSurvey(survey.id, { name: survey.name }).catch(() =>
              toast(t("editor.saveFailedShort"), "error"),
            )
          }
          aria-label={t("editor.surveyNameAria")}
        />
      }
      status={surveyStatusPill(survey.status)}
      actions={
        <button type="button" className="btn btn-primary" onClick={onTogglePublish}>
          {survey.status === "live" ? t("editor.closeSurvey") : t("editor.publish")}
        </button>
      }
      sections={SURVEY_SECTIONS}
      activeSection="build"
      onSectionChange={(k) => navigate(surveySectionPath(k, survey.id))}
      subNavLabel={t("editor.sectionsNavLabel")}
    >
      <div className="survey-editor__layout">
        {/* ── Left rail: question list ───────────────────────────────── */}
        <aside className="survey-editor__rail survey-editor__rail--left">
          <div className="survey-editor__rail-head">
            <span className="shell-nav__group-label">{t("editor.questions")}</span>
            <span className="shell-nav__count tabular">{questions.length}</span>
          </div>
          <ol className="survey-editor__qlist">
            {questions.map((q, i) => (
              <li
                key={q.id}
                className={`survey-editor__qitem${activeId === q.id ? " survey-editor__qitem--active" : ""}`}
                draggable
                onDragStart={onDragStart(q.id)}
                onDragOver={onDragOver}
                onDrop={onDropOn(q.id)}
                onClick={() => {
                  setActiveId(q.id);
                  setShowTypePicker(false);
                }}
              >
                <span className="survey-editor__qitem-num tabular">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="survey-editor__qitem-body">
                  <span className="survey-editor__qitem-type">{t(`editor.typeLabels.${q.type}`)}</span>
                  <span className="survey-editor__qitem-prompt">
                    {q.prompt || <em style={{ color: "var(--text-tertiary)" }}>{t("common.untitledQuestion")}</em>}
                  </span>
                </span>
                <button
                  type="button"
                  className="survey-editor__qitem-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(q.id);
                  }}
                  aria-label={t("editor.removeQuestion")}
                  title={t("editor.remove")}
                >
                  ×
                </button>
              </li>
            ))}
          </ol>
          <button
            type="button"
            className="survey-editor__add"
            onClick={() => {
              setShowTypePicker(true);
              setActiveId(null);
            }}
          >
            {t("editor.addQuestion")}
          </button>
        </aside>

        {/* ── Centre: editor or type picker ─────────────────────────── */}
        <main className="survey-editor__centre">
          {showTypePicker || !activeQuestion ? (
            <TypePickerPane onPick={onAddQuestion} />
          ) : (
            <ActiveQuestionEditor
              key={activeQuestion.id}
              question={activeQuestion}
              surveyId={survey.id}
              onChange={(payload) => {
                setQuestions((prev) =>
                  prev.map((q) =>
                    q.id === activeQuestion.id ? { ...q, ...payload } : q,
                  ),
                );
                queueAutosave(activeQuestion.id, payload);
              }}
            />
          )}
        </main>

        {/* ── Right rail: settings ──────────────────────────────────── */}
        <aside className="survey-editor__rail survey-editor__rail--right">
          <div className="survey-editor__rail-head">
            <span className="shell-nav__group-label">{t("editor.publicLinks")}</span>
          </div>
          {links.length === 0 ? (
            <p className="quanti-showcase__section-meta" style={{ marginTop: 0 }}>
              {t("editor.noLinksYet")}
            </p>
          ) : (
            <ul className="survey-editor__link-list">
              {links.map((link) => {
                const url = `${window.location.origin}/r/${link.token}`;
                return (
                  <li key={link.id} className="survey-editor__link">
                    <code className="survey-editor__link-token">{url}</code>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      onClick={() => {
                        navigator.clipboard?.writeText(url);
                        toast(t("editor.linkCopied"), "success");
                      }}
                    >
                      {t("editor.copy")}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCreatePublicLink}
            disabled={survey.status !== "live"}
          >
            {t("editor.createPublicLink")}
          </button>
          {survey.status !== "live" && (
            <p className="quanti-showcase__section-meta" style={{ marginTop: "var(--space-2)" }}>
              {t("editor.publishFirstHint")}
            </p>
          )}
        </aside>
      </div>

      {/* In-context AI assistant. Accepted proposals are applied via the
          real survey API, then we reload the question list. */}
      <ResearchCopilotPanel
        target={{
          id: survey.id,
          runTurn: (m, h) =>
            runCopilot("surveys", survey.id, m, "Build", surveyMission, h),
          loadConversation: () => getConversation("surveys", survey.id),
          saveConversation: (t, v) => saveConversation("surveys", survey.id, t, v),
          applyAction: async (action) => {
            if (action.type === "add_question" && action.question) {
              const q = action.question as ProposedSurveyQuestion;
              await createQuestion(survey.id, {
                type: q.type,
                prompt: q.prompt,
                config: q.config,
                is_required: false,
              });
            } else if (action.type === "edit_question" && action.question_id) {
              const payload: {
                prompt?: string;
                config?: Record<string, unknown>;
              } = {};
              if (action.new_prompt) payload.prompt = action.new_prompt;
              if (action.new_config) payload.config = action.new_config;
              await patchQuestion(survey.id, action.question_id, payload);
            } else if (
              action.type === "remove_question" &&
              action.question_id
            ) {
              await deprecateQuestion(survey.id, action.question_id);
            }
          },
        }}
        onApplied={() => {
          if (!id) return;
          listQuestions(id)
            .then((qs) => {
              setQuestions(qs);
              if (qs.length > 0 && !qs.some((q) => q.id === activeId)) {
                setActiveId(qs[qs.length - 1].id);
              }
            })
            .catch(() => undefined);
        }}
        mission={surveyMission}
        nextAction={surveyNextAction}
      />
    </InstrumentShell>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Sub-components
   ──────────────────────────────────────────────────────────────────── */

function TypePickerPane({
  onPick,
}: {
  onPick: (type: QuestionType) => void;
}) {
  const { t } = useTranslation("survey");
  const types: QuestionType[] = ["likert", "mc_single", "mc_multi", "nps", "open_text", "short_text"];
  return (
    <div style={{ maxWidth: 720 }}>
      <h2 className="quanti-showcase__section-title">{t("editor.typePicker.title")}</h2>
      <p className="quanti-showcase__section-meta">{t("editor.typePicker.subtitle")}</p>
      <div className="quanti-showcase__grid-2" style={{ marginTop: "var(--space-5)" }}>
        {types.map((type) => (
          <QuestionTypeCard
            key={type}
            name={t(`editor.typeLabels.${type}`)}
            description={t(`editor.typeDescriptions.${type}`)}
            onSelect={() => onPick(type)}
          />
        ))}
      </div>
    </div>
  );
}

function ActiveQuestionEditor({
  question,
  surveyId,
  onChange,
}: {
  question: SurveyQuestion;
  surveyId: string;
  onChange: (
    payload: Partial<{ prompt: string; is_required: boolean; config: Record<string, unknown> }>,
  ) => void;
}) {
  const { t } = useTranslation("survey");
  // ── Sprint 13: inline question coach ───────────────────────────
  const [lintFlags, setLintFlags] = useState<LintFlag[]>([]);
  const [linting, setLinting] = useState(false);
  const lintTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (lintTimer.current) clearTimeout(lintTimer.current);
    if (!question.prompt || question.prompt.trim().length < 4) {
      setLintFlags([]);
      return;
    }
    setLinting(true);
    lintTimer.current = setTimeout(async () => {
      try {
        const flags = await lintQuestion(surveyId, {
          prompt: question.prompt,
          type: question.type,
          config: question.config,
          with_rewrite: true,
        });
        setLintFlags(flags);
      } catch {
        setLintFlags([]);
      } finally {
        setLinting(false);
      }
    }, 900);
    return () => {
      if (lintTimer.current) clearTimeout(lintTimer.current);
    };
  }, [surveyId, question.prompt, question.type, question.config]);

  return (
    <div className="survey-q-editor" style={{ maxWidth: 720, margin: "0 auto" }}>
      <div className="survey-q-editor__head">
        <span className="survey-q-editor__type-pill">{t(`editor.typeLabels.${question.type}`)}</span>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
            fontSize: "var(--text-xs)",
            color: "var(--text-secondary)",
          }}
        >
          <input
            type="checkbox"
            checked={question.is_required}
            onChange={(e) => onChange({ is_required: e.target.checked })}
          />
          {t("editor.required")}
        </label>
      </div>
      <label className="survey-q-editor__prompt-label">{t("editor.questionPrompt")}</label>
      <textarea
        className="survey-q-editor__prompt"
        value={question.prompt}
        onChange={(e) => onChange({ prompt: e.target.value })}
        placeholder={t("editor.promptPlaceholder")}
        rows={2}
      />

      {(lintFlags.length > 0 || linting) && (
        <QuestionCoachPanel
          flags={lintFlags}
          linting={linting}
          onApplyRewrite={(rewrite) => onChange({ prompt: rewrite })}
        />
      )}

      <div className="survey-q-editor__divider" />

      <ConfigEditor
        type={question.type}
        config={question.config}
        onChange={(c) => onChange({ config: c })}
      />
    </div>
  );
}

function QuestionCoachPanel({
  flags,
  linting,
  onApplyRewrite,
}: {
  flags: LintFlag[];
  linting: boolean;
  onApplyRewrite: (rewrite: string) => void;
}) {
  const { t } = useTranslation("survey");
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        marginTop: "var(--space-3)",
        background: "var(--bg-base)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-3) var(--space-4)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--space-2)",
          marginBottom: "var(--space-2)",
        }}
      >
        <span
          style={{
            fontSize: "var(--text-eyebrow)",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--brand-700)",
          }}
        >
          {t("editor.coach.title")}
        </span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
          {linting ? t("editor.coach.checking") : t("editor.coach.advisory")}
        </span>
      </div>
      {flags.length === 0 ? (
        <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)", margin: 0 }}>
          {t("editor.coach.scanning")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {flags.map((flag) => (
            <li
              key={flag.code}
              className={`survey-q-editor__guardrail survey-q-editor__guardrail--${flag.tone}`}
              style={{ padding: "var(--space-3)" }}
            >
              <div style={{ fontWeight: 600 }}>{flag.label}</div>
              <div style={{ marginTop: 4, fontSize: "var(--text-xs)" }}>{flag.detail}</div>
              {flag.suggested_replacement && (
                <div
                  style={{
                    marginTop: "var(--space-2)",
                    padding: "var(--space-2) var(--space-3)",
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-default)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div
                    style={{
                      fontSize: "10px",
                      fontWeight: 600,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      color: "var(--brand-700)",
                      marginBottom: 4,
                    }}
                  >
                    {t("editor.coach.suggestedReplacement")}
                  </div>
                  <p
                    style={{
                      fontFamily: "var(--font-serif)",
                      fontSize: "var(--text-sm)",
                      fontStyle: "italic",
                      margin: 0,
                      color: "var(--text-primary)",
                      lineHeight: 1.4,
                    }}
                  >
                    "{flag.suggested_replacement}"
                  </p>
                  <button
                    type="button"
                    className="btn btn-primary btn-xs"
                    style={{ marginTop: "var(--space-2)" }}
                    onClick={() => onApplyRewrite(flag.suggested_replacement!)}
                  >
                    {t("editor.coach.applyRewrite")}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConfigEditor({
  type,
  config,
  onChange,
}: {
  type: QuestionType;
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const { t } = useTranslation("survey");
  if (type === "likert") {
    const scale = (config.scale as number) ?? 5;
    return (
      <div className="survey-q-editor__config">
        <div className="survey-q-editor__config-head">
          <span className="survey-q-editor__config-title">{t("editor.config.scale")}</span>
          <span className="survey-q-editor__config-flag">{t("editor.config.balanceEnforced")}</span>
        </div>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          {[5, 7].map((s) => (
            <button
              key={s}
              type="button"
              className={`compare-chips__chip${scale === s ? " compare-chips__chip--active" : ""}`}
              onClick={() => onChange({ ...config, scale: s })}
            >
              {t("editor.config.scalePoint", { n: s })}
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (type === "mc_single" || type === "mc_multi") {
    const choices = (config.choices as { id: string; label: string }[]) ?? [];
    const updateChoice = (i: number, label: string) => {
      const next = [...choices];
      next[i] = { ...next[i], label };
      onChange({ ...config, choices: next });
    };
    const addChoice = () => {
      const newId = String.fromCharCode(97 + choices.length);
      onChange({ ...config, choices: [...choices, { id: newId, label: t("editor.config.optionDefault", { letter: newId.toUpperCase() }) }] });
    };
    const removeChoice = (i: number) => {
      if (choices.length <= 2) return;
      onChange({ ...config, choices: choices.filter((_, j) => j !== i) });
    };
    return (
      <div className="survey-q-editor__config">
        <div className="survey-q-editor__config-head">
          <span className="survey-q-editor__config-title">{t("editor.config.options")}</span>
          <span className="survey-q-editor__config-flag">{t("editor.config.orderRandomized")}</span>
        </div>
        <ul className="survey-q-editor__option-list">
          {choices.map((c, i) => (
            <li key={c.id} className="survey-q-editor__option">
              <span className="survey-q-editor__option-handle">⋮⋮</span>
              <input
                type="text"
                className="survey-q-editor__option-input"
                value={c.label}
                onChange={(e) => updateChoice(i, e.target.value)}
              />
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => removeChoice(i)}
                disabled={choices.length <= 2}
                aria-label={t("editor.config.removeOption")}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="survey-q-editor__add-option" onClick={addChoice}>
          {t("editor.config.addOption")}
        </button>
      </div>
    );
  }
  if (type === "open_text") {
    const maxChars = (config.max_chars as number) ?? 500;
    const aiCluster = (config.ai_cluster as boolean) ?? false;
    return (
      <div className="survey-q-editor__config">
        <div className="survey-q-editor__config-head">
          <span className="survey-q-editor__config-title">{t("editor.config.responseSettings")}</span>
        </div>
        <label className="survey-q-editor__inline-label">
          {t("editor.config.maxLength")}
          <input
            type="number"
            className="survey-q-editor__inline-input tabular"
            value={maxChars}
            min={50}
            max={5000}
            step={50}
            onChange={(e) => onChange({ ...config, max_chars: Number(e.target.value) })}
          />
          {t("editor.config.characters")}
        </label>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
          }}
        >
          <input
            type="checkbox"
            checked={aiCluster}
            onChange={(e) => onChange({ ...config, ai_cluster: e.target.checked })}
          />
          {t("editor.config.aiClusterLabel")}
        </label>
      </div>
    );
  }
  if (type === "short_text") {
    const maxChars = (config.max_chars as number) ?? 120;
    return (
      <div className="survey-q-editor__config">
        <div className="survey-q-editor__config-head">
          <span className="survey-q-editor__config-title">{t("editor.config.responseSettings")}</span>
        </div>
        <label className="survey-q-editor__inline-label">
          {t("editor.config.maxLength")}
          <input
            type="number"
            className="survey-q-editor__inline-input tabular"
            value={maxChars}
            min={10}
            max={500}
            step={10}
            onChange={(e) => onChange({ ...config, max_chars: Number(e.target.value) })}
          />
          {t("editor.config.characters")}
        </label>
      </div>
    );
  }
  if (type === "nps") {
    return (
      <div className="survey-q-editor__config">
        <div className="survey-q-editor__config-head">
          <span className="survey-q-editor__config-title">{t("editor.config.scale")}</span>
          <span className="survey-q-editor__config-flag">{t("editor.config.npsStandard")}</span>
        </div>
        <p className="survey-q-editor__config-note">
          {t("editor.config.npsNote")}
        </p>
      </div>
    );
  }
  return null;
}
