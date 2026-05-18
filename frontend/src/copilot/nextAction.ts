/**
 * Next-best-action resolver — the deterministic core of the always-on
 * Research Copilot.
 *
 * This is intentionally NOT an LLM call. The single highest-value thing a
 * researcher should do next is a function of instrument state, so it's a
 * priority ladder: the first rule whose `test` passes wins. Instant, free,
 * runs on data the pages already hold.
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
  // shared terminal states
  | "wait"
  | "done";

export interface NextAction {
  /** Stable id — also used to dedupe a dismissed suggestion. */
  id: string;
  actionType: NbaActionType;
  /** Imperative, short — the chip label. e.g. "Run the analysis". */
  label: string;
  /** One line of why — the chip's subtext. */
  reason: string;
  /** do = actionable (accent), wait = informational (muted), done = quiet. */
  kind: "do" | "wait" | "done";
  /** Priority for cross-scope ranking (workspace NBA = max across studies). */
  weight: number;
  /** Where the action routes — e.g. the study a workspace action points at. */
  targetId?: string;
}

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
      label: "Draft your interview guide",
      reason: "This round has no questions yet — the copilot can draft a full guide.",
      kind: "do",
      weight: 100,
    }),
  },
  {
    test: (s) => s.guideQuestionCount > 0 && s.activeLinkCount === 0,
    action: () => ({
      id: "create_link",
      actionType: "create_link",
      label: "Create an interview link",
      reason: "Your guide is ready — you need a link before anyone can take part.",
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
      label: "Share your interview link",
      reason: "The round is live but no one has started — share the link to collect responses.",
      kind: "do",
      weight: 80,
    }),
  },
  {
    test: (s) => s.completedCount >= 3 && s.analysisStatus === "none",
    action: (s) => ({
      id: "run_analysis",
      actionType: "run_analysis",
      label: "Run the analysis",
      reason: `${s.completedCount} interviews are in and none analysed yet.`,
      kind: "do",
      weight: 85,
    }),
  },
  {
    test: (s) =>
      s.analysisStatus === "ready" &&
      s.completedCount > s.analysisParticipantCount,
    action: (s) => ({
      id: "refresh_analysis",
      actionType: "refresh_analysis",
      label: "Refresh the analysis",
      reason: `${s.completedCount - s.analysisParticipantCount} new interview(s) landed since the last analysis.`,
      kind: "do",
      weight: 70,
    }),
  },
  {
    test: (s) => s.analysisStatus === "ready" && s.annotationCount === 0,
    action: () => ({
      id: "review_themes",
      actionType: "review_themes",
      label: "Review the themes",
      reason: "Your analysis is ready — confirm or challenge each theme to sharpen it.",
      kind: "do",
      weight: 60,
    }),
  },
  {
    test: (s) => s.analysisStatus === "ready" && s.annotationCount > 0,
    action: () => ({
      id: "refine_analysis",
      actionType: "refine_analysis",
      label: "Refine the analysis",
      reason: "You've annotated themes — refine for a sharper v2 that takes them into account.",
      kind: "do",
      weight: 55,
    }),
  },
  {
    test: (s) => s.inProgressCount > 0 && s.completedCount === 0,
    action: (s) => ({
      id: "wait_responses",
      actionType: "wait",
      label: "Waiting on first responses",
      reason: `${s.inProgressCount} interview(s) in progress — nothing to do until they finish.`,
      kind: "wait",
      weight: 40,
    }),
  },
];

const PROJECT_DONE: NextAction = {
  id: "project_done",
  actionType: "done",
  label: "This round is in good shape",
  reason: "Nothing needs you right now.",
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
      label: "Add survey questions",
      reason: "This survey is empty — the copilot can draft a question set.",
      kind: "do",
      weight: 100,
    }),
  },
  {
    test: (s) => s.questionCount > 0 && s.status !== "live",
    action: () => ({
      id: "publish_survey",
      actionType: "publish_survey",
      label: "Publish the survey",
      reason: "Your questions are ready — publish to start collecting responses.",
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
      label: "Share the survey",
      reason: `${s.completedResponses}/${SURVEY_MIN_RESPONSES} responses — share the link to reach a reliable sample.`,
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
      label: "Generate the report",
      reason: `${s.completedResponses} responses are in — synthesise them into findings.`,
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
      label: "Refresh the report",
      reason: `${s.completedResponses - s.reportResponseCount} new response(s) since the last report.`,
      kind: "do",
      weight: 70,
    }),
  },
];

const SURVEY_DONE: NextAction = {
  id: "survey_done",
  actionType: "done",
  label: "This survey is in good shape",
  reason: "Nothing needs you right now.",
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
      label: `“${s.name}” is in good shape`,
      reason: "This study has a report — nothing needs you right now.",
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
      label: `Set up “${s.name}”`,
      reason: "This study has no survey or interview round yet.",
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
      label: `Analyse “${s.name}”`,
      reason: "Enough data is in — synthesise it into findings.",
      kind: "do",
      weight: 85,
      targetId: s.id,
    };
  }
  if (!s.hasReport) {
    return {
      id: `collect_${s.id}`,
      actionType: "collect_study",
      label: `“${s.name}” is collecting`,
      reason: "Responses are still coming in — share the links to reach a sample.",
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
export function resolveWorkspaceNextAction(
  studies: StudyNbaSummary[],
): NextAction {
  if (studies.length === 0) {
    return {
      id: "start_first_study",
      actionType: "start_study",
      label: "Start your first study",
      reason: "A study is one research effort — a survey, an interview round, or both.",
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
  return (
    best ?? {
      id: "workspace_done",
      actionType: "done",
      label: "Your studies are all moving",
      reason: "Every study has a report — nothing needs you right now.",
      kind: "done",
      weight: 0,
    }
  );
}
