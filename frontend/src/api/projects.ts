import client from "./client";

export interface QuestionCreate {
  section_index: number;
  section_title: string;
  question_index: number;
  main_question: string;
  interview_notes?: string;
  desired_learning?: string;
}

export interface ScreeningQuestionCreate {
  question: string;
  options: string[];
  disqualifying_options: string[];
}

export interface ScreeningTranslation {
  question: string;
  options: string[];
}

export interface ScreeningQuestionResponse {
  id: string;
  question: string;
  options: string[];
  disqualifying_options: string[];
  sort_order: number;
  translations?: Record<string, ScreeningTranslation>;
}

export interface ProjectCreate {
  name: string;
  language: string;
  /** When set, the interview round joins this existing Study (Sprint 15). */
  study_id?: string;
  interview_duration_minutes?: number;
  system_prompt?: string;
  research_objective?: string;
  // Study-specific grounding fields sent to the analysis prompt. These
  // override whatever company-level context is attached via business_context.
  decision_to_inform?: string;
  target_customer_description?: string;
  welcome_message?: string;
  questions: QuestionCreate[];
  screening_questions?: ScreeningQuestionCreate[];
}

export interface QuestionResponse {
  id: string;
  section_index: number;
  section_title: string;
  question_index: number;
  main_question: string;
  interview_notes?: string;
  desired_learning?: string;
  researcher_notes?: string | null;
  deprecated_at?: string | null;
}

export interface ProjectResponse {
  id: string;
  company_id: string;
  /** Parent Study — drives the breadcrumb on the rehoused interview detail. */
  study_id?: string | null;
  study_name?: string | null;
  name: string;
  language: string;
  interview_duration_minutes: number;
  system_prompt?: string;
  research_objective?: string;
  decision_to_inform?: string | null;
  target_customer_description?: string | null;
  /** Completed-interview target for this round (advisory). */
  target_participants?: number | null;
  welcome_message?: string;
  panel_collection_enabled?: boolean;
  /** PF-3: when true (default), engine opens with a warm-up turn before the first guide question. */
  warmup_enabled?: boolean;
  is_demo?: boolean;
  /** Participant-facing identity policy: standard | branded | anonymous. */
  branding_mode?: "standard" | "branded" | "anonymous";
  brand_primary_color?: string | null;
  brand_font?: string | null;
  researcher_name?: string | null;
  researcher_logo_url?: string | null;
  privacy_policy_url?: string | null;
  created_at: string;
  questions: QuestionResponse[];
  screening_questions: ScreeningQuestionResponse[];
  plan_context?: PlanContext | null;
}

export interface PlanContext {
  plan_id: string;
  plan_name: string;
  /** 1-based order_index of this step in the plan. */
  step_index: number;
  /** Total number of steps in the parent plan. */
  total_steps: number;
  /** e.g. "voice_interview". */
  step_method: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  language: string;
  created_at: string;
  archived_at: string | null;
  question_count: number;
  completed_count: number;
  in_progress_count: number;
  analysis_status: string | null;
  /** Most-recent participant completion timestamp; null until someone
   *  finishes an interview. Used for "N days since last response" nudges. */
  last_response_at: string | null;
  is_demo?: boolean;
  /** Wave E — surfaces when this project is the drafted step of a
   *  ResearchPlan. Dashboard shows "Step N of M in <plan name>". */
  plan_context?: PlanContext | null;
}

export interface InterviewLink {
  id: string;
  project_id: string;
  token: string;
  is_active: boolean;
  /** Participant ceiling for this link; null = uncapped. */
  max_participants: number | null;
  /** Participants admitted through this link so far. */
  participant_count: number;
  created_at: string;
}

