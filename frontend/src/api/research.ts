import client from "./client";
import type { QuestionCreate } from "./projects";

export interface BriefSummary {
  summary: string;
}

export interface ObjectiveSuggestion {
  objective: string;
  learning_goals: string[];
  study_type: "exploratory" | "evaluative" | "generative";
  rationale: string;
}

export interface ScopeSuggestion {
  audience: string;
  duration_minutes: number;
  language: string;
  participant_count: number;
  audience_rationale: string;
}

export interface QuestionsSuggestion {
  questions: QuestionCreate[];
}

export async function parseBrief(
  context: string,
  files: File[]
): Promise<BriefSummary> {
  const form = new FormData();
  form.append("context", context);
  files.forEach((f) => form.append("files", f));
  const { data } = await client.post<BriefSummary>("/research/parse-brief", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function suggestObjective(
  context: string,
  briefSummary: string
): Promise<ObjectiveSuggestion> {
  const { data } = await client.post<ObjectiveSuggestion>(
    "/research/suggest-objective",
    { context, brief_summary: briefSummary }
  );
  return data;
}

export async function suggestScope(
  objective: string,
  learningGoals: string[],
  context: string
): Promise<ScopeSuggestion> {
  const { data } = await client.post<ScopeSuggestion>(
    "/research/suggest-scope",
    { objective, learning_goals: learningGoals, context }
  );
  return data;
}

export async function suggestQuestions(
  objective: string,
  learningGoals: string[],
  audience: string,
  durationMinutes: number,
  language: string,
  context: string
): Promise<QuestionsSuggestion> {
  const { data } = await client.post<QuestionsSuggestion>(
    "/research/suggest-questions",
    {
      objective,
      learning_goals: learningGoals,
      audience,
      duration_minutes: durationMinutes,
      language,
      context,
    }
  );
  return data;
}

// ---------------------------------------------------------------------------
// Recommended studies — the Dashboard "what should I research next?" card.
// ---------------------------------------------------------------------------

export interface RecommendedStudy {
  id: string;
  name: string;
  category: string;
  icon: string;
  description: string;
  best_for: string;
  duration_minutes: number;
  question_count: number;
  has_screening: boolean;
  reasons: string[];
  match_score: number;
}

export interface RecommendedStudiesResponse {
  recommendations: RecommendedStudy[];
  personalised: boolean;
}

export async function getRecommendedStudies(
  limit: number = 3
): Promise<RecommendedStudiesResponse> {
  const { data } = await client.get<RecommendedStudiesResponse>(
    "/research/recommended-studies",
    { params: { limit } }
  );
  return data;
}
