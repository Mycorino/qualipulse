import client from "./client";
import type { ParticipantBranding } from "../utils/branding";

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
  /** Researcher-promised incentive, shown verbatim on the consent screen. */
  incentive_text?: string | null;
  panel_collection_enabled?: boolean;
  /** When true the socio-demographic questionnaire runs BEFORE the interview. */
  profile_before_interview?: boolean;
  /** Identity policy + theme. In "anonymous" mode the server already
   *  stripped company_name / researcher_name / researcher_logo_url. */
  branding?: ParticipantBranding;
  /** "realtime_beta" switches the participant flow to the live-voice
   *  conversation (WebRTC). Anything else (or absent) is the classic loop. */
  interview_mode?: "classic" | "realtime_beta";
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
  /** Authoritative language the AI + voice are using; UI locks to this. */
  language?: string;
  /** Index of the pending interviewer turn the participant must answer. */
  turn_index?: number;
  /** Guide question index of the opening turn (<0 = non-counting turn). */
  question_index?: number;
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
  /** The NEW pending turn to answer (on completion: the last turn). The
   *  client echoes it back on the next /respond or /skip so a retried
   *  upload can never be applied to the wrong question. */
  turn_index?: number;
}

/** Body of the HTTP 409 `turn_mismatch` error from /respond or /skip. */
export interface TurnMismatchDetail {
  code: "turn_mismatch";
  current: SubmitAudioResponse;
}

export interface ParticipantProfileUpdate {
  display_name?: string;
  age_range?: string;
  country?: string;
  profession?: string;
  email?: string;
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
  /** Authoritative interview language; UI re-locks to this on resume. */
  language?: string;
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
  /** Whether this email is already on the research panel. */
  panel_consent?: boolean;
  first_name?: string | null;
  preferred_language?: string | null;
}

export async function getInterviewInfo(token: string, lang?: string): Promise<InterviewInfo> {
  const { data } = await client.get<InterviewInfo>(`/interview/${token}`, {
    params: lang ? { lang } : undefined,
  });
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
  /** Screener answers (question_id → canonical option value) carried from the screening phase. */
  screeningAnswers?: Record<string, string>;
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
      screening_answers:
        params.screeningAnswers && Object.keys(params.screeningAnswers).length > 0
          ? params.screeningAnswers
          : undefined,
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

/** Stable sentinel for the client-side size guard; the UI maps it to a
 *  localized "recording too long" message instead of a connection error. */
export const RECORDING_TOO_LARGE = "RECORDING_TOO_LARGE";

/**
 * Submit a participant answer. Accepts either a recorded audio Blob (the
 * default voice path) or a typed string (accessibility fallback for
 * participants without a working microphone) — the backend requires exactly
 * one of the two.
 */
export async function submitAudio(
  token: string,
  participantId: string,
  answer: Blob | string,
  turnIndex?: number | null
): Promise<SubmitAudioResponse> {
  const form = new FormData();
  if (typeof answer === "string") {
    form.append("text", answer);
  } else {
    if (answer.size > MAX_AUDIO_UPLOAD_BYTES) {
      const err = new Error(RECORDING_TOO_LARGE) as Error & { code?: string };
      err.code = RECORDING_TOO_LARGE;
      throw err;
    }
    const ext = answer.type.includes("mp4") ? "mp4" : answer.type.includes("ogg") ? "ogg" : "webm";
    form.append("audio", answer, `recording.${ext}`);
  }
  if (turnIndex !== undefined && turnIndex !== null) {
    form.append("turn_index", String(turnIndex));
  }
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/respond`,
    form,
    { headers: { "Content-Type": "multipart/form-data" }, timeout: 90_000 }
  );
  return data;
}

export async function checkResume(
  token: string,
  email: string,
  sessionToken?: string | null
): Promise<ResumeCheck> {
  const { data } = await client.post<ResumeCheck>(`/interview/${token}/resume`, {
    email,
    session_token: sessionToken || undefined,
  });
  return data;
}

export async function getResumeSummary(token: string, participantId: string): Promise<ResumeSummary> {
  const { data } = await client.get<ResumeSummary>(`/interview/${token}/${participantId}/resume-summary`);
  return data;
}

export interface HandoffCreate {
  handoff_token: string;
  expires_in_seconds: number;
}

export interface HandoffClaim {
  participant_id: string;
  last_question: string | null;
  turn_count: number;
  question_index: number;
  email: string | null;
  session_token: string | null;
}

/** Mint a continue-on-another-device token for an in-progress interview. */
export async function createHandoff(token: string, participantId: string): Promise<HandoffCreate> {
  const { data } = await client.post<HandoffCreate>(`/interview/${token}/${participantId}/handoff`);
  return data;
}

/** Adopt an in-progress interview on this device via a handoff token. */
export async function claimHandoff(token: string, handoffToken: string): Promise<HandoffClaim> {
  const { data } = await client.post<HandoffClaim>(`/interview/${token}/handoff/claim`, {
    handoff_token: handoffToken,
  });
  return data;
}

export async function skipQuestion(
  token: string,
  participantId: string,
  turnIndex?: number | null
): Promise<SubmitAudioResponse> {
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/skip`,
    turnIndex !== undefined && turnIndex !== null ? { turn_index: turnIndex } : {}
  );
  return data;
}

