import client from "./client";
import type { SurveyRole, SurveyStatus } from "./surveys";

/**
 * Studies API client — mirrors backend/app/routers/studies.py.
 *
 * The Study Overview page (Sprint 9.5) is the primary research-workspace
 * surface. Surveys and Projects live as instruments inside a Study.
 */

export interface ProjectMini {
  id: string;
  name: string;
  language: string;
  interview_link_count: number;
  completed_participant_count: number;
  in_progress_participant_count: number;
  /** True when the round has a ready qualitative analysis. */
  has_ready_analysis: boolean;
}

/** The one instrument of a single-instrument study (see StudySummary). */
export interface SoleInstrument {
  kind: "survey" | "interview";
  id: string;
  survey_status: string | null;
}

export interface SurveyMini {
  id: string;
  name: string;
  role: SurveyRole;
  status: SurveyStatus;
  question_count: number;
  response_count: number;
  completed_count: number;
}

export interface StudyProgress {
  has_live_survey: boolean;
  total_completed_responses: number;
  segments_identified_placeholder: boolean;
  interviews_completed: number;
  report_ready_placeholder: boolean;
}

export interface StudySummary {
  id: string;
  name: string;
  created_at: string;
  archived_at: string | null;
  survey_count: number;
  project_count: number;
  participant_count: number;
  // Sprint 17: card-level progress signals for the Studies-list home.
  completed_response_count: number;
  completed_interview_count: number;
  has_report: boolean;
  /** Eligible for a cross-study decision memo (any ready analysis). */
  has_ready_analysis: boolean;
  /** Seeded showcase study — badged in lists, excluded from workspace totals. */
  is_demo: boolean;
  /** Set only when the study has exactly one instrument — the list links straight to it. */
  sole_instrument: SoleInstrument | null;
}

/**
 * Where a click on a study row should land. Single-instrument studies skip
 * the workspace hop and open their one instrument (drafts open the builder,
 * fielding/closed surveys open results); the workspace stays one breadcrumb
 * away. Multi-instrument studies open the workspace.
 */
export function studyEntryPath(s: StudySummary): string {
  const si = s.sole_instrument;
  if (!si) return `/studies/${s.id}`;
  if (si.kind === "survey") {
    return si.survey_status === "draft"
      ? `/surveys/${si.id}/edit`
      : `/surveys/${si.id}/dashboard`;
  }
  return `/projects/${si.id}`;
}

export interface StudyDetail {
  id: string;
  name: string;
  created_at: string;
  archived_at: string | null;
  surveys: SurveyMini[];
  projects: ProjectMini[];
  progress: StudyProgress;
  is_demo: boolean;
  /** English fallback text — prefer `recommended_action_key` for display. */
  recommended_action: string | null;
  /** i18n key stem for the recommended action (see study.json → overview.recommendedAction.actions). */
  recommended_action_key: string | null;
  recommended_action_params: Record<string, number> | null;
}

export async function listStudies(archived = false): Promise<StudySummary[]> {
  const resp = await client.get<StudySummary[]>("/studies/", {
    params: archived ? { archived: true } : {},
  });
  return resp.data;
}

export async function archiveStudy(id: string): Promise<{ id: string; archived_at: string }> {
  const resp = await client.patch<{ id: string; archived_at: string }>(`/studies/${id}/archive`);
  return resp.data;
}

export async function unarchiveStudy(id: string): Promise<{ id: string; archived_at: null }> {
  const resp = await client.patch<{ id: string; archived_at: null }>(`/studies/${id}/unarchive`);
  return resp.data;
}

export async function getStudy(id: string): Promise<StudyDetail> {
  const resp = await client.get<StudyDetail>(`/studies/${id}`);
  return resp.data;
}

/* ── Sprint 11: Quantified Themes report ─────────────────────── */

export type Confidence = "directional" | "supported" | "strong";
export type RecommendationKind = "product" | "marketing" | "next_research";

export interface SurveySignal {
  summary: string;
  n: number;
  percentage: number | null;
  segment_label: string | null;
  segment_over_index: number | null;
}

export interface InterviewEvidence {
  x_of_y: string;
  interview_count: number;
  anchor_quote: string;
  segments_mentioned: string[];
}

export interface ThemeRecommendation {
  kind: RecommendationKind;
  action: string;
  rationale: string | null;
  /** Falsifiable outcome that would confirm the action worked. Absent on older reports. */
  success_test?: string | null;
}

