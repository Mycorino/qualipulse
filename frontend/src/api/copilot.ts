import client from "./client";
import type { QuestionType } from "./surveys";

/**
 * Research Copilot API client — mirrors backend/app/routers/copilot.py.
 *
 * The API is stateless: the panel holds the chat thread and sends the full
 * message history each turn. The copilot's per-workspace memory is the only
 * server-persisted state.
 */

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ProposedQuestion {
  type: QuestionType;
  prompt: string;
  config: Record<string, unknown>;
  rationale: string;
}

/**
 * A change the copilot proposes. Intent only — nothing is applied until the
 * researcher accepts it.
 */
export interface ProposedAction {
  type: "add_question" | "edit_question" | "remove_question";
  /** add_question */
  question?: ProposedQuestion;
  /** edit_question / remove_question */
  question_id?: string;
  /** edit_question */
  new_prompt?: string;
  new_config?: Record<string, unknown>;
  rationale?: string;
}

export interface CopilotResponse {
  reply: string;
  proposed_actions: ProposedAction[];
  memory_updated: boolean;
}

export async function runCopilot(
  surveyId: string,
  messages: CopilotMessage[],
): Promise<CopilotResponse> {
  const resp = await client.post<CopilotResponse>(
    `/surveys/${surveyId}/copilot`,
    { messages },
  );
  return resp.data;
}

/* ── Conversation persistence ─────────────────────────────────────────
 * The panel's chat thread is stored server-side per survey, so it
 * resumes when the researcher navigates away and back. `thread` is the
 * panel's own thread-item structure — opaque to the API layer.
 */

export async function getConversation(surveyId: string): Promise<unknown[]> {
  const resp = await client.get<{ thread: unknown[] }>(
    `/surveys/${surveyId}/copilot/conversation`,
  );
  return resp.data.thread ?? [];
}

export async function saveConversation(
  surveyId: string,
  thread: unknown[],
): Promise<void> {
  await client.put(`/surveys/${surveyId}/copilot/conversation`, { thread });
}
