/**
 * Next-best-action resolver — the deterministic core of the always-on
 * Research Copilot.
 *
 * This is intentionally NOT an LLM call. The single highest-value thing a
 * researcher should do next is a function of instrument state, so it's a
 * priority ladder: the first rule whose `test` passes wins. Instant, free,
 * runs on data the pages already hold.
 *
 * i18n: resolvers are PURE — they return i18n keys (`labelKey` / `reasonKey`,
 * namespace-qualified) plus interpolation `params`, never literal copy. The
 * consuming component translates at render time (NextActionChip,
 * ResearchCopilotPanel) so the same resolver works in any locale.
 *
 * The LLM agent only engages when the researcher opens the copilot or
 * clicks the action — see ResearchCopilotPanel.
 */

/** Discriminates which handler the consuming page wires to `run`. */
export type NbaActionType =
  // interview project
  | "draft_guide"
  | "create_link"
  | "share_link"
  | "run_analysis"
  | "refresh_analysis"
  | "review_themes"
  | "refine_analysis"
  // survey
  | "add_survey_questions"
  | "publish_survey"
  | "share_survey"
  | "generate_report"
  | "refresh_report"
  // workspace / home
  | "start_study"
  | "set_up_study"
  | "analyze_study"
  | "collect_study"
  | "generate_memo"
  | "refresh_memo"
  // shared terminal states
  | "wait"
  | "done";

export interface NextAction {
  /** Stable id — also used to dedupe a dismissed suggestion. */
  id: string;
  actionType: NbaActionType;
  /** i18n key (namespace-qualified) for the imperative chip label. */
  labelKey: string;
  /** i18n key (namespace-qualified) for the one-line "why" subtext. */
  reasonKey: string;
  /** Interpolation values for labelKey / reasonKey (counts, study name). */
  params?: Record<string, string | number>;
  /** do = actionable (accent), wait = informational (muted), done = quiet. */
  kind: "do" | "wait" | "done";
  /** Priority for cross-scope ranking (workspace NBA = max across studies). */
  weight: number;
  /** Where the action routes — e.g. the study a workspace action points at. */
  targetId?: string;
}

const NS = "dashboard:nba.";

// ── Interview project ────────────────────────────────────────────────────────

export interface ProjectNbaInput {
  guideQuestionCount: number;
  activeLinkCount: number;
  completedCount: number;
  inProgressCount: number;
  analysisStatus: "none" | "generating" | "ready" | "failed";
  /** How many participants the latest ready analysis covered. */
  analysisParticipantCount: number;
  annotationCount: number;
}

interface Rule<T> {
  test: (s: T) => boolean;
  action: (s: T) => NextAction;
}

const PROJECT_RULES: Rule<ProjectNbaInput>[] = [
  {
    test: (s) => s.guideQuestionCount === 0,
    action: () => ({
      id: "draft_guide",
      actionType: "draft_guide",
      labelKey: `${NS}draftGuide.label`,
      reasonKey: `${NS}draftGuide.reason`,
      kind: "do",
      weight: 100,
    }),
  },
  {
    test: (s) => s.guideQuestionCount > 0 && s.activeLinkCount === 0,
    action: () => ({
      id: "create_link",
      actionType: "create_link",
      labelKey: `${NS}createLink.label`,
      reasonKey: `${NS}createLink.reason`,
      kind: "do",
      weight: 90,
    }),
  },
  {
    test: (s) =>
      s.activeLinkCount > 0 &&
      s.completedCount === 0 &&
      s.inProgressCount === 0,
    action: () => ({
      id: "share_link",
      actionType: "share_link",
      labelKey: `${NS}shareLink.label`,
      reasonKey: `${NS}shareLink.reason`,
      kind: "do",
      weight: 80,
    }),
  },
  {
    // Analysis in flight — say so instead of falling through to "done".
    test: (s) => s.analysisStatus === "generating",
    action: () => ({
      id: "analysis_generating",
      actionType: "wait",
      labelKey: `${NS}analysisGenerating.label`,
      reasonKey: `${NS}analysisGenerating.reason`,
      kind: "wait",
      weight: 50,
    }),
  },
  {
    // Analysis failed — offer the retry, don't pretend all is well.
    test: (s) => s.analysisStatus === "failed",
    action: (s) => ({
      id: "retry_analysis",
      actionType: "run_analysis",
      labelKey: `${NS}retryAnalysis.label`,
      reasonKey: `${NS}retryAnalysis.reason`,
      params: { count: s.completedCount },
      kind: "do",
      weight: 75,
    }),
  },
  {
    test: (s) => s.completedCount >= 3 && s.analysisStatus === "none",
    action: (s) => ({
      id: "run_analysis",
      actionType: "run_analysis",
      labelKey: `${NS}runAnalysis.label`,
      reasonKey: `${NS}runAnalysis.reason`,
      params: { count: s.completedCount },
      kind: "do",
      weight: 85,
    }),
  },
  {
    // 1-2 interviews in: not "all set" — analysis unlocks at 3.
    test: (s) =>
      s.completedCount > 0 &&
      s.completedCount < 3 &&
      s.analysisStatus === "none",
    action: (s) => ({
      id: "collect_more",
      actionType: "wait",
      labelKey: `${NS}collectMore.label`,
      reasonKey: `${NS}collectMore.reason`,
      params: { count: s.completedCount, min: 3 },
      kind: "wait",
      weight: 45,
    }),
  },
  {
    test: (s) =>
      s.analysisStatus === "ready" &&
      s.completedCount > s.analysisParticipantCount,
    action: (s) => ({
      id: "refresh_analysis",
      actionType: "refresh_analysis",
      labelKey: `${NS}refreshAnalysis.label`,
      reasonKey: `${NS}refreshAnalysis.reason`,
      params: { count: s.completedCount - s.analysisParticipantCount },
      kind: "do",
      weight: 70,
    }),
  },
  {
    test: (s) => s.analysisStatus === "ready" && s.annotationCount === 0,
    action: () => ({
      id: "review_themes",
      actionType: "review_themes",
      labelKey: `${NS}reviewThemes.label`,
      reasonKey: `${NS}reviewThemes.reason`,
      kind: "do",
      weight: 60,
    }),
  },
  {
    test: (s) => s.analysisStatus === "ready" && s.annotationCount > 0,
    action: () => ({
      id: "refine_analysis",
      actionType: "refine_analysis",
      labelKey: `${NS}refineAnalysis.label`,
      reasonKey: `${NS}refineAnalysis.reason`,
      kind: "do",
      weight: 55,
    }),
  },
  {
    test: (s) => s.inProgressCount > 0 && s.completedCount === 0,
    action: (s) => ({
      id: "wait_responses",
      actionType: "wait",
      labelKey: `${NS}waitResponses.label`,
      reasonKey: `${NS}waitResponses.reason`,
      params: { count: s.inProgressCount },
      kind: "wait",
      weight: 40,
    }),
  },
];

