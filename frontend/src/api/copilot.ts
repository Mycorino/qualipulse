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
    | "suggest_replies"
    | "request_website";
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
  /** suggest_replies (onboarding) */
  options?: string[];
  context?: string;
  /** request_website (onboarding) */
  prompt?: string;
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
export interface CopilotTarget {
  /** Stable id of the instrument — used as the panel's reload key. */
  id: string;
  runTurn: (
    messages: CopilotMessage[],
    handlers?: CopilotStreamHandlers,
  ) => Promise<CopilotResponse>;
  loadConversation: () => Promise<unknown[]>;
  saveConversation: (thread: unknown[]) => Promise<void>;
  /** Apply an accepted proposal via the real instrument API. */
  applyAction: (action: ProposedAction) => Promise<void>;
}

/** Idle stream timeout — abort if the server stops emitting for this long. */
const STREAM_IDLE_MS = 60_000;

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

export async function getOnboardingMemory(): Promise<OnboardingMemory> {
  const resp = await client.get<OnboardingMemory>(
    "/onboarding/copilot/memory",
  );
  return {
    memory: resp.data.memory || "",
    profile_summary: resp.data.profile_summary || "",
  };
}

export async function getConversation(
  instrument: CopilotInstrument,
  id: string,
): Promise<unknown[]> {
  const resp = await client.get<{ thread: unknown[] }>(
    `/${instrument}/${id}/copilot/conversation`,
  );
  return resp.data.thread ?? [];
}

export async function saveConversation(
  instrument: CopilotInstrument,
  id: string,
  thread: unknown[],
): Promise<void> {
  await client.put(`/${instrument}/${id}/copilot/conversation`, { thread });
}
