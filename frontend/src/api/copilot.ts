import client from "./client";
import type { QuestionType } from "./surveys";

/**
 * Research Copilot API client — mirrors backend/app/routers/copilot.py.
 *
 * The copilot runs on two surfaces — surveys and interview-guide projects.
 * The endpoint functions are generic over the instrument; each page builds
 * a `CopilotTarget` and hands it to <ResearchCopilotPanel>.
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

/** A screening question the copilot proposes (runs before the interview). */
export interface ProposedScreeningQuestion {
  question: string;
  options: string[];
  disqualifying_options: string[];
  rationale?: string;
}

/** A settings change the copilot proposes for this interview round. */
export interface ProposedSettings {
  interview_duration_minutes?: number;
  target_participants?: number;
  warmup_enabled?: boolean;
}

/**
 * A change the copilot proposes. Intent only — nothing is applied until the
 * researcher accepts it.
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
    | "edit_settings"
    | "add_screening_question"
    | "suggest_replies"
    | "run_analysis"
    | "refine_analysis";
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
  /** edit_settings */
  settings?: ProposedSettings;
  /** add_screening_question */
  screening?: ProposedScreeningQuestion;
  /** suggest_replies — clickable answer chips for a clarifying question */
  question_text?: string;
  options?: string[];
  context?: string;
  rationale?: string;
}

export interface CopilotResponse {
  reply: string;
  proposed_actions: ProposedAction[];
  memory_updated: boolean;
  /** Set by the backend when the reply is an error fallback, so the
   * panel can offer a retry instead of treating it as a normal turn. */
  error?: boolean;
}

export interface CopilotStreamHandlers {
  onStatus?: (label: string) => void;
  onDelta?: (text: string) => void;
  /** Abort the stream (Stop button, unmount, navigating away). The
   * promise rejects with an AbortError-named Error. */
  signal?: AbortSignal;
}

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

const STREAM_IDLE_MS = 90_000;

/** Refresh the access token once, mirroring the axios interceptor. The
 * SSE path uses raw fetch (axios buffers, unusable for streams), so it
 * must handle its own 401 — otherwise an overnight tab hard-fails until
 * some unrelated axios call happens to refresh. */
async function refreshAccessToken(): Promise<string | null> {
  const storedRefreshToken = localStorage.getItem("refresh_token");
  if (!storedRefreshToken) return null;
  try {
    const resp = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: storedRefreshToken }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.access_token) {
      localStorage.setItem("token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("refresh_token", data.refresh_token);
      }
      return data.access_token as string;
    }
  } catch {
    // fall through
  }
  return null;
}

async function streamCopilot(
  path: string,
  body: object,
  handlers?: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  const baseUrl = (client.defaults.baseURL ?? "").replace(/\/+$/, "");
  const url = `${baseUrl}${path}`;
  const payload = JSON.stringify(body);

  // One controller drives everything: the caller's Stop/unmount signal,
  // the idle timeout, and fetch/reader teardown. Without it, a timed-out
  // stream left the HTTP connection (and the server generator) running.
  const controller = new AbortController();
  const externalSignal = handlers?.signal;
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let idleTimedOut = false;
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      idleTimedOut = true;
      controller.abort();
    }, STREAM_IDLE_MS);
  };

  const doFetch = (token: string | null) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return fetch(url, {
      method: "POST",
      headers,
      body: payload,
      signal: controller.signal,
    });
  };

  try {
    let resp = await doFetch(localStorage.getItem("token"));
    if (resp.status === 401) {
      const fresh = await refreshAccessToken();
      if (fresh) resp = await doFetch(fresh);
    }

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Copilot request failed (${resp.status}): ${text}`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: CopilotResponse | null = null;

    try {
      resetIdle();
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        resetIdle();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "status" && handlers?.onStatus) {
              handlers.onStatus(event.label ?? "");
            } else if (event.type === "delta" && handlers?.onDelta) {
              handlers.onDelta(event.text ?? "");
            } else if (event.type === "done") {
              result = {
                reply: event.reply ?? "",
                proposed_actions: event.proposed_actions ?? [],
                memory_updated: event.memory_updated ?? false,
                error: event.error === true,
              };
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    } finally {
      // Release the connection whatever happened — a thrown timeout used
      // to leave the server streaming to nobody.
      try {
        await reader.cancel();
      } catch {
        // already closed
      }
    }

    if (!result) throw new Error("Stream ended without a done event");
    return result;
  } catch (err) {
    if (idleTimedOut) throw new Error("Stream idle timeout");
    throw err;
  } finally {
    clearTimeout(idleTimer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
}

export async function runCopilot(
  instrument: CopilotInstrument,
  id: string,
  messages: CopilotMessage[],
  activeSection?: string,
  mission?: string,
  handlers?: CopilotStreamHandlers,
): Promise<CopilotResponse> {
  return streamCopilot(
    `/${instrument}/${id}/copilot`,
    { messages, active_section: activeSection, mission },
    handlers,
  );
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
