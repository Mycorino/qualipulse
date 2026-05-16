import client from "./client";
import type { SurveyRole, SurveyStatus } from "./surveys";

/**
 * Studies API client — mirrors backend/app/routers/studies.py.
 *
 * The Study Overview page (Sprint 9.5) is the primary research-workspace
 * surface. Surveys and Projects live as instruments inside a Study.
 */

export interface ProjectMini {
  id: string;
  name: string;
  language: string;
  interview_link_count: number;
  completed_participant_count: number;
  in_progress_participant_count: number;
}

export interface SurveyMini {
  id: string;
  name: string;
  role: SurveyRole;
  status: SurveyStatus;
  question_count: number;
  response_count: number;
  completed_count: number;
}

export interface StudyProgress {
  has_live_survey: boolean;
  total_completed_responses: number;
  segments_identified_placeholder: boolean;
  interviews_completed: number;
  report_ready_placeholder: boolean;
}

export interface StudySummary {
  id: string;
  name: string;
  created_at: string;
  archived_at: string | null;
  survey_count: number;
  project_count: number;
  participant_count: number;
}

export interface StudyDetail {
  id: string;
  name: string;
  created_at: string;
  archived_at: string | null;
  surveys: SurveyMini[];
  projects: ProjectMini[];
  progress: StudyProgress;
  recommended_action: string | null;
}

export async function listStudies(): Promise<StudySummary[]> {
  const resp = await client.get<StudySummary[]>("/studies/");
  return resp.data;
}

export async function getStudy(id: string): Promise<StudyDetail> {
  const resp = await client.get<StudyDetail>(`/studies/${id}`);
  return resp.data;
}