const PROJECT_DONE: NextAction = {
  id: "project_done",
  actionType: "done",
  labelKey: `${NS}projectDone.label`,
  reasonKey: `${NS}projectDone.reason`,
  kind: "done",
  weight: 0,
};

export function resolveProjectNextAction(input: ProjectNbaInput): NextAction {
  for (const rule of PROJECT_RULES) {
    if (rule.test(input)) return rule.action(input);
  }
  return PROJECT_DONE;
}

// ── Survey ───────────────────────────────────────────────────────────────────

export interface SurveyNbaInput {
  questionCount: number;
  status: string; // "draft" | "live" | "closed"
  completedResponses: number;
  hasReport: boolean;
  /** How many responses the latest report covered. */
  reportResponseCount: number;
}

/** Below this, a survey's findings aren't yet worth synthesising. */
const SURVEY_MIN_RESPONSES = 30;

const SURVEY_RULES: Rule<SurveyNbaInput>[] = [
  {
    test: (s) => s.questionCount === 0,
    action: () => ({
      id: "add_survey_questions",
      actionType: "add_survey_questions",
      labelKey: `${NS}addSurveyQuestions.label`,
      reasonKey: `${NS}addSurveyQuestions.reason`,
      kind: "do",
      weight: 100,
    }),
  },
  {
    test: (s) => s.questionCount > 0 && s.status !== "live",
    action: () => ({
      id: "publish_survey",
      actionType: "publish_survey",
      labelKey: `${NS}publishSurvey.label`,
      reasonKey: `${NS}publishSurvey.reason`,
      kind: "do",
      weight: 90,
    }),
  },
  {
    test: (s) =>
      s.status === "live" && s.completedResponses < SURVEY_MIN_RESPONSES,
    action: (s) => ({
      id: "share_survey",
      actionType: "share_survey",
      labelKey: `${NS}shareSurvey.label`,
      reasonKey: `${NS}shareSurvey.reason`,
      params: { count: s.completedResponses, min: SURVEY_MIN_RESPONSES },
      kind: "do",
      weight: 80,
    }),
  },
  {
    test: (s) =>
      s.completedResponses >= SURVEY_MIN_RESPONSES && !s.hasReport,
    action: (s) => ({
      id: "generate_report",
      actionType: "generate_report",
      labelKey: `${NS}generateReport.label`,
      reasonKey: `${NS}generateReport.reason`,
      params: { count: s.completedResponses },
      kind: "do",
      weight: 85,
    }),
  },
  {
    test: (s) =>
      s.hasReport && s.completedResponses > s.reportResponseCount,
    action: (s) => ({
      id: "refresh_report",
      actionType: "refresh_report",
      labelKey: `${NS}refreshReport.label`,
      reasonKey: `${NS}refreshReport.reason`,
      params: { count: s.completedResponses - s.reportResponseCount },
      kind: "do",
      weight: 70,
    }),
  },
];

const SURVEY_DONE: NextAction = {
  id: "survey_done",
  actionType: "done",
  labelKey: `${NS}surveyDone.label`,
  reasonKey: `${NS}surveyDone.reason`,
  kind: "done",
  weight: 0,
};