/** "Finish here": closes the interview early. Idempotent; the response is a
 *  completed TurnResponse whose question_text is the spoken closing line. */
export async function finishInterview(
  token: string,
  participantId: string
): Promise<SubmitAudioResponse> {
  const { data } = await client.post<SubmitAudioResponse>(
    `/interview/${token}/${participantId}/finish`,
    {}
  );
  return data;
}

/** Post-interview demographics for participants WITHOUT a magic-link session.
 *  (Magic-link participants keep using savePanelProfile, the only path that
 *  can record panel consent.) */
export async function updateParticipantProfile(
  token: string,
  participantId: string,
  profile: ParticipantProfileUpdate
): Promise<{ saved: boolean }> {
  const { data } = await client.patch<{ saved: boolean }>(
    `/interview/${token}/${participantId}/profile`,
    profile
  );
  return data;
}

/** Deferred voice synthesis (item 13): /start, /respond, /skip and /finish
 *  usually return tts_audio_url: null so the question TEXT renders ~2s
 *  sooner. This endpoint synthesises the voice for a turn on first call and
 *  returns the stored URL on later calls (idempotent). `null` = synthesis
 *  genuinely failed; the interview stays text-only. */
export async function getTurnAudio(
  token: string,
  participantId: string,
  turnIndex: number
): Promise<string | null> {
  const { data } = await client.get<{ tts_audio_url: string | null }>(
    `/interview/${token}/${participantId}/turn-audio`,
    { params: { turn_index: turnIndex }, timeout: 30_000 }
  );
  return data.tts_audio_url ?? null;
}

export async function requestVerification(
  linkToken: string,
  email: string,
  lang?: string
): Promise<void> {
  await client.post(`/interview/${linkToken}/request-verification`, { email, lang });
}

/**
 * Exchange the six-digit code from the verification email for a session.
 *
 * The OTP twin of `verifyInterviewToken`: it returns the identical shape, so
 * callers can treat the two routes interchangeably. This is the route that
 * keeps a participant in the tab they already opened (and already granted the
 * microphone to) instead of bouncing them into the mail app's browser.
 *
 * Errors carry a structured `detail: { code, message }`:
 *   400 code_invalid / code_expired, 429 too_many_attempts.
 */
export async function verifyInterviewCode(
  linkToken: string,
  email: string,
  code: string
): Promise<VerifyTokenResponse> {
  const { data } = await client.post<VerifyTokenResponse>(
    `/interview/${linkToken}/verify-code`,
    { email, code }
  );
  return data;
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

// ── Realtime interview beta ────────────────────────────────────────────────

export interface InterviewStatus {
  participant_id: string;
  status: "in_progress" | "completed";
  turn_count: number;
  last_question: string | null;
  question_index: number | null;
  is_follow_up: boolean;
  language: string;
  started_at: string | null;
  completed_at: string | null;
}

export async function getInterviewStatus(
  token: string,
  participantId: string
): Promise<InterviewStatus> {
  const { data } = await client.get<InterviewStatus>(
    `/interview/${token}/${participantId}/status`
  );
  return data;
}

export interface RealtimeSession {
  sdp: string;
  /** The session's turn_detection config, needed to restore VAD after a
   *  mic pause (pause = session.update turn_detection null). */
  turnDetection: unknown | null;
}

/** WebRTC signaling: POST the browser's SDP offer, get OpenAI's SDP answer.
 *  The backend proxies the exchange and attaches its sideband bridge, so the
 *  client never sees an API key. */
export async function createRealtimeSession(
  token: string,
  participantId: string,
  sdpOffer: string
): Promise<RealtimeSession> {
  const res = await client.post<string>(
    `/interview/${token}/${participantId}/realtime/sdp`,
    sdpOffer,
    {
      headers: { "Content-Type": "application/sdp" },
      responseType: "text",
      // Axios would JSON.parse a text body by default; keep it verbatim.
      transformResponse: [(d) => d],
      timeout: 30_000,
    }
  );
  let turnDetection: unknown | null = null;
  try {
    const raw = res.headers["x-realtime-turn-detection"];
    if (raw) turnDetection = JSON.parse(String(raw));
  } catch { /* header optional */ }
  return { sdp: res.data, turnDetection };
}

/** Upload the parallel full-session recording (mic + interviewer voice). */
export async function uploadSessionRecording(
  token: string,
  participantId: string,
  blob: Blob
): Promise<{ session_recording_url: string }> {
  const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", blob, `session.${ext}`);
  const { data } = await client.post<{ session_recording_url: string }>(
    `/interview/${token}/${participantId}/realtime/recording`,
    form,
    { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 }
  );
  return data;
}
