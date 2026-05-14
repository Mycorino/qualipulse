import client from "./client";

/* ── Types ──────────────────────────────────────────────────────────── */

export type QuestionType =
  | "likert"
  | "mc_single"
  | "mc_multi"
  | "nps"
  | "open_text"
  | "short_text";

export type SurveyRole = "screener" | "validation" | "standalone";
export type SurveyStatus = "draft" | "live" | "closed";

export interface Survey {
  id: string;
  study_id: string;
  company_id: string;
  name: string;
  description: string | null;
  role: SurveyRole;
  status: SurveyStatus;
  fielding_started_at: string | null;
  fielding_ended_at: string | null;
  created_at: string;
  archived_at: string | null;
  question_count: number;
  response_count: number;
  completed_count: number;
}

export interface QuestionConfigChoice {
  id: string;
  label: string;
}

export interface SurveyQuestion {
  id: string;
  survey_id: string;
  sort_order: number;
  type: QuestionType;
  prompt: string;
  is_required: boolean;
  config: Record<string, unknown>;
  created_at: string;
  deprecated_at: string | null;
}

export interface SurveyLink {
  id: string;
  survey_id: string;
  token: string;
  is_active: boolean;
  is_anonymous: boolean;
  target_n: number | null;
  response_cap: number | null;
  opens_at: string | null;
  closes_at: string | null;
  created_at: string;
}

/* ── Survey CRUD ───────────────────────────────────────────────────── */

export async function listSurveys(): Promise<Survey[]> {
  const resp = await client.get<Survey[]>("/surveys/");
  return resp.data;
}

export async function getSurvey(id: string): Promise<Survey> {
  const resp = await client.get<Survey>(`/surveys/${id}`);
  return resp.data;
}

export async function createSurvey(payload: {
  name: string;
  description?: string;
  role?: SurveyRole;
  study_id?: string;
}): Promise<Survey> {
  const resp = await client.post<Survey>("/surveys/", payload);
  return resp.data;
}

export async function patchSurvey(
  id: string,
  payload: Partial<Pick<Survey, "name" | "description" | "role" | "status">>,
): Promise<Survey> {
  const resp = await client.patch<Survey>(`/surveys/${id}`, payload);
  return resp.data;
}

export async function archiveSurvey(id: string): Promise<void> {
  await client.delete(`/surveys/${id}`);
}

/* ── Question CRUD ─────────────────────────────────────────────────── */

export async function listQuestions(surveyId: string): Promise<SurveyQuestion[]> {
  const resp = await client.get<SurveyQuestion[]>(
    `/surveys/${surveyId}/questions`,
  );
  return resp.data;
}

export async function createQuestion(
  surveyId: string,
  payload: {
    type: QuestionType;
    prompt: string;
    is_required?: boolean;
    sort_order?: number;
    config: Record<string, unknown>;
  },
): Promise<SurveyQuestion> {
  const resp = await client.post<SurveyQuestion>(
    `/surveys/${surveyId}/questions`,
    payload,
  );
  return resp.data;
}

export async function patchQuestion(
  surveyId: string,
  questionId: string,
  payload: Partial<{
    prompt: string;
    is_required: boolean;
    sort_order: number;
    config: Record<string, unknown>;
  }>,
): Promise<SurveyQuestion> {
  const resp = await client.patch<SurveyQuestion>(
    `/surveys/${surveyId}/questions/${questionId}`,
    payload,
  );
  return resp.data;
}

export async function deprecateQuestion(
  surveyId: string,
  questionId: string,
): Promise<void> {
  await client.delete(`/surveys/${surveyId}/questions/${questionId}`);
}

/* ── Survey link ───────────────────────────────────────────────────── */

export async function createLink(
  surveyId: string,
  payload: {
    is_anonymous?: boolean;
    target_n?: number;
    response_cap?: number;
  } = {},
): Promise<SurveyLink> {
  const resp = await client.post<SurveyLink>(`/surveys/${surveyId}/links`, payload);
  return resp.data;
}

export async function listLinks(surveyId: string): Promise<SurveyLink[]> {
  const resp = await client.get<SurveyLink[]>(`/surveys/${surveyId}/links`);
  return resp.data;
}

/* ── Default config helpers (used by the editor when adding a question) */

export function defaultConfigForType(type: QuestionType): Record<string, unknown> {
  switch (type) {
    case "likert":
      return { scale: 5, anchors: ["Strongly disagree", "Strongly agree"], reverse_coded: false };
    case "mc_single":
      return {
        choices: [
          { id: "a", label: "Option A" },
          { id: "b", label: "Option B" },
        ],
        randomize: true,
        has_other: false,
      };
    case "mc_multi":
      return {
        choices: [
          { id: "a", label: "Option A" },
          { id: "b", label: "Option B" },
        ],
        randomize: true,
        has_other: false,
        max_selectable: null,
      };
    case "nps":
      return { context: "" };
    case "open_text":
      return { max_chars: 500, ai_cluster: false };
    case "short_text":
      return { max_chars: 120 };
  }
}
