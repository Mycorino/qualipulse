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

// Per-question refinement. The entire point of this endpoint is that it
// is *scoped* — we send one question, we get one question back, and the
// sibling questions that go into the request are read-only context for
// coherence. The frontend keeps a snapshot of the pre-refine question so
// the researcher can undo if they dislike the refinement.
export interface RefinedQuestionResponse {
  refined: {
    section_title: string;
    main_question: string;
    interview_notes: string;
    desired_learning: string;
  };
  rationale: string;
}

export async function refineQuestion(params: {
  question: QuestionCreate;
  questionIndex: number;
  objective: string;
  learningGoals: string[];
  audience: string;
  allQuestions: QuestionCreate[];
  language: string;
  instruction?: string;
}): Promise<RefinedQuestionResponse> {
  const { data } = await client.post<RefinedQuestionResponse>(
    "/research/refine-question",
    {
      question: {
        section_title: params.question.section_title,
        main_question: params.question.main_question,
        interview_notes: params.question.interview_notes ?? "",
        desired_learning: params.question.desired_learning ?? "",
      },
      question_index: params.questionIndex,
      objective: params.objective,
      learning_goals: params.learningGoals,
      audience: params.audience,
      // Strip each sibling to only the fields the backend actually uses
      // for coherence. This keeps the request small and makes it obvious
      // at the wire level that we're not asking Claude to rewrite them.
      all_questions: params.allQuestions.map((q) => ({
        section_title: q.section_title,
        main_question: q.main_question,
      })),
      language: params.language,
      instruction: params.instruction,
    }
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