export interface QuantifiedTheme {
  title: string;
  survey_signal: SurveySignal | null;
  interview_evidence: InterviewEvidence | null;
  /** Divergent voice or signal that cuts against the theme. Absent on older reports. */
  counter_evidence?: string | null;
  recommendation: ThemeRecommendation;
  confidence: Confidence;
}

export interface QuantifiedThemeReport {
  executive_summary: string;
  /** Decision-oriented bottom line. Absent on older reports. */
  verdict?: string | null;
  themes: QuantifiedTheme[];
  /** What the data cannot answer. Absent on older reports. */
  gaps?: string[];
  methodology_note: string;
  generated_with_survey_count: number;
  generated_with_response_count: number;
  generated_with_interview_count: number;
}

export interface StudyAnalysis {
  id: string;
  study_id: string;
  version: number;
  status: "generating" | "ready" | "failed";
  error: string | null;
  created_at: string;
  generated_at: string | null;
  report: QuantifiedThemeReport | null;
}

export async function triggerAnalysis(studyId: string): Promise<StudyAnalysis> {
  const resp = await client.post<StudyAnalysis>(`/studies/${studyId}/analyses`);
  return resp.data;
}

export async function getLatestAnalysis(studyId: string): Promise<StudyAnalysis | null> {
  const resp = await client.get<StudyAnalysis | null>(`/studies/${studyId}/analyses/latest`);
  return resp.data;
}

export async function listAnalyses(studyId: string): Promise<StudyAnalysis[]> {
  const resp = await client.get<StudyAnalysis[]>(`/studies/${studyId}/analyses`);
  return resp.data;
}

export async function fetchStudyReportHtml(
  studyId: string,
  analysisId: string,
  opts?: { embed?: boolean },
): Promise<Blob> {
  const { data } = await client.get(`/studies/${studyId}/analyses/${analysisId}/report.html`, {
    responseType: "blob",
    params: opts?.embed ? { embed: 1 } : undefined,
  });
  return data;
}

/* ── Reports hub catalog: every ready report, by type ─────────────── */

export type ReportKind = "qualitative" | "survey" | "decision";

/** One generated report document — mirrors backend ReportCatalogEntry.
 *  Exactly one of project_id / survey_id / analysis_id is set, per `kind`. */
export interface ReportCatalogEntry {
  kind: ReportKind;
  study_id: string;
  study_name: string;
  is_demo: boolean;
  project_id: string | null;
  survey_id: string | null;
  analysis_id: string | null;
  interviews: number;
  responses: number;
}

export async function listReportCatalog(): Promise<ReportCatalogEntry[]> {
  const resp = await client.get<ReportCatalogEntry[]>("/studies/report-catalog");
  return resp.data;
}

/** Green qualitative findings report for one interview project. */
export async function fetchProjectReportHtml(projectId: string): Promise<Blob> {
  const { data } = await client.get(`/projects/${projectId}/analysis/report.html`, {
    responseType: "blob",
  });
  return data;
}

/** Blue survey results report for one survey. */
export async function fetchSurveyReportHtml(surveyId: string): Promise<Blob> {
  const { data } = await client.get(`/surveys/${surveyId}/dashboard/report.html`, {
    responseType: "blob",
  });
  return data;
}

/* ── Sprint 14: Validation surveys ────────────────────────────── */

export interface GeneratedValidationSurvey {
  survey_id: string;
  study_id: string;
  name: string;
  question_count: number;
}

export interface ThemeValidationSnapshot {
  theme_index: number;
  n_answered: number;
  agreement_pct: number | null;
  ci_low: number | null;
  ci_high: number | null;
  distribution: Record<string, number>;
}

export interface ValidationSummary {
  survey_id: string;
  survey_name: string;
  survey_status: string;
  n_responses: number;
  n_completed: number;
  per_theme: Record<string, ThemeValidationSnapshot>;
}

export async function createValidationSurvey(
  studyId: string,
  analysisId: string,
): Promise<GeneratedValidationSurvey> {
  const resp = await client.post<GeneratedValidationSurvey>(
    `/studies/${studyId}/analyses/${analysisId}/validation-survey`,
  );
  return resp.data;
}

export async function getValidationSummary(
  studyId: string,
  analysisId: string,
): Promise<ValidationSummary | null> {
  const resp = await client.get<ValidationSummary | null>(
    `/studies/${studyId}/analyses/${analysisId}/validation`,
  );
  return resp.data;
}
