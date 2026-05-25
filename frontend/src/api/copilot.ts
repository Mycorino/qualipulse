import client from "./client";
import type { QuestionType } from "./surveys";

/**
 * Research Copilot API client — mirrors backend/app/routers/copilot.py.
 *
 * The copilot runs on two surfaces — surveys and interview-guide projects.
 * The endpoint functions are generic over the instrument; each page builds
 * a `CopilotTarget` and hands it to <ResearchCopilotPanel>.
 *
 * The API is stateless: the panel holds the chat thread and sends the full
 * message history each turn. Per-workspace/study/instrument memory and the
 * persisted conversation are the only server-side state.
 */

export type CopilotInstrument = "surveys" | "projects";

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

/** A survey question the copilot proposes. */
export interface ProposedSurveyQuestion {
  type: QuestionType;
  prompt: string;
  config: Record<string, unknown>;
  rationale: string;
}

/** An interview-guide question the copilot proposes. */
export interface ProposedGuideQuestion {
  section_title: string;
  main_question: string;
  desired_learning: string;
  rationale: string;
}

/**
 * A change the copilot proposes. Intent only — nothing is applied until the
 * researcher accepts it. `type` discriminates survey vs interview-guide
 * actions and add/edit/remove.
 */
export interface ProposedAction {
  type:
    | "add_question"
    | "edit_question"
    | "remove_question"
    | "add_guide_question"
    | "edit_guide_question"
    | "remove_guide_question"
    | "edit_objective"
    | "run_analysis"
    | "refine_analysis"
    | "create_first_study"
    | "create_research_plan"
    | "suggest_replies"
    | "request_website"
    | "propose_participant_demo";
  /** add_question / add_guide_question */
  question?: ProposedSurveyQuestion | ProposedGuideQuestion;
  /** edit / remove */
  question_id?: string;
  /** survey edit_question */
  new_prompt?: string;
  new_config?: Record<string, unknown>;
  /** interview edit_guide_question */
  new_main_question?: string;
  new_desired_learning?: string;
  /** edit_objective */
  new_objective?: string;
  /** create_first_study (onboarding) */
  study_name?: string;
  objective?: string;
  questions?: ProposedGuideQuestion[];
  rationale?: string;
  /** Suggested participant count scaled to the captured company_size. */
  recommended_participants?: number;
  /** Strategic context captured during the V2 onboarding chat — written
   *  through to the Project on accept so downstream personalisation
   *  (analysis, lifecycle emails, plan recommendation) can tie back. */
  decision_to_inform?: string;
  timeline?: string;
  success_criteria?: string;
  target_customer_description?: string;
  /** suggest_replies (onboarding) */
  options?: string[];
  context?: string;
  /** request_website (onboarding) */
  prompt?: string;
  /** propose_participant_demo (onboarding) — lead-in text shown in
   *  the chat above the demo card. */
  intro?: string;
  /** create_research_plan (Wave E) — multi-step plan card. */
  plan_name?: string;
  steps?: Array<{
    order_index: number;
    method: string;
    title: string;
    purpose?: string;
    deliverable?: string;
    n_participants?: number | null;
    duration_weeks?: number | null;
  }>;
}

/** Result of POST /onboarding/research-plan — Wave E. */
export interface ResearchPlanCreated {
  plan_id: string;
  project_id: string | null;
  study_name: string | null;
  interview_token: string | null;
}

export async function createResearchPlan(payload: {
  plan_name: string;
  rationale: string;
  steps: Array<{
    order_index: number;
    method: string;
    title: string;
    purpose?: string;
    deliverable?: string;
    n_participants?: number | null;
    duration_weeks?: number | null;
  }>;
  decision_to_inform?: string;
  timeline?: string;
  success_criteria?: string;
  target_customer_description?: string;
  language?: string;
}): Promise<ResearchPlanCreated> {
  const resp = await client.post<ResearchPlanCreated>(
    "/onboarding/research-plan",
    payload,
  );
  return resp.data;
}

export interface CopilotResponse {
  reply: string;
  proposed_actions: ProposedAction[];
  memory_updated: boolean;
}

/**
 * Live-stream callbacks the panel passes through `target.runTurn` so the
 * agent's progress narration (`onStatus`) and reply text (`onDelta`)
 * appear in the UI as they arrive — instead of the user staring at a
 * spinner for 30-90s. Omit them for a buffered call (test code etc.).
 */
export interface CopilotStreamHandlers {
  onStatus?: (label: string) => void;
  onDelta?: (text: string) => void;
}

/**
 * Everything <ResearchCopilotPanel> needs to talk to one surface. Each host
 * page (survey editor, interview project) builds one of these.
 */
export interface ConversationSnapshot {
  thread: unknown[];
  version: number;
}