export function resolveSurveyNextAction(input: SurveyNbaInput): NextAction {
  for (const rule of SURVEY_RULES) {
    if (rule.test(input)) return rule.action(input);
  }
  return SURVEY_DONE;
}

// ── Workspace / home ─────────────────────────────────────────────────────────

/** Coarse per-study signal from the studies-list summary. */
export interface StudyNbaSummary {
  id: string;
  name: string;
  surveyCount: number;
  projectCount: number;
  completedResponseCount: number;
  completedInterviewCount: number;
  hasReport: boolean;
}

const WS_MIN_RESPONSES = 30;
const WS_MIN_INTERVIEWS = 3;

/**
 * The next action for one study — always returns something (a "done"
 * action when the study has a report and needs nothing). Use this for
 * per-study UI like the home study cards.
 */
export function resolveStudySummaryAction(s: StudyNbaSummary): NextAction {
  return (
    studyCandidate(s) ?? {
      id: `study_done_${s.id}`,
      actionType: "done",
      labelKey: `${NS}studyDone.label`,
      reasonKey: `${NS}studyDone.reason`,
      params: { name: s.name },
      kind: "done",
      weight: 0,
      targetId: s.id,
    }
  );
}

/** The candidate next action for one study, or null if it needs nothing. */
function studyCandidate(s: StudyNbaSummary): NextAction | null {
  if (s.surveyCount + s.projectCount === 0) {
    return {
      id: `set_up_${s.id}`,
      actionType: "set_up_study",
      labelKey: `${NS}setUpStudy.label`,
      reasonKey: `${NS}setUpStudy.reason`,
      params: { name: s.name },
      kind: "do",
      weight: 95,
      targetId: s.id,
    };
  }
  const hasData =
    s.completedInterviewCount >= WS_MIN_INTERVIEWS ||
    s.completedResponseCount >= WS_MIN_RESPONSES;
  if (hasData && !s.hasReport) {
    return {
      id: `analyze_${s.id}`,
      actionType: "analyze_study",
      labelKey: `${NS}analyzeStudy.label`,
      reasonKey: `${NS}analyzeStudy.reason`,
      params: { name: s.name },
      kind: "do",
      weight: 85,
      targetId: s.id,
    };
  }
  if (!s.hasReport) {
    return {
      id: `collect_${s.id}`,
      actionType: "collect_study",
      labelKey: `${NS}collectStudy.label`,
      reasonKey: `${NS}collectStudy.reason`,
      params: { name: s.name },
      kind: "wait",
      weight: 45,
      targetId: s.id,
    };
  }
  return null; // has a report — nothing needs doing
}

/**
 * The single study across the workspace that most needs attention — the
 * highest-weight candidate. Drives the home-page copilot suggestion.
 */
/** The workspace-level cross-study synthesis signal (decision memos). */
export interface WorkspaceMemoSignal {
  /** Studies with at least one ready analysis — memo-eligible. */
  eligibleStudyCount: number;
  /** Ready decision memos in the workspace. */
  readyMemoCount: number;
  /** Ready memos where an included study has newer analysis evidence. */
  staleMemoCount: number;
}

export function resolveWorkspaceNextAction(
  studies: StudyNbaSummary[],
  memoSignal?: WorkspaceMemoSignal,
): NextAction {
  if (studies.length === 0) {
    return {
      id: "start_first_study",
      actionType: "start_study",
      labelKey: `${NS}startFirstStudy.label`,
      reasonKey: `${NS}startFirstStudy.reason`,
      kind: "do",
      weight: 100,
    };
  }
  let best: NextAction | null = null;
  for (const s of studies) {
    const candidate = studyCandidate(s);
    if (candidate && (!best || candidate.weight > best.weight)) {
      best = candidate;
    }
  }
  // Actionable per-study work always outranks synthesis suggestions.
  if (best && best.kind === "do") return best;

  // Cross-study rungs: exactly the moment the per-study ladders go quiet
  // ("all set") is when the highest-value next step is synthesis.
  if (memoSignal) {
    if (memoSignal.staleMemoCount > 0) {
      return {
        id: "refresh_memo",
        actionType: "refresh_memo",
        labelKey: `${NS}refreshMemo.label`,
        reasonKey: `${NS}refreshMemo.reason`,
        params: { count: memoSignal.staleMemoCount },
        kind: "do",
        weight: 40,
      };
    }
    if (
      memoSignal.readyMemoCount === 0 &&
      memoSignal.eligibleStudyCount >= 2
    ) {
      return {
        id: "generate_memo",
        actionType: "generate_memo",
        labelKey: `${NS}generateMemo.label`,
        reasonKey: `${NS}generateMemo.reason`,
        params: { count: memoSignal.eligibleStudyCount },
        kind: "do",
        weight: 35,
      };
    }
  }

  return (
    best ?? {
      id: "workspace_done",
      actionType: "done",
      labelKey: `${NS}workspaceDone.label`,
      reasonKey: `${NS}workspaceDone.reason`,
      kind: "done",
      weight: 0,
    }
  );
}
