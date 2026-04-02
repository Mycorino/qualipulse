import client from "./client";

export interface InterviewInfo {
  project_name: string;
  language: string;
  welcome_message?: string;
  interview_duration_minutes?: number;
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
}

export async function getInterviewInfo(
  token: string
): Promise<InterviewInfo> {
  const { data } = await client.get<InterviewInfo>(
    `/interview/${token}`
  );
  return data;
}

export async function startInterview(
  token: string,
  displayName?: string
): Promise<StartInterviewResponse> {
  const { data } = await client.post<StartInterviewResponse>(
    `/interview/${token}/start`,
    { display_name: displayName || undefined }
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
