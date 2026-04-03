import client from "./client";

export interface InterviewInfo {
  project_name: string;
  language: string;
  welcome_message?: string;
  interview_duration_minutes?: number;
  question_count?: number;
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

export async function getInterviewInfo(
  token: string
): Promise<InterviewInfo> {
  const { data } = await client.get<InterviewInfo>(
    `/interview/${token}`
  );
  return data;
}

export interface StartInterviewParams {
  displayName?: string;
  profession?: string;
  ageRange?: string;
  country?: string;
  email?: string;
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