export interface ParticipantResponse {
  id: string;
  display_name: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  age_range?: string | null;
  profession?: string | null;
  country?: string | null;
  email?: string | null;
  email_verified?: boolean;
  /** True = agreed to be recontacted for future studies, false = declined,
   *  null/undefined = unknown (pre-feature participants). */
  panel_consent?: boolean | null;
  quality_score?: number | null;
  quality_label?: string | null;
  quality_summary?: string | null;
  quality_strengths?: string[] | null;
  quality_issues?: string[] | null;
  avg_response_words?: number | null;
  short_answer_pct?: number | null;
  /** V4 paywall — true when this participant's transcript body is
   *  hidden behind the free-preview paywall for the current
   *  workspace. List view shows a locked row; transcript endpoint
   *  returns 402. */
  is_locked?: boolean;
}

/** V4 paywall response body — returned with HTTP 402 from gated
 *  endpoints (transcript view, analysis). */
export interface PaywallDetail {
  paywall: true;
  reason: "free_preview_exhausted";
  free_preview_count: number;
  locked_completed_count: number;
  unlock_paths: ("subscription" | "credit_pack")[];
  has_ever_paid: boolean;
  feature?: "transcript" | "analysis";
}

export interface QualityAssessment {
  quality_score: number;
  quality_label: string;
  summary: string;
  strengths: string[];
  issues: string[];
  avg_response_words: number;
  short_answer_pct: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptTurn {
  id: string;
  turn_index: number;
  question_text: string;
  response_transcript: string | null;
  response_segments: TranscriptSegment[] | null;
  is_follow_up: boolean;
  manually_edited: boolean;
  edited_at: string | null;
  created_at: string;
  audio_recording_url: string | null;
  tts_audio_url: string | null;
  translated_response: string | null;
  translated_question: string | null;
  translation_language: string | null;
  cleaned_response: string | null;
  cleaned_at: string | null;
}

// ── Analysis types ─────────────────────────────────────────────────────────

export interface AttributedQuote {
  text: string;
  participant_identifier?: string;
  participant_display_name?: string;
  turn_index?: number;
  question_text?: string;
}

export interface AnalysisTheme {
  title: string;
  summary: string;
  quotes: (AttributedQuote | string)[];
  frequency: string;
  researcher_note?: string;
}

export type ThemeAnnotationStatus = "confirmed" | "disputed" | "needs_evidence";

export interface ThemeAnnotation {
  id?: string;
  analysis_id: string;
  theme_title: string;
  status: ThemeAnnotationStatus;
  researcher_note: string | null;
}
export interface AnalysisJTBD {
  job: string;
  insight: string;
  frequency: string;
}
export interface AnalysisTension {
  tension: string;
  detail: string;
}
// Recommendations were upgraded from plain strings to objects (action + owner +
// horizon + impact + effort + kpi + falsifier). Both shapes coexist: analyses
// generated before the upgrade stay strings. Always read them through
// `recommendationText()` so old and new data render safely.
export interface AnalysisRecommendation {
  action: string;
  rationale?: string;
  owner_role?: string;
  horizon?: string;
  impact?: string;
  effort?: string;
  kpi?: string;
  falsifier?: string;
}
export type Recommendation = string | AnalysisRecommendation;

/** Display headline for a recommendation of either shape. */
export function recommendationText(r: Recommendation): string {
  return typeof r === "string" ? r : r?.action ?? "";
}

export interface AnalysisReport {
  summary: string;
  themes: AnalysisTheme[];
  jobs_to_be_done: AnalysisJTBD[];
  tensions: AnalysisTension[];
  recommendations: Recommendation[];
  confidence: string;
  confidence_rationale?: string;
  participant_count: number;
}
export interface AnalysisResponse {
  status: "none" | "generating" | "ready" | "failed";
  completed_count: number;
  participant_count: number;
  generated_at: string | null;
  report: AnalysisReport | null;
  filters: { filter_by: string; filter_values: string[] } | null;
  error: string | null;
  analysis_id: string | null;
  version: number | null;
  version_label: string | null;
}

// ── Coding types ────────────────────────────────────────────────────────────

export interface ManualCode {
  id: string;
  project_id: string;
  name: string;
  color: string;
  sort_order: number;
  tag_count: number;
  created_at: string;
}

export interface QuoteTag {
  id: string;
  turn_id: string;
  manual_code_id: string;
  code_name: string | null;
  code_color: string | null;
  selected_text: string;
  start_index: number;
  end_index: number;
  tagged_from_translation?: boolean;
  participant_id?: string | null;
  participant_display_name?: string | null;
  created_at: string;
}

// ── Memo types ──────────────────────────────────────────────────────────────

export interface ProjectMemo {
  id: string;
  project_id: string;
  type: "general" | "theme_note" | "tension_note" | "jtbd_note";
  linked_key: string | null;
  content: string;
  created_at: string;
  updated_at: string;
}

// ── Heatmap types ───────────────────────────────────────────────────────────

export interface HeatmapTheme {
  title: string;
  segment_counts: Record<string, number>;
}

export interface HeatmapResponse {
  segments: string[];
  segment_participants: Record<string, string[]>;
  themes: HeatmapTheme[];
}

// ── API functions ───────────────────────────────────────────────────────────

export async function listProjects(archived = false): Promise<ProjectListItem[]> {
  const { data } = await client.get<ProjectListItem[]>("/projects/", {
    params: archived ? { archived: true } : {},
  });
  return data;
}

export async function archiveProject(id: string): Promise<{ id: string; archived_at: string }> {
  const { data } = await client.patch<{ id: string; archived_at: string }>(`/projects/${id}/archive`);
  return data;
}

export async function unarchiveProject(id: string): Promise<{ id: string; archived_at: null }> {
  const { data } = await client.patch<{ id: string; archived_at: null }>(`/projects/${id}/unarchive`);
  return data;
}

export async function getProject(id: string): Promise<ProjectResponse> {
  const { data } = await client.get<ProjectResponse>(`/projects/${id}`);
  return data;
}

export async function createProject(body: ProjectCreate): Promise<ProjectResponse> {
  const { data } = await client.post<ProjectResponse>("/projects/", body);
  return data;
}

export async function createDemoProject(): Promise<ProjectResponse> {
  const { data } = await client.post<ProjectResponse>("/projects/demo");
  return data;
}

export async function updateProject(id: string, body: ProjectCreate): Promise<ProjectResponse> {
  const { data } = await client.put<ProjectResponse>(`/projects/${id}`, body);
  return data;
}

export async function patchProjectSettings(
  id: string,
  settings: {
    name?: string;
    panel_collection_enabled?: boolean;
    warmup_enabled?: boolean;
    research_objective?: string;
    research_context?: string;
    interview_duration_minutes?: number;
    target_participants?: number;
    branding_mode?: "standard" | "branded" | "anonymous";
    brand_primary_color?: string;
    brand_font?: string;
    researcher_name?: string;
    researcher_logo_url?: string;
    privacy_policy_url?: string;
  }
): Promise<ProjectResponse> {
  const { data } = await client.patch<ProjectResponse>(`/projects/${id}/settings`, settings);
  return data;
}

export async function uploadProjectLogo(id: string, file: File): Promise<ProjectResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<ProjectResponse>(`/projects/${id}/branding/logo`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function importProjectCSV(name: string, language: string, csvFile: File): Promise<ProjectResponse> {
  const form = new FormData();
  form.append("name", name);
  form.append("language", language);
  form.append("csv_file", csvFile);
  const { data } = await client.post<ProjectResponse>("/projects/import", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await client.delete(`/projects/${id}`);
}

export async function patchQuestion(
  projectId: string,
  questionId: string,
  body: { main_question?: string | null; question_index?: number | null; section_title?: string | null; section_index?: number | null; researcher_notes?: string | null; deprecated_at?: string | null; interview_notes?: string | null; desired_learning?: string | null }
): Promise<QuestionResponse> {
  const { data } = await client.patch<QuestionResponse>(
    `/projects/${projectId}/questions/${questionId}`,
    body
  );
  return data;
}

/** Add a single interview-guide question. Section/question indices are
 *  derived server-side from the section title. Powers the Research Copilot. */
export async function createGuideQuestion(
  projectId: string,
  body: {
    section_title: string;
    main_question: string;
    desired_learning?: string;
    interview_notes?: string;
    researcher_notes?: string;
  },
): Promise<QuestionResponse> {
  const { data } = await client.post<QuestionResponse>(
    `/projects/${projectId}/questions`,
    body,
  );
  return data;
}

export async function createScreeningQuestion(
  projectId: string,
  body: {
    question: string;
    options: string[];
    disqualifying_options: string[];
  },
): Promise<ScreeningQuestionResponse> {
  const { data } = await client.post<ScreeningQuestionResponse>(
    `/projects/${projectId}/screening`,
    body,
  );
  return data;
}

export async function patchScreeningTranslation(
  projectId: string,
  screeningId: string,
  body: { lang: string; question: string; options: string[] },
): Promise<ScreeningQuestionResponse> {
  const { data } = await client.patch<ScreeningQuestionResponse>(
    `/projects/${projectId}/screening/${screeningId}/translations`,
    body,
  );
  return data;
}

export async function regenerateScreeningTranslations(projectId: string): Promise<void> {
  await client.post(`/projects/${projectId}/screening/regenerate-translations`);
}

/** Auto-translate a screening question into one language via Claude (cached
 *  server-side). Returns the question with its freshly generated translation. */
export async function generateScreeningTranslation(
  projectId: string,
  screeningId: string,
  lang: string,
): Promise<ScreeningQuestionResponse> {
  const { data } = await client.post<ScreeningQuestionResponse>(
    `/projects/${projectId}/screening/${screeningId}/translations/${lang}/generate`,
  );
  return data;
}

export async function createLink(projectId: string): Promise<InterviewLink> {
  const { data } = await client.post<InterviewLink>(`/projects/${projectId}/links`);
  return data;
}

export async function getLinks(projectId: string): Promise<InterviewLink[]> {
  const { data } = await client.get<InterviewLink[]>(`/projects/${projectId}/links`);
  return data;
}

export async function toggleLink(linkId: string): Promise<InterviewLink> {
  const { data } = await client.patch<InterviewLink>(`/links/${linkId}`);
  return data;
}

/** Set or remove the per-link participant cap. Pass null to remove it. */
export async function setLinkCap(
  linkId: string,
  maxParticipants: number | null,
): Promise<InterviewLink> {
  const { data } = await client.patch<InterviewLink>(
    `/links/${linkId}`,
    maxParticipants === null
      ? { clear_max_participants: true }
      : { max_participants: maxParticipants },
  );
  return data;
}

export async function deleteParticipant(projectId: string, participantId: string): Promise<void> {
  await client.delete(`/projects/${projectId}/participants/${participantId}`);
}

export async function getParticipants(projectId: string): Promise<ParticipantResponse[]> {
  const { data } = await client.get<ParticipantResponse[]>(`/projects/${projectId}/participants`);
  return data;
}

export async function getTranscript(
  projectId: string,
  participantId: string
): Promise<{ participant: ParticipantResponse; turns: TranscriptTurn[]; translation_language: string | null }> {
  const { data } = await client.get<{ participant: ParticipantResponse; turns: TranscriptTurn[]; translation_language: string | null }>(
    `/projects/${projectId}/participants/${participantId}/transcript`
  );
  return data;
}

export async function translateTranscript(
  projectId: string,
  participantId: string,
  targetLanguage: string
): Promise<{ status: string; target_language: string }> {
  const { data } = await client.post(
    `/projects/${projectId}/participants/${participantId}/translate`,
    { target_language: targetLanguage }
  );
  return data;
}

export async function updateTurn(
  projectId: string,
  participantId: string,
  turnId: string,
  responseTranscript: string
): Promise<{ id: string; turn_index: number; response_transcript: string; manually_edited: boolean; edited_at: string | null }> {
  const { data } = await client.put(
    `/projects/${projectId}/participants/${participantId}/turns/${turnId}`,
    { response_transcript: responseTranscript }
  );
  return data;
}

export async function getAnalysis(projectId: string): Promise<AnalysisResponse> {
  const { data } = await client.get<AnalysisResponse>(`/projects/${projectId}/analysis`);
  return data;
}

export async function triggerAnalysis(
  projectId: string,
  filters?: { filter_by: string; filter_values: string[] }
): Promise<void> {
  await client.post(`/projects/${projectId}/analysis`, filters ?? {});
}

export async function getHeatmap(projectId: string): Promise<HeatmapResponse> {
  const { data } = await client.get<HeatmapResponse>(`/projects/${projectId}/analysis/heatmap`);
  return data;
}

export async function exportCSV(projectId: string): Promise<Blob> {
  const { data } = await client.get(`/projects/${projectId}/export`, { responseType: "blob" });
  return data;
}

export async function fetchAnalysisReportHtml(projectId: string, version?: number): Promise<Blob> {
  const { data } = await client.get(`/projects/${projectId}/analysis/report.html`, {
    params: version != null ? { version } : undefined,
    responseType: "blob",
  });
  return data;
}

// ── Coding API ──────────────────────────────────────────────────────────────

export async function getCodes(projectId: string): Promise<ManualCode[]> {
  const { data } = await client.get<ManualCode[]>(`/projects/${projectId}/codes`);
  return data;
}

export async function createCode(projectId: string, name: string, color: string): Promise<ManualCode> {
  const { data } = await client.post<ManualCode>(`/projects/${projectId}/codes`, { name, color });
  return data;
}

export async function updateCode(projectId: string, codeId: string, body: { name?: string; color?: string }): Promise<ManualCode> {
  const { data } = await client.patch<ManualCode>(`/projects/${projectId}/codes/${codeId}`, body);
  return data;
}

export async function deleteCode(projectId: string, codeId: string): Promise<void> {
  await client.delete(`/projects/${projectId}/codes/${codeId}`);
}

export async function getTags(projectId: string): Promise<QuoteTag[]> {
  const { data } = await client.get<QuoteTag[]>(`/projects/${projectId}/tags`);
  return data;
}

export async function createTag(
  projectId: string,
  turnId: string,
  body: { manual_code_id: string; selected_text: string; start_index: number; end_index: number; tagged_from_translation?: boolean }
): Promise<QuoteTag> {
  const { data } = await client.post<QuoteTag>(`/projects/${projectId}/turns/${turnId}/tags`, body);
  return data;
}

export async function deleteTag(projectId: string, tagId: string): Promise<void> {
  await client.delete(`/projects/${projectId}/tags/${tagId}`);
}

// ── Memos API ───────────────────────────────────────────────────────────────

export async function getMemos(projectId: string): Promise<ProjectMemo[]> {
  const { data } = await client.get<ProjectMemo[]>(`/projects/${projectId}/memos`);
  return data;
}

export async function createMemo(
  projectId: string,
  body: { type: string; linked_key?: string | null; content: string }
): Promise<ProjectMemo> {
  const { data } = await client.post<ProjectMemo>(`/projects/${projectId}/memos`, body);
  return data;
}

export async function updateMemo(projectId: string, memoId: string, content: string): Promise<ProjectMemo> {
  const { data } = await client.put<ProjectMemo>(`/projects/${projectId}/memos/${memoId}`, { content });
  return data;
}

export async function deleteMemo(projectId: string, memoId: string): Promise<void> {
  await client.delete(`/projects/${projectId}/memos/${memoId}`);
}

export async function shareAnalysis(projectId: string): Promise<{ share_token: string }> {
  const { data } = await client.post<{ share_token: string }>(`/projects/${projectId}/analysis/share`);
  return data;
}

export async function revokeAnalysisShare(projectId: string): Promise<void> {
  await client.delete(`/projects/${projectId}/analysis/share`);
}

export interface AnalysisVersionMeta {
  version: number;
  generated_at: string | null;
  participant_count: number;
  filters: { filter_by: string; filter_values: string[] } | null;
  version_label: string;
  parent_version: number | null;
  annotation_count: number;
}

export async function getAnalysisHistory(projectId: string): Promise<AnalysisVersionMeta[]> {
  const { data } = await client.get<AnalysisVersionMeta[]>(`/projects/${projectId}/analysis/versions`);
  return data;
}

export async function getAnalysisByVersion(projectId: string, version: number): Promise<AnalysisResponse> {
  const { data } = await client.get<AnalysisResponse>(`/projects/${projectId}/analysis/${version}`);
  return data;
}

export async function upsertThemeAnnotation(
  projectId: string,
  body: { analysis_id: string; theme_title: string; status: ThemeAnnotationStatus; researcher_note: string | null }
): Promise<ThemeAnnotation> {
  const { data } = await client.post<ThemeAnnotation>(`/projects/${projectId}/analysis/annotations`, body);
  return data;
}

export async function getThemeAnnotations(projectId: string, analysisId: string): Promise<ThemeAnnotation[]> {
  const { data } = await client.get<ThemeAnnotation[]>(`/projects/${projectId}/analysis/annotations/${analysisId}`);
  return data;
}

export async function saveResearcherContext(projectId: string, version: number, context: string): Promise<void> {
  await client.patch(`/projects/${projectId}/analysis/${version}/context`, { researcher_context: context });
}

export async function triggerRefinedAnalysis(projectId: string): Promise<{ status: string; version: number }> {
  const { data } = await client.post<{ status: string; version: number }>(`/projects/${projectId}/analysis/refine`);
  return data;
}

// ---------------------------------------------------------------------------
// Project state summary — drives the Overview "state-of-study" card and the
// Dashboard stale-project nudges.
// ---------------------------------------------------------------------------

export interface ProjectStateLatestAnalysis {
  version: number | null;
  status: string | null;
  generated_at: string | null;
  participant_count: number | null;
  is_behind: boolean;
  gap: number;
}

export interface ProjectState {
  completed_count: number;
  in_progress_count: number;
  target_count: number | null;
  last_response_at: string | null;
  days_since_last_response: number | null;
  is_stale: boolean;
  latest_analysis: ProjectStateLatestAnalysis | null;
  headline: string;
  suggested_next_action: string;
}

export async function getProjectState(
  projectId: string,
  includeAiSummary = true
): Promise<ProjectState> {
  const { data } = await client.get<ProjectState>(`/projects/${projectId}/state`, {
    params: { include_ai_summary: includeAiSummary },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Promote an analysis theme into a codebook code (with auto-tagged quotes).
// ---------------------------------------------------------------------------

export interface PromoteThemeResult {
  code: ManualCode;
  tags_created: Array<{
    id: string;
    turn_id: string;
    selected_text: string;
    already_existed: boolean;
  }>;
  unmatched_quotes: Array<{
    text: string;
    participant_display_name?: string | null;
    reason: string;
  }>;
}

export async function promoteThemeToCode(
  projectId: string,
  analysisId: string,
  themeTitle: string,
  color?: string
): Promise<PromoteThemeResult> {
  const { data } = await client.post<PromoteThemeResult>(
    `/projects/${projectId}/analysis/themes/promote-to-code`,
    { analysis_id: analysisId, theme_title: themeTitle, color }
  );
  return data;
}
