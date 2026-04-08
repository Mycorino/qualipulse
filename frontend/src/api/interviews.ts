import client from "./client";

export interface InterviewInfo {
  project_name: string;
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

export interface ScreeningQuestion {
  id: string;
  question: string;
  options: string[];
  disqualifying_options: string[];
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
  panel_consent: boolean;
  tag_ids: number[];
}

export interface VerifyTokenResponse {
  session_token: string;
  link_token: string;
  email: string;
}

export async function getInterviewInfo(token: string): Promise<InterviewInfo> {
  const { data } = await client.get<InterviewInfo>(`/interview/${token}`);
  return data;
}

export interface StartInterviewParams {
  displayName?: string;
  profession?: string;
  ageRange?: string;
  country?: string;
  email?: string;
  sessionToken?: string;
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
    }
  );
  return data;
}

export async function getScreeningQuestions(token: string): Promise<ScreeningQuestion[]> {
  const { data } = await client.get<ScreeningQuestion[]>(`/interview/${token}/screening-questions`);
  return data;
}

export async function submitScreening(token: string, answers: Record<string, string>): Promise<ScreenResult> {
  const { data } = await client.post<ScreenResult>(`/interview/${token}/screen`, { answers });
  return data;
}

export async function submitAudio(
  token: string,
  participantId: string,
  audioBlob: Blob
): Promise<SubmitAudioResponse> {
  const form = new FormData();
  const ext = audioBlob.type.includes("mp4") ? "mp4" : audioBlob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audioBlob, `recording.${ext}`);
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/respond`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

export async function checkResume(token: string, email: string): Promise<ResumeCheck> {
  const { data } = await client.get<ResumeCheck>(`/interview/${token}/resume`, { params: { email } });
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

export async function requestVerification(linkToken: string, email: string): Promise<void> {
  await client.post(`/interview/${linkToken}/request-verification`, { email });
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
