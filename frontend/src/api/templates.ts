import client from "./client";

export interface TemplateSummary {
  id: string;
  name: string;
  category: string;
  icon: string;
  description: string;
  best_for: string;
  duration_minutes: number;
  question_count: number;
  has_screening: boolean;
}

export interface TemplateQuestion {
  section_index: number;
  section_title: string;
  question_index: number;
  main_question: string;
  interview_notes: string;
  desired_learning: string;
}

export interface TemplateScreeningQuestion {
  question: string;
  options: string[];
  disqualifying_options: string[];
}

export interface ProjectTemplate extends TemplateSummary {
  research_objective: string;
  target_audience: string;
  learning_goals: string[];
  questions: TemplateQuestion[];
  screening_questions: TemplateScreeningQuestion[];
}

export async function listTemplates(lang?: string): Promise<TemplateSummary[]> {
  const { data } = await client.get<{ templates: TemplateSummary[] }>("/templates", {
    params: lang ? { lang } : undefined,
  });
  return data.templates;
}

export async function getTemplate(id: string, lang?: string): Promise<ProjectTemplate> {
  const { data } = await client.get<ProjectTemplate>(`/templates/${id}`, {
    params: lang ? { lang } : undefined,
  });
  return data;
}
