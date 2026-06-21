import client from "./client";

export interface InterviewInfo {
  project_name: string;
  company_name?: string;
  language: string;
  welcome_message?: string;
  interview_duration_minutes?: number;
  question_count?: number;
  researcher_name?: string;
  researcher_logo_url?: string;
  research_context?: string;
  privacy_policy_url?: string;
  panel_collection_enabled?: boolean;
}

export interface ScreeningOption {
  value: string; // canonical option — submitted back to the gate (stable identity)
  label: string; // localized display text
}

export interface ScreeningQuestion {
  id: string;
  question: string;
  options: ScreeningOption[];
  sort_order: number;
}

export interface ScreenResult {
  qualified: boolean;
  disqualified_on?: string;
}

export interface StartInterviewResponse {
  participant_id: string;
  first_question: string;
  tts_audio_url?: string;
  /** True when the engine is opening with a warm-up turn (PF-3). */
  is_warmup?: boolean;
}

export interface SubmitAudioResponse {
  question_text: string | null;
  tts_audio_url?: string;
  is_complete: boolean;
  is_follow_up?: boolean;
  question_index?: number;
  elapsed_seconds?: number;
  total_seconds?: number;
  transcript?: string;
  /**
   * PF-3: gentle in-flight tip when the participant's last answers
   * trended short. Null when no nudge is warranted. Frontend renders
   * as a soft, dismissable inline banner above the record button.
   */
  coaching_hint?: string | null;
}

export interface ResumeCheck {
  found: boolean;
  participant_id?: string;
  last_question?: string;
  turn_count?: number;
  question_index?: number;
}

export interface ResumeSummary {
  questions_covered: string[];
  last_question?: string;
  turn_count: number;
  elapsed_minutes: number;
}

export interface PanelTag {
  id: number;
  name: string;
  category: string;
}

export interface PanelProfileData {
  email: string;
  session_token: string;
  first_name?: string;
  age_range?: string;
  gender?: string;
  country?: string;
  city?: string;
  education?: string;
  employment_status?: string;
  job_function?: string;
  seniority?: string;
  industry?: string;
  company_size?: string;
  preferred_language?: string;
  panel_consent: boolean;
  tag_ids: number[];
}

export interface VerifyTokenResponse {
  session_token: string;
  link_token: string;
  email: string;
  /** True when a returning participant already has a complete panel profile —
   *  the frontend skips the profiling questionnaire when set. */
  profile_complete?: boolean;
  first_name?: string | null;
  preferred_language?: string | null;
}

export async function getInterviewInfo(token: string): Promise<InterviewInfo> {
  const { data } = await client.get<InterviewInfo>(`/interview/${token}`);
  return data;
}

export async function getDemoLink(): Promise<{ redirect_token: string }> {
  const { data } = await client.get<{ redirect_token: string }>("/interview/demo");
  return data;
}

export interface StartInterviewParams {
  displayName?: string;
  profession?: string;
  ageRange?: string;
  country?: string;
  email?: string;
  sessionToken?: string;
  preferredLanguage?: string;
}

export async function startInterview(
  token: string,
  params: StartInterviewParams = {}
): Promise<StartInterviewResponse> {
  const { data } = await client.post<StartInterviewResponse>(
    `/interview/${token}/start`,
    {
      display_name: params.displayName || undefined,
      profession: params.profession || undefined,
      age_range: params.ageRange || undefined,
      country: params.country || undefined,
      email: params.email || undefined,
      session_token: params.sessionToken || undefined,
      preferred_language: params.preferredLanguage || undefined,
    }
  );
  return data;
}

export async function getScreeningQuestions(token: string, lang?: string): Promise<ScreeningQuestion[]> {
  const { data } = await client.get<ScreeningQuestion[]>(
    `/interview/${token}/screening-questions`,
    { params: lang ? { lang } : undefined }
  );
  return data;
}

export async function submitScreening(token: string, answers: Record<string, string>): Promise<ScreenResult> {
  const { data } = await client.post<ScreenResult>(`/interview/${token}/screen`, { answers });
  return data;
}

const MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024;

export async function submitAudio(
  token: string,
  participantId: string,
  audioBlob: Blob
): Promise<SubmitAudioResponse> {
  if (audioBlob.size > MAX_AUDIO_UPLOAD_BYTES) {
    throw new Error("Recording is too large. Please try a shorter response.");
  }
  const form = new FormData();
  const ext = audioBlob.type.includes("mp4") ? "mp4" : audioBlob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audioBlob, `recording.${ext}`);
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/respond`,
    form,
    { headers: { "Content-Type": "multipart/form-data" }, timeout: 90_000 }
  );
  return data;
}

export async function checkResume(token: string, email: string): Promise<ResumeCheck> {
  const { data } = await client.post<ResumeCheck>(`/interview/${token}/resume`, { email });
  return data;
}

export async function getResumeSummary(token: string, participantId: string): Promise<ResumeSummary> {
  const { data } = await client.get<ResumeSummary>(`/interview/${token}/${participantId}/resume-summary`);
  return data;
}

export async function skipQuestion(
  token: string,
  participantId: string
): Promise<SubmitAudioResponse> {
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/skip`
  );
  return data;
}

export async function requestVerification(
  linkToken: string,
  email: string,
  lang?: string
): Promise<void> {
  await client.post(`/interview/${linkToken}/request-verification`, { email, lang });
}

export async function verifyInterviewToken(magicToken: string): Promise<VerifyTokenResponse> {
  const { data } = await client.get<VerifyTokenResponse>(`/interview/verify/${magicToken}`);
  return data;
}

export async function getPanelTags(): Promise<PanelTag[]> {
  const { data } = await client.get<PanelTag[]>("/interview/panel-tags");
  return data;
}

export async function savePanelProfile(
  linkToken: string,
  profile: PanelProfileData
): Promise<{ saved: boolean }> {
  const { data } = await client.post<{ saved: boolean }>(
    `/interview/${linkToken}/panel-profile`,
    profile
  );
  return data;
}
