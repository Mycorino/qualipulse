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
    | "create_first_study";
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
}

export interface CopilotResponse {
  reply: string;
  proposed_actions: ProposedAction[];
  memory_updated: boolean;
}

/**
 * Everything <ResearchCopilotPanel> needs to talk to one surface. Each host
 * page (survey editor, interview project) builds one of these.
 */
export interface CopilotTarget {
  /** Stable id of the instrument — used as the panel's reload key. */
  id: string;
  runTurn: (messages: CopilotMessage[]) => Promise<CopilotResponse>;
  loadConversation: () => Promise<unknown[]>;
  saveConversation: (thread: unknown[]) => Promise<void>;
  /** Apply an accepted proposal via the real instrument API. */
  applyAction: (action: ProposedAction) => Promise<void>;
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
): Promise<CopilotResponse> {
  // A copilot turn runs an Opus 4.7 agent loop (adaptive thinking +
  // multiple tool-call iterations) and routinely takes 30-90s — well past
  // the axios client's 30s default. Give it a generous per-request
  // timeout so the panel waits for the real reply instead of aborting.
  const resp = await client.post<CopilotResponse>(
    `/${instrument}/${id}/copilot`,
    { messages, active_section: activeSection, mission },
    { timeout: 180000 },
  );
  return resp.data;
}

/**
 * Onboarding copilot — the new researcher's first conversation. No
 * instrument id: the surface is the workspace itself.
 */
export async function runOnboardingCopilot(
  messages: CopilotMessage[],
): Promise<CopilotResponse> {
  const resp = await client.post<CopilotResponse>(
    "/onboarding/copilot",
    { messages },
    { timeout: 180000 },
  );
  return resp.data;
}

/** The memory the copilot wrote during onboarding — for the completion recap. */
export async function getOnboardingMemory(): Promise<string> {
  const resp = await client.get<{ memory: string }>(
    "/onboarding/copilot/memory",
  );
  return resp.data.memory;
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