export interface CopilotTarget {
  /** Stable id of the instrument — used as the panel's reload key. */
  id: string;
  runTurn: (
    messages: CopilotMessage[],
    handlers?: CopilotStreamHandlers,
  ) => Promise<CopilotResponse>;
  loadConversation: () => Promise<ConversationSnapshot>;
  saveConversation: (thread: unknown[], version: number) => Promise<number>;
  /** Apply an accepted proposal via the real instrument API. */
  applyAction: (action: ProposedAction) => Promise<void>;
}

/** Idle stream timeout — abort if the server stops emitting for this long.
 *  90s to accommodate Opus 4.7 adaptive thinking on complex tool-use chains. */
const STREAM_IDLE_MS = 90_000;

/**
 * POST a copilot request and consume the SSE stream. Status + delta
 * events fire through `handlers`; the `done` payload is returned (and is
 * the authoritative final state).
 *
 * Raw `fetch` (not axios) so the response body can be streamed. The
 * client-level Authorization interceptor is bypassed; the token is
 * read straight from localStorage here.
 */
async function streamCopilot(
  path: string,
  body: object,
  handlers?: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  // Per-chunk idle timeout — reset on every read so a slow stream is
  // fine, but a stalled one (network drop, server hung) aborts.
  const controller = new AbortController();
  let idleTimer: ReturnType<typeof setTimeout> = setTimeout(
    () => controller.abort(),
    STREAM_IDLE_MS,
  );
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), STREAM_IDLE_MS);
  };

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(idleTimer);
    throw err;
  }
  if (!response.ok || !response.body) {
    clearTimeout(idleTimer);
    throw new Error(`Copilot HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: CopilotResponse | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      resetIdle();
      buffer += decoder.decode(value, { stream: true });
      let split: number;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        if (!frame.startsWith("data: ")) continue;
        let event: { type: string; [k: string]: unknown };
        try {
          event = JSON.parse(frame.slice(6));
        } catch {
          console.warn("[copilot] Failed to parse SSE frame:", frame.slice(6));
          continue;
        }
        if (event.type === "status" && handlers?.onStatus) {
          handlers.onStatus(event.label as string);
        } else if (event.type === "delta" && handlers?.onDelta) {
          handlers.onDelta(event.text as string);
        } else if (event.type === "done") {
          final = {
            reply: (event.reply as string) ?? "",
            proposed_actions:
              (event.proposed_actions as ProposedAction[]) ?? [],
            memory_updated: Boolean(event.memory_updated),
          };
        }
      }
    }
  } finally {
    clearTimeout(idleTimer);
    reader.releaseLock();
  }

  if (!final) throw new Error("Copilot stream ended without a 'done' event");
  return final;
}

export async function runCopilot(
  instrument: CopilotInstrument,
  id: string,
  messages: CopilotMessage[],
  /** The tab/section the researcher is currently viewing, if any — lets
   *  the copilot tailor its help to where they sit. */
  activeSection?: string,
  /** The one-line job the copilot is helping with on this surface. */
  mission?: string,
  handlers?: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  return streamCopilot(
    `/${instrument}/${id}/copilot`,
    { messages, active_section: activeSection, mission },
    handlers,
  );
}

/**
 * Onboarding copilot — the new researcher's first conversation. No
 * instrument id: the surface is the workspace itself.
 */
export async function runOnboardingCopilot(
  messages: CopilotMessage[],
  handlers?: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  return streamCopilot("/onboarding/copilot", { messages }, handlers);
}

/** The memory the copilot wrote during onboarding — for the completion recap. */
export interface OnboardingMemory {
  /** Free-form notes the agent wrote via the `remember` tool. */
  memory: string;
  /** Deterministic sentence built server-side from the captured profile
   *  fields. Empty if nothing was captured. */
  profile_summary: string;
}

/**
 * Wave A Fix 4 — fetch the persisted onboarding conversation thread so
 * Welcome.tsx can hydrate prior turns on mount instead of losing them
 * to a router round-trip. Shape mirrors `getConversation` but the
 * onboarding endpoint lives at a fixed (no-id) path because the
 * instrument is the workspace itself.
 */
export async function getOnboardingConversation(): Promise<ConversationSnapshot> {
  const resp = await client.get<{ thread: unknown[]; version: number }>(
    "/onboarding/copilot/conversation",
  );
  return { thread: resp.data.thread ?? [], version: resp.data.version ?? 0 };
}

export async function saveOnboardingConversation(
  thread: unknown[],
  version: number,
): Promise<number> {
  const resp = await client.put<{ version: number }>(
    "/onboarding/copilot/conversation",
    { thread, version },
  );
  return resp.data.version ?? version;
}

export async function getOnboardingMemory(): Promise<OnboardingMemory> {
  const resp = await client.get<OnboardingMemory>(
    "/onboarding/copilot/memory",
  );
  return {
    memory: resp.data.memory || "",
    profile_summary: resp.data.profile_summary || "",
  };
}

/** Backend-served demo bundle for the sample-study modal. Variant
 *  routes to the right industry-flavoured fixture; locale comes from
 *  the company's preferred_language server-side. */
export interface DemoBundleExample {
  name: string;
  objective: string;
  q1_section: string;
  q1_question: string;
  q2_section: string;
  q2_question: string;
  q3_section: string;
  q3_question: string;
}
export interface DemoBundleTheme {
  title: string;
  finding: string;
  quote: string;
  speaker: string;
}
export interface DemoBundleQuote {
  speaker: string;
  text: string;
  highlight: string;
  code: string;
  code_color: string;
}
export interface DemoBundle {
  variant: string;
  locale: string;
  n_participants: number;
  completed_label: string;
  example: DemoBundleExample;
  themes: DemoBundleTheme[];
  quotes: DemoBundleQuote[];
}

export async function getDemoBundle(
  variant: "saas" | "b2b_specifier" | "consumer",
): Promise<DemoBundle | null> {
  try {
    const resp = await client.get<DemoBundle>(
      "/onboarding/demo-bundle",
      { params: { variant } },
    );
    return resp.data;
  } catch {
    return null;
  }
}

/** Return a Haiku-personalised mid-conversation opening question for
 *  the participant-demo modal — sounds like turn 2 of a real research
 *  conversation, referencing the researcher's captured context.
 *  Returns null when the wizard wasn't completed enough to generate
 *  a sensible question — caller falls back to the static i18n
 *  question. */
export async function getDemoOpeningQuestion(): Promise<string | null> {
  try {
    const resp = await client.get<{ question: string | null }>(
      "/onboarding/copilot/demo-opening-question",
    );
    return resp.data.question || null;
  } catch {
    return null;
  }
}

/** Trigger or fetch the cached personalised /welcome greeting generated
 *  by Haiku from the wizard-captured profile. Returns null when we
 *  can't generate (sparse profile, API failure) — caller falls back
 *  to the static i18n greeting. */
export async function prepWelcomeGreeting(): Promise<string | null> {
  try {
    const resp = await client.post<{ greeting: string | null }>(
      "/onboarding/copilot/greeting-prep",
    );
    return resp.data.greeting || null;
  } catch {
    return null;
  }
}

/** Fetch the 3 personalised starter-question chips. Returns null when
 *  the backend can't generate (sparse profile or API failure) — caller
 *  falls back to the static i18n `goal_suggestions` list. */
export async function getStarterSuggestions(): Promise<string[] | null> {
  try {
    const resp = await client.get<{ suggestions: string[] | null }>(
      "/onboarding/copilot/starter-suggestions",
    );
    return resp.data.suggestions && resp.data.suggestions.length === 3
      ? resp.data.suggestions
      : null;
  } catch {
    return null;
  }
}

/** V3 participant-experience demo response. */
export interface DemoTranscribeResponse {
  transcript: string;
  highlight: { start: number; end: number; text: string } | null;
  code: { label: string; color: string };
}

/** Send the user's demo recording for Whisper transcription + light
 *  keyword coding. Preview only — nothing persists. */
export async function transcribeDemoAudio(
  audio: Blob,
): Promise<DemoTranscribeResponse> {
  const form = new FormData();
  // Whisper picks up the extension from the filename — pass through
  // whatever the recorder gave us (webm on Chrome, m4a on Safari).
  const filename = audio.type.includes("mp4")
    ? "demo.m4a"
    : audio.type.includes("ogg")
      ? "demo.ogg"
      : "demo.webm";
  form.append("audio", audio, filename);
  const resp = await client.post<DemoTranscribeResponse>(
    "/onboarding/demo-interview/transcribe",
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    },
  );
  return resp.data;
}

export async function getConversation(
  instrument: CopilotInstrument,
  id: string,
): Promise<ConversationSnapshot> {
  const resp = await client.get<{ thread: unknown[]; version: number }>(
    `/${instrument}/${id}/copilot/conversation`,
  );
  return { thread: resp.data.thread ?? [], version: resp.data.version ?? 0 };
}

export async function saveConversation(
  instrument: CopilotInstrument,
  id: string,
  thread: unknown[],
  version: number,
): Promise<number> {
  const resp = await client.put<{ version: number }>(
    `/${instrument}/${id}/copilot/conversation`,
    { thread, version },
  );
  return resp.data.version ?? version;
}

export interface OnboardingStudyPayload {
  study_name: string;
  objective?: string;
  decision_to_inform?: string;
  timeline?: string;
  success_criteria?: string;
  target_customer_description?: string;
  questions: { section_title: string; main_question: string; desired_learning?: string }[];
  language: string;
}

export async function createOnboardingStudy(
  payload: OnboardingStudyPayload,
): Promise<{ project_id: string; study_name: string; interview_token: string }> {
  const resp = await client.post<{
    project_id: string;
    study_name: string;
    interview_token: string;
  }>("/onboarding/study", payload);
  return resp.data;
}
